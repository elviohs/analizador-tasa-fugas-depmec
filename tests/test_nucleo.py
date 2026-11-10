# -*- coding: utf-8 -*-
"""Tests del núcleo del Analizador de Fugas V3.

Ejecutar desde la carpeta del programa:   python -m pytest -q tests
Los tests con ficheros reales se saltan si no están en ../Ejemplos de datos.
"""
import math
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import nucleo_fugas as nf  # noqa: E402

EJEMPLOS = [os.path.join(os.path.dirname(AQUI), "..", "Ejemplos de datos"),
            os.path.join(os.path.dirname(AQUI), "Ejemplos de datos")]


def _ejemplo(nombre):
    for d in EJEMPLOS:
        p = os.path.join(d, nombre)
        if os.path.exists(p):
            return p
    pytest.skip(f"No está {nombre}")


# ---------------------------------------------------------------- utilidades
def _fmt(v):
    """Formato CryoMonitor: 3 cifras, coma decimal, exponente sin ceros: 4,13E+1"""
    if not np.isfinite(v):
        return "Overrange"
    m, e = f"{v:.2E}".split("E")
    return f"{m.replace('.', ',')}E{int(e):+d}"


def escribir_sintetico(ruta, p_cam, p_ref, paso=20.0, extra_lineas=()):
    t0 = datetime(2026, 1, 1, 8, 0, 0)
    with open(ruta, "w", encoding="cp1252", newline="\r\n") as f:
        f.write("Subsystem or prototype:  CryoMonitor\t     Cycle: 1\t\n")
        f.write("Responsible: Test\nTest Purpose: Sintético\nStart: x\nAvailable at: x\n")
        f.write("Sampling Period.   Temperature(s):  20     Pressure(s): 20\n\n\n")
        f.write("                                      COM5 C1          COM5 C2\n")
        f.write("Seconds   Date          Local time    Press1(P)        Press2(P)        \n")
        for i, (a, b) in enumerate(zip(p_cam, p_ref)):
            t = t0 + timedelta(seconds=i * paso)
            f.write(f"{int(i * paso) + 1:<10}{t:%d/%m/%Y}    {t.hour}:{t:%M:%S}       {_fmt(a):<17}{_fmt(b)}\n")
        for ln in extra_lineas:
            f.write(ln + "\n")


def caso(tmp_path, nombre, subida, horas=24.0, ruido=0.01, semilla=0, t_cierre_h=1.0):
    rng = np.random.default_rng(semilla)
    t = np.arange(0, (t_cierre_h + horas) * 3600, 20.0)
    tc = t_cierre_h * 3600
    tr = np.clip(t - tc, 0, None)
    p0 = 1e-5
    p = np.where(t < tc, p0, p0 + subida(tr))
    ref = np.where(t < tc, p0, 2e-7)
    p = p * (1 + ruido * rng.standard_normal(len(p)))
    ruta = tmp_path / f"{nombre}.txt"
    escribir_sintetico(ruta, p, ref)
    return str(ruta), tc


CASOS = {
    # nombre: (función de subida, L real [mbar/s])
    "fuga_pura": (lambda t: 1e-7 * t, 1e-7),
    "desgas_potencia": (lambda t: 0.02 * (1 - (1 + t / 1800) ** -0.3), 0.0),
    "desgas_log": (lambda t: 3e-3 * np.log1p(t / 600), 0.0),
    "potencia_mas_fuga": (lambda t: 0.02 * (1 - (1 + t / 1800) ** -0.3) + 2e-8 * t, 2e-8),
    "exp_mas_fuga": (lambda t: 0.02 * (1 - np.exp(-t / 7200)) + 2e-8 * t, 2e-8),
}


# ---------------------------------------------------------------- lectura
def test_lectura_formato_cryomonitor(tmp_path):
    ruta = tmp_path / "f.txt"
    escribir_sintetico(ruta, [1e-5, 2e-5, np.nan, 4e-5] * 10, [1e-6] * 40,
                       extra_lineas=["texto suelto que no es un dato"])
    reg = nf.leer_registro(str(ruta))
    assert reg.columnas_presion() == ["Press1(P)", "Press2(P)"]
    assert reg.etiquetas["Press1(P)"] == "COM5 C1"
    assert reg.digitos == 3
    assert reg.valores_no_numericos == 10
    assert np.isclose(np.nanmax(reg.columnas["Press1(P)"]), 4e-5)
    assert any("no numéricos" in a for a in reg.avisos)


def test_aviso_unidades(tmp_path):
    ruta = tmp_path / "pa.txt"
    escribir_sintetico(ruta, [1.01e5] * 30, [1.0] * 30)
    reg = nf.leer_registro(str(ruta))
    assert any("Unidad" in a or "unidad" in a for a in nf.comprobar_unidades(reg, "mbar"))
    assert not nf.comprobar_unidades(reg, "Pa")


