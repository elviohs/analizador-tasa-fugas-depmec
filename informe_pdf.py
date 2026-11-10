# -*- coding: utf-8 -*-
"""Informe PDF trazable del Analizador de Fugas V3 (fpdf2 + fuentes DejaVu de matplotlib).

- Uno o varios ensayos en el mismo informe (con tabla resumen).
- Comparación opcional de ensayos repetidos.
- Español o inglés (lang="es" | "en").
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence

import matplotlib
import numpy as np
from matplotlib.figure import Figure
from fpdf import FPDF

import graficos as gr
import nucleo_fugas as nf
from textos import et, tr


@dataclass
class EnsayoInforme:
    nombre: str
    res: nf.Resultado
    reg: nf.Registro
    temps: Optional[nf.Registro] = None
    observaciones: str = ""


def recurso(nombre: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nombre)


def _fecha(t64, lang, corta=False) -> str:
    d = datetime.strptime(str(t64)[:19], "%Y-%m-%dT%H:%M:%S")
    return d.strftime(et("fmt_fecha_corta" if corta else "fmt_fecha", lang))


class _PDF(FPDF):
    def __init__(self, lang):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.lang = lang
        ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
        self.add_font("DV", "", os.path.join(ttf, "DejaVuSans.ttf"))
        self.add_font("DV", "B", os.path.join(ttf, "DejaVuSans-Bold.ttf"))
        self.set_auto_page_break(True, margin=18)
        self.set_margins(15, 15, 15)

    def footer(self):
        self.set_y(-12)
        self.set_font("DV", "", 7.5)
        self.set_text_color(110, 110, 110)
        self.cell(0, 5, et("pie", self.lang, v=nf.VERSION, p=self.page_no()), align="C")


def _h(pdf, texto, tam=11):
    pdf.ln(2)
    pdf.set_font("DV", "B", tam)
    pdf.set_text_color(11, 11, 11)
    pdf.multi_cell(0, 7, texto, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(200, 200, 200)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(1.5)


def _fila(pdf, k, v, ancho=58):
    pdf.set_font("DV", "B", 8.5)
    pdf.set_text_color(82, 81, 78)
    y = pdf.get_y()
    pdf.multi_cell(ancho, 5, k, new_x="RIGHT", new_y="TOP")
    pdf.set_font("DV", "", 8.5)
    pdf.set_text_color(11, 11, 11)
    pdf.multi_cell(0, 5, v, new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(pdf.get_y(), y + 5))


def _parrafo(pdf, texto, tam=8.2, alto=4.4):
    pdf.set_font("DV", "", tam)
    pdf.set_text_color(11, 11, 11)
    pdf.multi_cell(0, alto, texto, new_x="LMARGIN", new_y="NEXT")


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _tabla(pdf, anchos, cabecera, filas, colores=None, tam=7.6):
    """Tabla con ajuste de texto por celda; `colores[i]` = color de fondo de la última celda."""
    pdf.set_font("DV", "B", tam)
    pdf.set_fill_color(240, 239, 236)
    pdf.set_text_color(11, 11, 11)
    n_lin = max(len(pdf.multi_cell(a, 4.2, t, dry_run=True, output="LINES")) for a, t in zip(anchos, cabecera))
    alto = 4.2 * n_lin + 1.2
    y0, x = pdf.get_y(), pdf.l_margin
    pdf.rect(x, y0, sum(anchos), alto, style="F")
    for a, t in zip(anchos, cabecera):
        pdf.set_xy(x, y0 + 0.6)
        pdf.multi_cell(a, 4.2, t, new_x="RIGHT", new_y="TOP", align="L")
        x += a
    pdf.set_xy(pdf.l_margin, y0 + alto + 0.4)
    pdf.set_font("DV", "", tam)
    for i, f in enumerate(filas):
        n_lin = max(len(pdf.multi_cell(a, 4.2, t, dry_run=True, output="LINES")) for a, t in zip(anchos, f))
        alto = 4.2 * n_lin + 1
        if pdf.get_y() + alto > pdf.h - 20:
            pdf.add_page()
        y0, x = pdf.get_y(), pdf.l_margin
        for j, (a, t) in enumerate(zip(anchos, f)):
            if colores and j == len(f) - 1 and colores[i]:
                pdf.set_fill_color(*_hex(colores[i]))
                pdf.rect(x, y0, a, alto - 0.6, style="F")
            pdf.set_xy(x, y0)
            pdf.multi_cell(a, 4.2, t, new_x="RIGHT", new_y="TOP", align="L")
            x += a
        pdf.set_xy(pdf.l_margin, y0 + alto)
        pdf.set_draw_color(230, 230, 230)
        pdf.line(pdf.l_margin, pdf.get_y() - 0.3, pdf.w - pdf.r_margin, pdf.get_y() - 0.3)


def _figura(func, *args, w=10.0, h=4.6, temporales=None) -> str:
    fig = Figure(figsize=(w, h), dpi=150, facecolor="white")
    func(fig, *args)
    fd, ruta = tempfile.mkstemp(suffix=".png", prefix="fugas_v3_")
    os.close(fd)
    fig.savefig(ruta, dpi=150, facecolor="white")
    if temporales is not None:
        temporales.append(ruta)
    return ruta


def _cabecera(pdf, titulo, lang):
    x_txt = 15
    logo = recurso("logo_depmec.png")
    if os.path.exists(logo):
        info = pdf.image(logo, x=15, y=10, h=15)       # logo IAC DEPMEC (ancho según su proporción)
        x_txt = 15 + float(getattr(info, "rendered_width", 27)) + 5
    pdf.set_xy(x_txt, 12)
    pdf.set_font("DV", "B", 13)
    pdf.multi_cell(0, 6.5, titulo, new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.set_x(x_txt)
    pdf.set_font("DV", "", 8.5)
    pdf.set_text_color(82, 81, 78)
    pdf.cell(0, 5, et("generado", lang, f=datetime.now().strftime(et("fmt_fecha_corta", lang)), v=nf.VERSION),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(pdf.get_y(), 27))
    pdf.ln(6)


def _seccion_ensayo(pdf, e: EnsayoInforme, lang, temporales, titulo=None):
    r, reg = e.res, e.reg
    L = lang
    if titulo:
        _h(pdf, titulo, 12.5)
    # --- veredicto
    pdf.set_fill_color(*_hex(gr.ESTADO.get(r.veredicto, "#d9d8d3")))
    pdf.set_text_color(11, 11, 11)
    pdf.set_font("DV", "B", 12)
    pdf.cell(0, 9, f"  {tr(r.clasificacion, L)}   ·   {et('veredicto', L)}: {tr(r.veredicto, L)}", fill=True,
             new_x="LMARGIN", new_y="NEXT")
    texto = tr(r.explicacion, L) + ("\n" + tr(r.veredicto_motivo, L) if r.veredicto != "SIN CRITERIO" else "")
    pdf.set_font("DV", "", 8.5)
    pdf.multi_cell(0, 4.6, texto, new_x="LMARGIN", new_y="NEXT")

    _h(pdf, et("resultados", L))
    _fila(pdf, et("dpdt_final", L), f"{nf.fmt(r.s_final, 'mbar/s')} ± {nf.fmt(2 * r.s_final_sig)} (2σ) "
          + et("entre", L, a=r.ventana_final[0] / 3600, b=r.ventana_final[1] / 3600))
    _fila(pdf, et("cota", L), f"L ≤ {nf.fmt(r.cota_L, 'mbar/s')}  ({nf.fmt(r.cota_L * 3600, 'mbar/h')})")
    beta = f"{r.beta:.2f} ± {2 * r.beta_sig:.2f} (2σ)  " if np.isfinite(r.beta) else "—  "
    _fila(pdf, et("tendencia", L), beta + et("tendencia_nota", L))
    if r.L_estimada:
        _fila(pdf, et("fuga_est", L), f"{nf.fmt(r.L_estimada[0], 'mbar/s')} ± {nf.fmt(2 * r.L_estimada[1])} (2σ) — "
              + tr(r.L_estimada[2], L))
    else:
        _fila(pdf, et("fuga_est", L), et("no_separable", L))
    c = r.criterio
    if c.volumen_L:
        _fila(pdf, et("volumen", L), f"{c.volumen_L:g} L ± {100 * c.incert_volumen:.0f} %")
        _fila(pdf, et("q_cota", L), f"Q ≤ {nf.fmt(r.Q_cota, 'mbar·L/s')}")
        if r.Q_estimada:
            _fila(pdf, et("q_est", L), f"{nf.fmt(r.Q_estimada[0], 'mbar·L/s')} ± {nf.fmt(2 * r.Q_estimada[1])} (2σ)")
    if c.q_admisible:
        _fila(pdf, et("q_adm", L), nf.fmt(c.q_admisible, "mbar·L/s"))
    if r.carga_especifica:
        q, sq, qc = r.carga_especifica
        _fila(pdf, et("area", L), f"{c.area_cm2:g} cm²")
        _fila(pdf, et("q_esp", L), et("q_esp_txt", L, q=nf.fmt(q), s=nf.fmt(2 * sq), c=nf.fmt(qc), qsi=nf.fmt(q * 1e3)))

    _h(pdf, et("identificacion", L))
    _fila(pdf, et("fichero", L), os.path.basename(r.fichero))
    _fila(pdf, "SHA-256", r.sha256)
    for k, clave in (("Subsystem or prototype", "sistema"), ("Responsible", "responsable"),
                     ("Test Purpose", "objetivo"), ("Start", "inicio_reg")):
        if k in reg.meta:
            _fila(pdf, et(clave, L), reg.meta[k])
    _fila(pdf, et("sensor_cam", L), f"{r.sensor} {reg.etiquetas.get(r.sensor, '')} · {et('unidad', L)}: {r.unidad}")
    if r.sensor_ref:
        _fila(pdf, et("sensor_ref", L), f"{r.sensor_ref} {reg.etiquetas.get(r.sensor_ref, '')}")
    _fila(pdf, et("cierre", L), f"{_fecha(r.t_cierre, L)} — " + et("auto" if r.cierre_auto else "manual", L)
          + (et("confirmado", L) if r.cierre_confirmado_ref else ""))
    _fila(pdf, et("fin", L), f"{_fecha(r.t_fin, L)} — {tr(r.motivo_fin, L)}")
    _fila(pdf, et("duracion", L), f"{r.duracion_s / 3600:.2f} h")
    cf = r.config
    _fila(pdf, et("preproceso", L), et("preproceso_txt", L, e=cf["excluir_inicio_min"], f=100 * cf["fraccion_final"],
                                       m=cf["ventana_final_min_h"],
                                       c=et("si" if cf["corregir_escalon"] else "no", L),
                                       p=et("si" if cf["eliminar_picos"] else "no", L), n=r.n_picos))
    if r.temperaturas:
        _fila(pdf, et("temps", L), "; ".join(f"{k}: {a:.1f}–{b:.1f}" for k, (a, b) in r.temperaturas.items()))
    if e.observaciones.strip():
        _fila(pdf, et("observaciones", L), e.observaciones.strip())

    if r.avisos:
        _h(pdf, et("avisos", L))
        for a in r.avisos:
            _parrafo(pdf, "• " + tr(a, L))
    if r.recomendaciones:
        _h(pdf, et("recomendaciones", L))
        for a in r.recomendaciones:
            _parrafo(pdf, "• " + tr(a, L))

    # --- gráficas
    pdf.add_page()
    _h(pdf, et("graficas", L) + (f" — {e.nombre}" if titulo else ""))
    anchura = pdf.w - 30
    for im in (_figura(gr.dibujar_dpdt, r, L, temporales=temporales),
               _figura(gr.dibujar_subida, r, L, temporales=temporales)):
        pdf.image(im, x=15, w=anchura)
        pdf.ln(2)
    pdf.add_page()
    ventana = (r.t_cierre, r.t_fin)
    im3 = _figura(lambda fg: gr.dibujar_datos(fg, reg, r.unidad, r.sensor, r.sensor_ref, r, e.temps, ventana, L),
                  h=4.0, temporales=temporales)
    pdf.image(im3, x=15, w=anchura)
    pdf.ln(2)

    # --- modelos
    _h(pdf, et("modelos", L))
    _parrafo(pdf, et("modelos_txt", L, t=cf["tau_max_factor"]), tam=7.8, alto=4.2)
    pdf.ln(1)
    filas = []
    if r.derivada is not None:
        d = r.derivada
        filas.append((d.nombre, "—", "—", nf.fmt(d.L), nf.fmt(2 * d.L_sig), "; ".join(tr(a, L) for a in d.avisos) or "—"))
    for mo in r.modelos:
        filas.append((tr(mo.nombre, L), f"{mo.daic:.1f}", f"{mo.peso:.2f}",
                      nf.fmt(mo.L) if mo.tiene_L else et("sin_fuga", L),
                      nf.fmt(2 * mo.L_sig) if mo.tiene_L else "", "; ".join(tr(a, L) for a in mo.avisos) or "—"))
    if filas:
        _tabla(pdf, (50, 15, 13, 24, 20, pdf.w - 30 - 122),
               (et("col_modelo", L), "ΔAIC", et("col_peso", L), "L (mbar/s)", "±2σ", et("col_obs", L)), filas)


def generar_informe_multi(ensayos: Sequence[EnsayoInforme], ruta_pdf: str, lang: str = "es",
                          comparar: bool = False, observaciones: str = "") -> None:
    """Informe de uno o varios ensayos. Con varios: tabla resumen al principio y,
    si `comparar`, la comparación de ensayos repetidos."""
    if not ensayos:
        raise ValueError("No hay ensayos analizados para el informe.")
    L = lang
    temporales: List[str] = []
    try:
        pdf = _PDF(L)
        pdf.alias_nb_pages()
        pdf.add_page()
        multi = len(ensayos) > 1
        _cabecera(pdf, et("titulo_multi" if multi else "titulo", L), L)
        if multi:
            _h(pdf, et("resumen", L))
            filas, colores = [], []
            for i, e in enumerate(ensayos, 1):
                r = e.res
                filas.append((str(i), e.nombre, _fecha(r.t_cierre, L, corta=True), f"{r.duracion_s / 3600:.1f}",
                              tr(r.clasificacion, L) + ("" if r.estacionario else " *"), nf.fmt(r.cota_L),
                              nf.fmt(r.Q_cota), tr(r.veredicto, L)))
                colores.append(gr.ESTADO.get(r.veredicto))
            _tabla(pdf, (7, 45, 25, 13, 34, 19, 19, 18),
                   ("#", et("ensayo", L), et("col_cierre", L), et("col_dur", L), et("col_diag", L),
                    et("col_cota", L), et("col_q", L), et("col_ver", L)), filas, colores, tam=7.3)
            if any(not e.res.estacionario for e in ensayos):
                _parrafo(pdf, "* " + tr(nf.Msg("atencion_no_estac"), L), tam=7.5, alto=4)
        if observaciones.strip():
            _h(pdf, et("obs_generales", L))
            _parrafo(pdf, observaciones.strip())
        if comparar and multi:
            _h(pdf, et("comparacion", L))
            _parrafo(pdf, et("comparacion_nota", L), tam=7.8, alto=4.2)
            rs = [e.res for e in ensayos]
            nombres = [e.nombre for e in ensayos]
            try:
                c = nf.comparar(rs, nombres)
                pdf.ln(1)
                pdf.image(_figura(gr.dibujar_comparacion, rs, nombres, L, h=4.4, temporales=temporales),
                          x=15, w=pdf.w - 30)
                _fila(pdf, et("conclusion", L), tr(c.conclusion, L))
                for n, rm in zip(nombres[1:], c.ratio_medio):
                    _fila(pdf, et("ratio", L), f"{n}: {rm:.2f}")
            except ValueError as err:
                _parrafo(pdf, et("comp_error", L, e=str(err)))
        for i, e in enumerate(ensayos, 1):
            if multi:
                pdf.add_page()
            _seccion_ensayo(pdf, e, L, temporales, titulo=et("ensayo_n", L, i=i, n=e.nombre) if multi else None)
        _h(pdf, et("metodo", L))
        _parrafo(pdf, et("metodo_txt", L), tam=7.8, alto=4.2)
        pdf.output(ruta_pdf)
    finally:
        for t in temporales:
            try:
                os.remove(t)
            except OSError:
                pass


def generar_informe(r: nf.Resultado, reg: nf.Registro, ruta_pdf: str,
                    temps: Optional[nf.Registro] = None, observaciones: str = "", lang: str = "es") -> None:
    """Informe de un solo ensayo (compatibilidad con la v3.0)."""
    generar_informe_multi([EnsayoInforme(os.path.basename(r.fichero), r, reg, temps, observaciones)],
                          ruta_pdf, lang=lang)