# ---------------------------------------------------------------- sintéticos
@pytest.mark.parametrize("nombre", list(CASOS))
def test_sinteticos_cota_y_cierre(tmp_path, nombre):
    subida, L_real = CASOS[nombre]
    ruta, tc = caso(tmp_path, nombre, subida)
    reg = nf.leer_registro(ruta)
    r = nf.analizar(reg, "Press1(P)", sensor_ref="Press2(P)", con_modelos=True)
    # 1) cierre detectado en el sitio (± 1 min) y confirmado por el sensor turbo
    t_det = (r.t_cierre - reg.tiempo[0]).astype(float)
    assert abs(t_det - tc) <= 60, (t_det, tc)
    assert r.cierre_confirmado_ref
    # 2) la cota superior nunca queda por debajo de la fuga real
    assert r.cota_L >= L_real * 0.98, (r.cota_L, L_real)
    # 3) si se da una estimación, contiene la fuga real
    if r.L_estimada:
        L, s, _ = r.L_estimada
        assert abs(L - L_real) <= 2 * s + 0.05 * L_real, (L, s, L_real)


def test_sintetico_fuga_pura_diagnostico(tmp_path):
    ruta, _ = caso(tmp_path, "fp", CASOS["fuga_pura"][0])
    r = nf.analizar(nf.leer_registro(ruta), "Press1(P)", con_modelos=False)
    assert r.clasificacion == "FUGA DOMINANTE"
    assert abs(r.L_estimada[0] - 1e-7) < 3e-9


@pytest.mark.parametrize("nombre", ["desgas_potencia", "desgas_log"])
def test_sintetico_desgas_no_es_fuga(tmp_path, nombre):
    ruta, _ = caso(tmp_path, nombre, CASOS[nombre][0])
    r = nf.analizar(nf.leer_registro(ruta), "Press1(P)")
    assert r.clasificacion in ("DESGASIFICACIÓN DOMINANTE", "MIXTO / NO CONCLUYENTE")
    assert r.L_estimada is None or r.L_estimada[0] - 2 * r.L_estimada[1] <= 0


def test_sin_subida(tmp_path):
    """Sistema muy estanco: la cámara apenas sube; el cierre se detecta por el sensor turbo."""
    ruta, tc = caso(tmp_path, "plano", lambda t: 1e-6 * (1 - np.exp(-t / 300)), ruido=0.005)
    reg = nf.leer_registro(ruta)
    r = nf.analizar(reg, "Press1(P)", sensor_ref="Press2(P)", con_modelos=False)
    assert abs((r.t_cierre - reg.tiempo[0]).astype(float) - tc) <= 60
    assert r.clasificacion == "SIN SUBIDA SIGNIFICATIVA"
    assert r.cota_L < 1e-10


def test_criterio(tmp_path):
    ruta, _ = caso(tmp_path, "fp2", CASOS["fuga_pura"][0])
    reg = nf.leer_registro(ruta)
    r = nf.analizar(reg, "Press1(P)", criterio=nf.Criterio(10.0, 0.1, 1e-7), con_modelos=False)
    assert r.veredicto == "NO APTO"            # Q ≈ 1e-6 > 1e-7
    r = nf.analizar(reg, "Press1(P)", criterio=nf.Criterio(10.0, 0.1, 1e-5), con_modelos=False)
    assert r.veredicto == "APTO"


def test_escalon_galga_detectado_y_corregido():
    t = np.arange(0, 7200, 20.0)
    p = 1e-3 + 2e-6 * t
    p[t >= 3000] += 1.2e-3       # salto artificial en la banda 1e-3–3e-2
    esc = nf.detectar_escalones(t, p, 3)
    assert len(esc) == 1 and abs(esc[0].salto - 1.2e-3) < 1e-4
    pc = nf.corregir_escalones(t, p, esc)
    assert abs(nf.regresion_lineal(t, pc)[0] - 2e-6) < 2e-8


def test_comparacion_ensayos(tmp_path):
    a, _ = caso(tmp_path, "a", CASOS["desgas_potencia"][0])
    b, _ = caso(tmp_path, "b", lambda t: 0.5 * CASOS["desgas_potencia"][0](t), semilla=1)
    ra = nf.analizar(nf.leer_registro(a), "Press1(P)", con_modelos=False)
    rb = nf.analizar(nf.leer_registro(b), "Press1(P)", con_modelos=False)
    c = nf.comparar([ra, rb], ["1", "2"])
    assert c.ratio_medio[0] < 0.8 and "DESGASIFICACIÓN" in c.conclusion
    f1, _ = caso(tmp_path, "f1", CASOS["fuga_pura"][0])
    f2, _ = caso(tmp_path, "f2", CASOS["fuga_pura"][0], semilla=2)
    c = nf.comparar([nf.analizar(nf.leer_registro(x), "Press1(P)", con_modelos=False) for x in (f1, f2)], ["1", "2"])
    assert "FUGA REAL" in c.conclusion


# ---------------------------------------------------------------- ficheros reales
def test_ejemplo_fuga():
    reg = nf.leer_registro(_ejemplo("LEAK_EXAMPLE.txt"))
    r = nf.analizar(reg, "Press1(P)", sensor_ref="Press2(P)")
    assert r.clasificacion == "FUGA DOMINANTE"
    assert 3.6e-5 < r.s_final < 4.0e-5
    assert r.cierre_confirmado_ref


def test_ejemplo_desgasificacion():
    reg = nf.leer_registro(_ejemplo("OUTGASSING_EXAMPLE.txt"))
    r = nf.analizar(reg, "Press1(P)", sensor_ref="Press2(P)")
    assert r.clasificacion == "DESGASIFICACIÓN DOMINANTE"
    assert r.cota_L < 9e-8      # la V2 daba 9,2e-8 como "fuga real": imposible
    assert len(r.escalones) == 1


def test_temperaturas(tmp_path):
    """Fichero de temperaturas con el mismo formato del CryoMonitor (formato supuesto)."""
    ruta, _ = caso(tmp_path, "fpT", CASOS["fuga_pura"][0])
    reg = nf.leer_registro(ruta)
    rt = tmp_path / "temps.txt"
    t0 = reg.tiempo[0].astype(object)
    with open(rt, "w", encoding="cp1252", newline="\r\n") as f:
        f.write("Subsystem or prototype:  CryoMonitor\n\n                                      COM3 T1          COM3 T2\n")
        f.write("Seconds   Date          Local time    Temp1(K)         Temp2(K)\n")
        for i in range(0, len(reg.tiempo), 3):
            t = t0 + timedelta(seconds=20 * i)
            f.write(f"{20 * i + 1:<10}{t:%d/%m/%Y}    {t.hour}:{t:%M:%S}       {_fmt(295 + i * 1e-3)}        {_fmt(80.0)}\n")
    temps = nf.leer_registro(str(rt))
    assert list(temps.columnas) == ["Temp1(K)", "Temp2(K)"]
    r = nf.analizar(reg, "Press1(P)", temperaturas=temps, con_modelos=False)
    assert "Temp1(K)" in r.temperaturas
    assert any("Temperatura Temp1(K)" in a for a in r.avisos)       # varía ~4 K
    assert not any("Temperatura Temp2(K)" in a for a in r.avisos)   # constante


def test_varios_ensayos_en_un_fichero(tmp_path):
    """Dos cierres de válvula en el mismo registro, con re-bombeo entre ellos."""
    t = np.arange(0, 30 * 3600, 20.0)
    p = np.full(len(t), 1e-5)
    ref = np.full(len(t), 1e-5)
    for tc, dur in ((2 * 3600, 8 * 3600), (16 * 3600, 10 * 3600)):
        m = (t >= tc) & (t < tc + dur)
        p[m] = 1e-5 + 5e-8 * (t[m] - tc)
        ref[m] = 2e-7
    ruta = tmp_path / "dos.txt"
    escribir_sintetico(ruta, p, ref)
    reg = nf.leer_registro(str(ruta))
    a, b, vs = nf.ensayos_en_registro(reg)
    assert (a, b) == ("Press1(P)", "Press2(P)")
    assert len(vs) == 2
    tcs = [(reg.tiempo[v.i0] - reg.tiempo[0]).astype(float) for v in vs]
    assert abs(tcs[0] - 2 * 3600) <= 60 and abs(tcs[1] - 16 * 3600) <= 60


def test_traducciones():
    from textos import Msg, tr, MENSAJES, CODIGOS
    m = Msg("escalon", t=1.0, p=4.7e-3, s=1e-3, pct=21)
    assert "Escalón" in m and tr(m, "en").startswith("Gauge step")
    u = Msg.unir(Msg("exp_fuga", b=0.0, s=0.1), Msg("atencion_no_estac"))
    assert "ATENCIÓN" in u and "WARNING" in tr(u, "en")
    assert tr("NO APTO", "en") == "FAIL" and tr("NO APTO", "es") == "NO APTO"
    for k, (es, en) in MENSAJES.items():   # mismas variables en ambos idiomas
        import string
        f = lambda x: sorted(n for _, n, _, _ in string.Formatter().parse(x) if n)
        assert f(es) == f(en), k


def test_informe_bilingue(tmp_path):
    pytest.importorskip("fpdf")
    import matplotlib
    matplotlib.use("Agg")
    import informe_pdf as ip
    ra, _ = caso(tmp_path, "i1", CASOS["desgas_potencia"][0])
    rb, _ = caso(tmp_path, "i2", lambda t: 0.5 * CASOS["desgas_potencia"][0](t), semilla=3)
    ens = []
    for k, ruta in enumerate((ra, rb)):
        reg = nf.leer_registro(ruta)
        r = nf.analizar(reg, "Press1(P)", sensor_ref="Press2(P)", criterio=nf.Criterio(50, 0.1, 1e-6), con_modelos=False)
        ens.append(ip.EnsayoInforme(f"Ensayo {k + 1}", r, reg))
    for lang in ("es", "en"):
        out = tmp_path / f"inf_{lang}.pdf"
        ip.generar_informe_multi(ens, str(out), lang=lang, comparar=True, observaciones="obs")
        assert out.stat().st_size > 20000
