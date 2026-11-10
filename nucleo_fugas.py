# -*- coding: utf-8 -*-
"""
Núcleo de cálculo del Analizador de Tasa de Fugas DEPMEC - V3
==============================================================

Línea de Vacío y Criogenia - Departamento de Mecánica - IAC

Este módulo no depende de la interfaz gráfica: se puede usar desde scripts,
notebooks o tests. La interfaz (analizador_fugas_v3.py) solo lo llama.

Método (resumen)
----------------
1. Lectura robusta de ficheros CryoMonitor: columnas y unidades desde la
   cabecera, tiempo a partir de fecha + hora local (no del contador de
   segundos), decimales con coma, tokens no numéricos contados y avisados.
2. Detección del cierre de válvula (inicio brusco de una subida sostenida)
   y del final del ensayo (venteo o re-bombeo). Si se indica el sensor del
   lado de la turbo, se usa para confirmar el cierre (la turbo baja o se
   mantiene mientras la cámara sube).
3. Preprocesado: eliminación de picos aislados, corrección del escalón que
   producen las galgas de rango completo al cambiar de sistema de medida
   (≈5e-3 mbar en los datos del EMCTS), exclusión del transitorio inicial.
4. Análisis SIN MODELO (resultado principal):
   - dP/dt en ventanas logarítmicas a lo largo del ensayo.
   - Pendiente en la ventana final con incertidumbre (autocorrelación y
     resolución del registro incluidas).
   - Cota superior de la fuga: L <= dP/dt_final + 2·sigma. Es válida porque
     dP/dt = fuga + desgasificación y la desgasificación no es negativa
     (salvo readsorción o bajadas de temperatura, que se avisan).
   - Exponente de tendencia beta (dP/dt ∝ t^beta en la última media década):
     beta ≈ 0 -> fuga dominante; beta << 0 -> desgasificación dominante.
5. Estimación CON MODELO (secundaria): ajuste de dP/dt = L + B·(t+t0)^-n y
   comparación de modelos P(t) (exponencial, doble exponencial, potencia,
   logarítmico, con y sin fuga) con AIC, IC de L y avisos de no
   separabilidad o de inconsistencia con la cota superior.
6. Criterio de aceptación opcional: Q admisible y volumen (± incertidumbre)
   -> APTO / NO APTO / NO CONCLUYENTE, siempre del lado conservador.
7. Comparación de ensayos repetidos (método recomendado por Leybold):
   misma fuga -> misma dP/dt a igual tiempo desde el cierre; desgasificación
   -> la dP/dt baja de un ensayo al siguiente.
"""
from __future__ import annotations

import hashlib
import math
import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import least_squares

from textos import Msg

VERSION = "3.2.0"

# Factores de conversión a mbar
UNIDADES = {"mbar": 1.0, "hPa": 1.0, "Pa": 0.01, "Torr": 1.333224, "bar": 1000.0}

# Valores por defecto de la configuración (todos ajustables desde la GUI)
CONFIG_DEFECTO = {
    "excluir_inicio_min": 15.0,       # transitorio tras el cierre
    "fraccion_final": 0.20,           # ventana final para la pendiente (fracción de la duración)
    "ventana_final_min_h": 1.0,       # mínimo de esa ventana
    "corregir_escalon": True,
    "banda_escalon": (1e-3, 3e-2),    # mbar, zona de cambio de sistema de medida
    "eliminar_picos": True,
    "beta_fuga": -0.20,               # beta > este valor -> fuga dominante
    "beta_desgas": -0.60,             # beta < este valor -> desgasificación dominante
    "tau_max_factor": 1.0,            # tau <= factor·T en los modelos exponenciales
    "umbral_pirani_mbar": 1e-2,       # por encima mide la Pirani (depende del gas)
    "umbral_temp_K": 2.0,             # aviso si la temperatura varía más que esto
}


# =============================================================================
# 1. LECTURA DE FICHEROS
# =============================================================================
_RE_FECHA = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_RE_HORA = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")


@dataclass
class Registro:
    """Contenido de un fichero CryoMonitor (o compatible)."""
    ruta: str
    sha256: str
    meta: Dict[str, str]
    tiempo: np.ndarray                 # datetime64[s]
    columnas: Dict[str, np.ndarray]    # nombre -> valores (unidades originales)
    etiquetas: Dict[str, str]          # nombre -> etiqueta de canal (p.ej. "COM5 C1")
    digitos: int = 3                   # cifras significativas del registro
    lineas_descartadas: int = 0
    valores_no_numericos: int = 0
    avisos: List[str] = field(default_factory=list)

    @property
    def segundos(self) -> np.ndarray:
        return (self.tiempo - self.tiempo[0]).astype("timedelta64[s]").astype(float)

    def columnas_presion(self) -> List[str]:
        n = [c for c in self.columnas if re.search(r"press|\(p\)|mbar|pa\b|torr", c, re.I)]
        return n or [c for c in self.columnas if not re.search(r"temp|\(k\)|\(c\)", c, re.I)]

    def columnas_temperatura(self) -> List[str]:
        return [c for c in self.columnas if c not in self.columnas_presion()]


def _sha256(ruta: str) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _leer_texto(ruta: str) -> List[str]:
    with open(ruta, "rb") as f:
        crudo = f.read()
    for cod in ("utf-8", "cp1252", "latin-1"):
        try:
            return crudo.decode(cod).splitlines()
        except UnicodeDecodeError:
            continue
    return crudo.decode("latin-1", errors="replace").splitlines()


def _a_float(tok: str) -> Tuple[float, int]:
    """Convierte '4,13E+1' -> (41.3, 3 cifras). Devuelve (nan, 0) si no es numérico."""
    t = tok.strip().replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return math.nan, 0
    mant = re.split(r"[eE]", t)[0].replace("-", "").replace("+", "").replace(".", "").lstrip("0")
    return v, max(len(mant), 1)


def leer_registro(ruta: str) -> Registro:
    """Lee un fichero CryoMonitor de presiones o de temperaturas.

    Reconoce la cabecera ('Seconds  Date  Local time  Press1(P) ...'), toma los
    nombres de columna de ella y usa fecha+hora como base de tiempos. Admite
    cabeceras repetidas a mitad de fichero y contadores de segundos que se
    reinician.
    """
    lineas = _leer_texto(ruta)
    meta: Dict[str, str] = {}
    for ln in lineas[:12]:
        m = re.match(r"\s*([A-Za-zÁÉÍÓÚáéíóúñÑ ]+?):\s*(.+)", ln)
        if m and not ln.lstrip().startswith("Seconds"):
            meta[m.group(1).strip()] = re.sub(r"\s+", " ", m.group(2)).strip()

    nombres: Optional[List[str]] = None
    etiquetas_canal: List[str] = []
    linea_previa = ""
    filas_t: List[str] = []
    filas_v: List[List[float]] = []
    digitos = 0
    descartadas = no_num = 0
    for ln in lineas:
        s = ln.strip()
        if not s:
            linea_previa = ln
            continue
        if re.search(r"\bDate\b", s) and re.search(r"time", s, re.I):
            campos = re.split(r"\s{2,}", s)
            idx = [i for i, c in enumerate(campos) if re.search(r"time", c, re.I)]
            nombres = campos[idx[-1] + 1:] if idx else campos[3:]
            etiquetas_canal = re.split(r"\s{2,}", linea_previa.strip()) if linea_previa.strip() else []
            linea_previa = ln
            continue
        linea_previa = ln
        if nombres is None:
            continue
        toks = s.split()
        # localizar fecha y hora
        i_f = next((i for i, t in enumerate(toks[:4]) if _RE_FECHA.match(t)), None)
        if i_f is None or i_f + 1 >= len(toks) or not _RE_HORA.match(toks[i_f + 1]):
            descartadas += 1
            continue
        vals = []
        for t in toks[i_f + 2:]:
            v, d = _a_float(t)
            if math.isnan(v):
                no_num += 1
            digitos = max(digitos, d)
            vals.append(v)
        if not vals:
            descartadas += 1
            continue
        filas_t.append(toks[i_f] + " " + toks[i_f + 1])
        filas_v.append(vals)

    if nombres is None:
        raise ValueError("No se encontró la cabecera de datos (línea con 'Date' y 'Local time').")
    if not filas_t:
        raise ValueError("El fichero no contiene filas de datos válidas.")

    ncol = max(len(v) for v in filas_v)
    if len(nombres) < ncol:
        nombres = list(nombres) + [f"Col{i + 1}" for i in range(len(nombres), ncol)]
    nombres = nombres[:ncol]
    M = np.full((len(filas_v), ncol), np.nan)
    for i, v in enumerate(filas_v):
        M[i, :len(v)] = v

    tiempo = np.array([datetime.strptime(x, "%d/%m/%Y %H:%M:%S") for x in filas_t], dtype="datetime64[s]")
    orden = np.argsort(tiempo, kind="stable")
    avisos = []
    if np.any(np.diff(orden) < 0):
        avisos.append(Msg("lec_desordenado"))
    tiempo, M = tiempo[orden], M[orden]
    _, unicos = np.unique(tiempo, return_index=True)
    if len(unicos) < len(tiempo):
        avisos.append(Msg("lec_duplicados", n=len(tiempo) - len(unicos)))
        tiempo, M = tiempo[unicos], M[unicos]
    dt = np.diff(tiempo).astype(float)
    if len(dt):
        paso = np.median(dt)
        huecos = int(np.sum(dt > 10 * paso))
        if huecos:
            avisos.append(Msg("lec_huecos", n=huecos, paso=paso))
    if no_num:
        avisos.append(Msg("lec_no_num", n=no_num))
    if descartadas:
        avisos.append(Msg("lec_descartadas", n=descartadas))

    etiq = {}
    if len(etiquetas_canal) == len(nombres):
        etiq = dict(zip(nombres, etiquetas_canal))
    return Registro(ruta=ruta, sha256=_sha256(ruta), meta=meta, tiempo=tiempo,
                    columnas={n: M[:, i] for i, n in enumerate(nombres)}, etiquetas=etiq,
                    digitos=digitos or 3, lineas_descartadas=descartadas,
                    valores_no_numericos=no_num, avisos=avisos)


def comprobar_unidades(reg: Registro, unidad: str) -> List[str]:
    """Avisos de plausibilidad de unidades (p.ej. presión atmosférica fuera de rango)."""
    av = []
    f = UNIDADES[unidad]
    for c in reg.columnas_presion():
        v = reg.columnas[c] * f
        mx = np.nanmax(v) if np.any(np.isfinite(v)) else np.nan
        if np.isfinite(mx) and mx > 2000:
            av.append(Msg("uni_max", c=c, mx=mx))
        if np.isfinite(mx) and np.nanmin(v) <= 0:
            av.append(Msg("uni_neg", c=c))
    return av


# =============================================================================
# 2. UTILIDADES ESTADÍSTICAS
# =============================================================================
def resolucion(p: np.ndarray, digitos: int) -> np.ndarray:
    """Paso de cuantificación del registro (p.ej. 3 cifras: 4,71E-3 -> 1e-5)."""
    p = np.asarray(p, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 ** (np.floor(np.log10(np.abs(p))) - (digitos - 1))


def regresion_lineal(t: np.ndarray, p: np.ndarray, q: float = 0.0) -> Tuple[float, float, float]:
    """Pendiente por mínimos cuadrados con error típico corregido por
    autocorrelación (n efectivo con rho lag-1) y con un suelo por la resolución
    del registro (0,5·q/duración). Devuelve (pendiente, sigma, ordenada)."""
    n = len(t)
    if n < 3:
        return math.nan, math.nan, math.nan
    tm = t.mean()
    x = t - tm
    sxx = np.sum(x * x)
    if sxx <= 0:
        return math.nan, math.nan, math.nan
    m = np.sum(x * (p - p.mean())) / sxx
    b = p.mean() - m * tm
    r = p - (m * t + b)
    s2 = np.sum(r * r) / max(n - 2, 1)
    se = math.sqrt(s2 / sxx)
    if n > 4 and np.std(r) > 0:
        rho = np.corrcoef(r[:-1], r[1:])[0, 1]
        rho = min(max(rho if np.isfinite(rho) else 0.0, 0.0), 0.99)
        se *= math.sqrt((1 + rho) / (1 - rho))
    dur = t[-1] - t[0]
    if dur > 0 and q > 0:
        se = max(se, 0.5 * q / dur)
    return m, se, b


def reducir(t: np.ndarray, p: np.ndarray, nmax: int = 1500) -> Tuple[np.ndarray, np.ndarray]:
    """Promedia en intervalos de tiempo iguales para ajustar modelos rápido."""
    if len(t) <= nmax:
        return t, p
    bordes = np.linspace(t[0], t[-1], nmax + 1)
    k = np.clip(np.searchsorted(bordes, t, side="right") - 1, 0, nmax - 1)
    cnt = np.bincount(k, minlength=nmax)
    ok = cnt > 0
    tb = np.bincount(k, weights=t, minlength=nmax)[ok] / cnt[ok]
    pb = np.bincount(k, weights=p, minlength=nmax)[ok] / cnt[ok]
    return tb, pb


# =============================================================================
# 3. DETECCIÓN DEL ENSAYO (CIERRE Y FINAL)
# =============================================================================
@dataclass
class Ventana:
    i0: int
    i1: int
    confirmado_ref: bool = False
    motivo_fin: str = ""
    puntuacion: float = 0.0


def _suave(x: np.ndarray, k: int = 5) -> np.ndarray:
    if len(x) < k:
        return x.copy()
    pad = k // 2
    xp = np.pad(x, pad, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(xp, k), axis=1)


def detectar_final(t: np.ndarray, p: np.ndarray, i0: int) -> Tuple[int, str]:
    """Primer índice tras i0 donde se ventea (salto a > 100 mbar) o se vuelve
    a bombear (caída sostenida por debajo del 50 % del máximo alcanzado)."""
    lp = _suave(np.log10(np.clip(p, 1e-15, None)), 5)
    pmax = -np.inf
    for i in range(i0 + 1, len(p)):
        if p[i] > 100 and p[i] > 5 * p[i - 1]:
            return i - 1, "venteo"
        pmax = max(pmax, lp[i - 1])
        if i - i0 > 10 and lp[i] < pmax - math.log10(2) and np.all(lp[i:i + 3] < pmax - math.log10(2)):
            return i - 1, "re-bombeo o apertura de válvula"
    return len(p) - 1, "fin del registro"


def detectar_ensayo(t: np.ndarray, p: np.ndarray, ref: Optional[np.ndarray] = None, todos: bool = False):
    """Busca el cierre de válvula: inicio BRUSCO de una subida SOSTENIDA.

    - Brusco: la subida en log10 en los 10 min siguientes es >= 0,1 décadas y
      al menos 5 veces mayor que la tendencia de los 30 min anteriores.
    - Sostenida: el ensayo que empieza ahí dura >= 1 h hasta venteo/re-bombeo.
    - Si hay sensor de referencia (lado turbo), se prefiere el candidato donde
      log10(P_cámara/P_ref) sube > 0,3 décadas (la turbo queda aislada).
    Puntuación = duración·(1 + confirmación). Devuelve None si no hay candidato.
    """
    ok = np.isfinite(p) & (p > 0)
    idx_ok = np.where(ok)[0]
    if len(idx_ok) < 20:
        return [] if todos else None
    tt, lp = t[idx_ok], _suave(np.log10(p[idx_ok]), 3)
    j10 = np.searchsorted(tt, tt + 600.0)
    j30 = np.searchsorted(tt, tt - 1800.0)
    cand = []
    i = 1
    n = len(tt)
    while i < n - 3:
        k = min(j10[i], n - 1)
        if k <= i:
            i += 1
            continue
        sube = lp[k] - lp[i]
        if sube >= 0.05:
            a = j30[i]
            pre = (lp[i] - lp[a]) / max(tt[i] - tt[a], 1.0) * 600.0 if i > a else 0.0
            if pre <= sube / 5.0:
                # el cierre es la muestra previa al mayor salto entre muestras
                # consecutivas en [i - 10 min, i + 10 min] (datos sin suavizar)
                a2 = int(np.searchsorted(tt, tt[i] - 600.0))
                lraw = np.log10(p[idx_ok[a2:k + 1]])
                ini = a2 + int(np.argmax(np.diff(lraw))) if len(lraw) > 1 else i
                cand.append(ini)
                # saltar hasta que deje de subir bruscamente
                i = k
                continue
        i += 1
    # candidatos adicionales desde el sensor del lado turbo: caída brusca
    # (> 0,5 décadas en 10 min) mientras la cámara no baja
    if ref is not None:
        okr = np.isfinite(ref) & (ref > 0) & ok
        ir = np.where(okr)[0]
        if len(ir) > 20:
            # mediana móvil de 3 muestras: un pico aislado del sensor no es un cierre
            tr, lr = t[ir], _suave(np.log10(ref[ir]), 3)
            lc = _suave(np.log10(p[ir]), 3)
            k10 = np.searchsorted(tr, tr + 600.0)
            j = 0
            while j < len(ir) - 3:
                k = min(k10[j], len(ir) - 1)
                if k > j and lr[j] - lr[k] > 0.5 and lc[k] >= lc[j] - 0.02:
                    seg = lr[j:k + 1]
                    jj = j + int(np.argmin(np.diff(seg)))
                    cand.append(int(np.searchsorted(idx_ok, ir[jj])))
                    j = k
                    continue
                j += 1
    mejores: List[Ventana] = []
    for c in sorted(set(cand)):
        g0 = idx_ok[c]
        g1, motivo = detectar_final(t, p, g0)
        dur = t[g1] - t[g0]
        if dur < 3600:
            continue
        # la cámara tiene que subir: mediana final > nivel antes del cierre (+2 %)
        seg = np.where((t >= t[g0]) & (t <= t[g1]) & np.isfinite(p) & (p > 0))[0]
        if len(seg) < 10:
            continue
        n10 = max(3, len(seg) // 10)
        pre = np.where((t >= t[g0] - 600) & (t <= t[g0]) & np.isfinite(p) & (p > 0))[0]
        nivel0 = np.median(p[pre]) if len(pre) else np.median(p[seg[:n10]])
        if np.median(p[seg[-n10:]]) <= 1.02 * nivel0:
            continue
        # confirmación con el lado turbo: la relación cámara/turbo cambia > 0,3
        # décadas y SE MANTIENE (mediana entre 1 y 30 min tras el cierre). Vale
        # tanto si la turbo queda aislada (baja) como si se ventea (sube).
        conf = False
        if ref is not None:
            r = ref
            a = np.where((t >= t[g0] - 600) & (t < t[g0]) & np.isfinite(r) & (r > 0))[0]
            b = np.where((t > t[g0] + 60) & (t <= t[g0] + 1800) & np.isfinite(r) & (r > 0))[0]
            if len(a) and len(b) >= 3:
                rat0 = np.median(np.log10(p[a] / r[a]))
                rat1 = np.median(np.log10(p[b] / r[b]))
                conf = abs(rat1 - rat0) > 0.3
        mejores.append(Ventana(g0, g1, conf, motivo, dur * (2.0 if conf else 1.0)))
    if not mejores:
        return [] if todos else None
    if ref is not None and any(v.confirmado_ref for v in mejores):
        mejores = [v for v in mejores if v.confirmado_ref]
    if not todos:
        return max(mejores, key=lambda v: v.puntuacion)
    # todos los ensayos que no se solapan, empezando por los de mayor puntuación
    elegidos: List[Ventana] = []
    for v in sorted(mejores, key=lambda v: -v.puntuacion):
        if all(v.i1 < e.i0 or v.i0 > e.i1 for e in elegidos):
            elegidos.append(v)
    return sorted(elegidos, key=lambda v: v.i0)


def detectar_ensayos(t: np.ndarray, p: np.ndarray, ref: Optional[np.ndarray] = None) -> List[Ventana]:
    """Todos los ensayos de subida (cierres de válvula) de un registro, sin solaparse."""
    return detectar_ensayo(t, p, ref, todos=True)


def sugerir_roles(reg: Registro, unidad: str = "mbar") -> Tuple[Optional[str], Optional[str], Optional[Ventana]]:
    """Propone qué sensor es la cámara y cuál el lado turbo probando ambas
    asignaciones: la buena es la que da un cierre confirmado (la cámara sube
    mientras el lado turbo baja o queda aislado) y el ensayo más largo."""
    cols = reg.columnas_presion()
    if not cols:
        return None, None, None
    f = UNIDADES[unidad]
    t = reg.segundos
    if len(cols) == 1:
        return cols[0], None, detectar_ensayo(t, reg.columnas[cols[0]] * f)
    opciones = []
    for a in cols:
        for b in cols:
            if a == b:
                continue
            v = detectar_ensayo(t, reg.columnas[a] * f, reg.columnas[b] * f)
            if v is not None:
                opciones.append((v.confirmado_ref, t[v.i1] - t[v.i0], -cols.index(a), a, b, v))
    if not opciones:
        return cols[0], cols[1], None
    opciones.sort(reverse=True)
    _, _, _, a, b, v = opciones[0]
    return a, b, v


def ensayos_en_registro(reg: Registro, unidad: str = "mbar") -> Tuple[Optional[str], Optional[str], List[Ventana]]:
    """Roles de los sensores y TODOS los ensayos de subida del fichero."""
    a, b, _ = sugerir_roles(reg, unidad)
    if a is None:
        return None, None, []
    f = UNIDADES[unidad]
    ref = reg.columnas[b] * f if b else None
    return a, b, detectar_ensayos(reg.segundos, reg.columnas[a] * f, ref)


# =============================================================================
# 4. PREPROCESADO
# =============================================================================
@dataclass
class Escalon:
    t_s: float
    p_antes: float
    p_despues: float
    salto: float  # mbar, ya descontado lo que correspondería a la subida normal


def quitar_picos(t: np.ndarray, p: np.ndarray, k: int = 7, nsig: float = 6.0) -> np.ndarray:
    """Máscara de puntos válidos (Hampel en log10 p, solo picos aislados <= 2 muestras)."""
    lp = np.log10(np.clip(p, 1e-15, None))
    med = _suave(lp, k)
    pad = k // 2
    dev = np.abs(lp - med)
    mad = _suave(dev, k) * 1.4826
    sig = np.maximum(mad, 0.005)
    mala = dev > nsig * sig
    # solo aislados
    out = mala.copy()
    run = 0
    for i in range(len(mala)):
        run = run + 1 if mala[i] else 0
        if run > 2:
            out[i - run + 1:i + 1] = False
    return ~out


def detectar_escalones(t: np.ndarray, p: np.ndarray, digitos: int,
                       banda: Tuple[float, float] = (1e-3, 3e-2), n_vec: int = 15) -> List[Escalon]:
    """Saltos de lectura en la banda de cambio de sistema de medida de las galgas
    de rango completo. Un salto es un incremento entre dos muestras muy superior
    al esperado por la tendencia local (ajustada sin ese punto)."""
    esc = []
    dp = np.diff(p)
    q = resolucion(p, digitos)
    for k in range(len(dp)):
        if not (banda[0] <= p[k] <= banda[1]):
            continue
        a, b = max(0, k - n_vec), min(len(dp), k + n_vec + 1)
        vec = np.r_[dp[a:k], dp[k + 1:b]]
        tv = np.r_[t[a + 1:k + 1], t[k + 2:b + 1]]
        if len(vec) < 6:
            continue
        dtk = t[k + 1] - t[k]
        dts = np.r_[np.diff(t)[a:k], np.diff(t)[k + 1:b]]
        tasa = np.median(vec / np.where(dts > 0, dts, np.nan))
        esperado = tasa * dtk
        resid = dp[k] - esperado
        disp = 1.4826 * np.median(np.abs(vec - np.median(vec)))
        umbral = max(6 * disp, 3 * q[k], 0.08 * p[k])
        if resid > umbral:
            esc.append(Escalon(float(t[k + 1]), float(p[k]), float(p[k + 1]), float(resid)))
    # quedarse con el mayor de cada grupo (muestras contiguas)
    final: List[Escalon] = []
    for e in esc:
        if final and abs(e.t_s - final[-1].t_s) < 600:
            if e.salto > final[-1].salto:
                final[-1] = e
        else:
            final.append(e)
    return final


def corregir_escalones(t: np.ndarray, p: np.ndarray, escalones: Sequence[Escalon]) -> np.ndarray:
    pc = p.copy()
    for e in escalones:
        pc[t >= e.t_s] -= e.salto
    return pc


# =============================================================================
# 5. ANÁLISIS SIN MODELO
# =============================================================================
@dataclass
class Pendientes:
    t: np.ndarray      # centro de cada ventana [s desde cierre]
    s: np.ndarray      # dP/dt [mbar/s]
    sig: np.ndarray    # 1 sigma


def pendientes_ventana(t: np.ndarray, p: np.ndarray, digitos: int,
                       decadas: float = 0.2, paso: float = 0.1, n_min: int = 8) -> Pendientes:
    """dP/dt en ventanas logarítmicas [c·10^-w/2, c·10^w/2] (solapadas)."""
    t_ini = max(t[0], 60.0)
    if t[-1] <= t_ini * 1.2:
        return Pendientes(np.array([]), np.array([]), np.array([]))
    # rejilla anclada al FINAL del ensayo: la última ventana termina en t[-1]
    lt_fin = math.log10(t[-1]) - decadas / 2
    centros = 10 ** np.arange(lt_fin, math.log10(t_ini) + decadas / 2 - 1e-9, -paso)[::-1]
    if len(centros) == 0:
        centros = np.array([math.sqrt(t_ini * t[-1])])
    tc, sc, ec = [], [], []
    q = resolucion(p, digitos)
    for c in centros:
        a, b = c * 10 ** (-decadas / 2), c * 10 ** (decadas / 2)
        m = (t >= a) & (t <= b)
        if m.sum() < n_min:
            continue
        ts = t[m]
        if (ts[-1] - ts[0]) < 0.5 * (b - a):   # hueco: cobertura insuficiente
            continue
        s, e, _ = regresion_lineal(ts, p[m], float(np.nanmedian(q[m])))
        if np.isfinite(s):
            tc.append(c); sc.append(s); ec.append(e * math.sqrt(2.0))  # x sqrt(2): ventanas solapadas
    return Pendientes(np.array(tc), np.array(sc), np.array(ec))


def tendencia_beta(pend: Pendientes, t_fin: float, decadas: float = 0.5) -> Tuple[float, float, int, int]:
    """Exponente beta de dP/dt ∝ t^beta en el tramo final del ensayo
    (última media década por defecto: describe el comportamiento AL FINAL,
    que es lo que importa para separar fuga de desgasificación).
    Si hay menos de 4 ventanas, amplía el tramo. Devuelve (beta, sigma, n_usadas, n_negativas)."""
    if len(pend.t) == 0:
        return math.nan, math.nan, 0, 0
    m = pend.t >= max(t_fin / 10 ** decadas, pend.t.min())
    for d in (decadas + 0.25, decadas + 0.5, 1.5, 3.0):
        if m.sum() >= 4:
            break
        m = pend.t >= max(t_fin / 10 ** d, pend.t.min())
    neg = int(np.sum(m & (pend.s <= 0)))
    m &= pend.s > 0
    if m.sum() < 3:
        return math.nan, math.nan, int(m.sum()), neg
    x = np.log10(pend.t[m])
    y = np.log10(pend.s[m])
    w = (pend.s[m] / np.maximum(pend.sig[m], 1e-300)) ** 2  # 1/var(log s) ~ (s/sigma)^2
    W = np.sum(w)
    xm, ym = np.sum(w * x) / W, np.sum(w * y) / W
    sxx = np.sum(w * (x - xm) ** 2)
    if sxx <= 0:
        return math.nan, math.nan, int(m.sum()), neg
    beta = np.sum(w * (x - xm) * (y - ym)) / sxx
    r = y - (ym + beta * (x - xm))
    chi2 = np.sum(w * r * r) / max(m.sum() - 2, 1)
    sig = math.sqrt(max(chi2, 1.0) / sxx)
    return float(beta), float(sig), int(m.sum()), neg


# =============================================================================
# 6. MODELOS
# =============================================================================
@dataclass
class ResultadoModelo:
    nombre: str
    params: Dict[str, float]
    sigma: Dict[str, float]
    L: float                 # mbar/s (0 si el modelo no tiene fuga)
    L_sig: float
    rms: float
    aic: float
    daic: float = 0.0
    peso: float = 0.0
    corr_max_L: float = 0.0
    en_limite: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    curva: Optional[Tuple[np.ndarray, np.ndarray]] = None
    tiene_L: bool = True


def _modelos_P(T: float, pm: float, tau_max: float):
    """Modelos de P(t) [t en horas, P en mbar, L en mbar/h]."""
    Th = T
    return {
        "Exponencial + fuga (V2)": (
            lambda t, P0, A, tau, L: P0 + A * (1 - np.exp(-t / tau)) + L * t,
            ["P0", "A", "tau", "L"], [0, 0, Th * 1e-3, 0], [np.inf, np.inf, tau_max, np.inf]),
        "Doble exponencial + fuga": (
            lambda t, P0, A1, t1, A2, t2, L: P0 + A1 * (1 - np.exp(-t / t1)) + A2 * (1 - np.exp(-t / t2)) + L * t,
            ["P0", "A1", "t1", "A2", "t2", "L"], [0, 0, Th * 1e-3, 0, Th * 1e-3, 0],
            [np.inf, np.inf, tau_max, np.inf, tau_max, np.inf]),
        "Potencia + fuga": (
            lambda t, P0, a, t0, n, L: P0 + a * ((t + t0) ** (1 - n) - t0 ** (1 - n)) / (1 - n) + L * t,
            ["P0", "a", "t0", "n", "L"], [0, 0, Th * 1e-4, 1.02, 0], [np.inf, np.inf, 10 * Th, 4.0, np.inf]),
        "Logarítmico + fuga": (
            lambda t, P0, a, t0, L: P0 + a * np.log1p(t / t0) + L * t,
            ["P0", "a", "t0", "L"], [0, 0, Th * 1e-4, 0], [np.inf, np.inf, 10 * Th, np.inf]),
        "Exponencial (sin fuga)": (
            lambda t, P0, A, tau: P0 + A * (1 - np.exp(-t / tau)),
            ["P0", "A", "tau"], [0, 0, Th * 1e-3], [np.inf, np.inf, tau_max]),
        "Potencia (sin fuga)": (
            lambda t, P0, a, t0, n: P0 + a * ((t + t0) ** (1 - n) - t0 ** (1 - n)) / (1 - n),
            ["P0", "a", "t0", "n"], [0, 0, Th * 1e-4, 1.02], [np.inf, np.inf, 10 * Th, 4.0]),
    }


def _ajustar(f, nombres, lb, ub, t, p, n_arr=10, semilla=0):
    rng = np.random.default_rng(semilla)
    T = t[-1]
    pm = max(p.max(), 1e-30)
    escala = []
    for nm in nombres:
        if nm in ("P0", "A", "A1", "A2", "a"):
            escala.append(pm)
        elif nm == "L":
            escala.append(pm / T)
        elif nm == "n":
            escala.append(1.0)
        else:
            escala.append(T)
    escala = np.array(escala)
    mejor = None
    for _ in range(n_arr):
        x0 = []
        for nm, lo, hi in zip(nombres, lb, ub):
            if nm == "P0":
                v = max(p[0], 0)
            elif nm in ("A", "A1", "A2", "a"):
                v = pm * rng.uniform(0.02, 1.0)
            elif nm == "L":
                v = pm / T * rng.uniform(0.0, 0.5)
            elif nm == "n":
                v = rng.uniform(1.05, 2.5)
            else:
                v = 10 ** rng.uniform(math.log10(max(lo, T * 1e-3)), math.log10(min(hi, 10 * T)))
            x0.append(min(max(v, lo + 1e-12 * (abs(lo) + 1)), hi if np.isfinite(hi) else v))
        try:
            with np.errstate(all="ignore"):
                r = least_squares(lambda x: f(t, *x) - p, x0, bounds=(lb, ub), x_scale=escala,
                                  method="trf", max_nfev=4000)
        except Exception:
            continue
        if np.all(np.isfinite(r.fun)) and (mejor is None or r.cost < mejor.cost):
            mejor = r
    return mejor


def ajustar_modelos(t_s: np.ndarray, p: np.ndarray, tau_max_factor: float = 1.0,
                    cota_sup: float = math.inf) -> List[ResultadoModelo]:
    """Ajusta y compara los modelos de P(t). t en s desde el cierre, p en mbar."""
    th, pr = reducir(t_s / 3600.0, p, 1500)
    th = th - th[0] + 1e-9 if th[0] < 0 else th
    T = th[-1]
    res: List[ResultadoModelo] = []
    for nombre, (f, nombres, lb, ub) in _modelos_P(T, pr.max(), tau_max_factor * T).items():
        r = _ajustar(f, nombres, lb, ub, th, pr)
        if r is None:
            continue
        n, k = len(th), len(nombres)
        rss = 2 * r.cost
        J = r.jac
        # inflar covarianza por autocorrelación de residuos
        ro = np.corrcoef(r.fun[:-1], r.fun[1:])[0, 1] if n > 5 and np.std(r.fun) > 0 else 0.0
        ro = min(max(ro if np.isfinite(ro) else 0.0, 0.0), 0.99)
        infl = (1 + ro) / (1 - ro)
        try:
            cov = np.linalg.pinv(J.T @ J) * rss / max(n - k, 1) * infl
            sig = np.sqrt(np.clip(np.diag(cov), 0, None))
        except Exception:
            cov = None
            sig = np.full(k, np.nan)
        aic = n * math.log(max(rss, 1e-300) / n) + 2 * k
        pars = dict(zip(nombres, r.x))
        sigs = dict(zip(nombres, sig))
        tiene_L = "L" in pars
        L = pars.get("L", 0.0) / 3600.0
        Ls = sigs.get("L", 0.0) / 3600.0
        corr = 0.0
        if tiene_L and cov is not None:
            iL = nombres.index("L")
            d = np.sqrt(np.clip(np.diag(cov), 1e-300, None))
            with np.errstate(all="ignore"):
                cc = np.clip(cov[iL] / (d[iL] * d), -1.0, 1.0)
            cc[iL] = 0
            cc[np.diag(cov) <= 0] = 0
            corr = float(np.nanmax(np.abs(cc)))
        lim = [nm for nm, v, lo, hi in zip(nombres, r.x, lb, ub)
               if nm not in ("P0", "L") and (abs(v - lo) <= 1e-6 * max(abs(lo), 1e-12) * 10 or (np.isfinite(hi) and v >= hi * 0.999))]
        av = []
        if tiene_L:
            if L - 2 * Ls <= 0:
                av.append(Msg("mod_L0"))
            if corr > 0.95:
                av.append(Msg("mod_corr", r=corr))
            if np.isfinite(cota_sup) and L - 2 * Ls > cota_sup:
                av.append(Msg("mod_incons"))
        if lim:
            av.append(Msg("mod_lim", p=", ".join(lim)))
        tf = np.linspace(0, T, 400)
        with np.errstate(all="ignore"):
            curva = (tf * 3600.0, f(tf, *r.x))
        res.append(ResultadoModelo(nombre, pars, sigs, L, Ls, math.sqrt(rss / n), aic,
                                   corr_max_L=corr, en_limite=lim, avisos=av, curva=curva, tiene_L=tiene_L))
    if res:
        amin = min(m.aic for m in res)
        for m in res:
            m.daic = m.aic - amin
        w = np.array([math.exp(-0.5 * min(m.daic, 1400)) for m in res])
        w /= w.sum()
        for m, wi in zip(res, w):
            m.peso = float(wi)
    return sorted(res, key=lambda m: m.daic)


def ajustar_derivada(pend: Pendientes, T: float) -> Optional[ResultadoModelo]:
    """dP/dt = L + B·(t + t0)^-n ajustado a las pendientes por ventanas (pesos 1/sigma²)."""
    m = np.isfinite(pend.s) & np.isfinite(pend.sig) & (pend.sig > 0)
    if m.sum() < 6:
        return None
    t, s, e = pend.t[m] / 3600.0, pend.s[m] * 3600.0, pend.sig[m] * 3600.0
    Th = T / 3600.0
    smax = max(np.abs(s).max(), 1e-30)

    def f(x, L, B, t0, n):
        return L + B * (x + t0) ** (-n)

    lb, ub = [0, 0, 0, 0.2], [np.inf, np.inf, 20 * Th, 6.0]
    rng = np.random.default_rng(1)
    mejor = None
    for _ in range(16):
        x0 = [smax * rng.uniform(0, 0.5), smax * rng.uniform(0.1, 10) * Th ** 1.0,
              10 ** rng.uniform(math.log10(Th * 1e-4), math.log10(Th * 5)), rng.uniform(0.5, 2.5)]
        try:
            with np.errstate(all="ignore"):
                r = least_squares(lambda x: (f(t, *x) - s) / e, x0, bounds=(lb, ub),
                                  x_scale=[smax, smax * Th, Th, 1.0], max_nfev=4000)
        except Exception:
            continue
        if np.all(np.isfinite(r.fun)) and (mejor is None or r.cost < mejor.cost):
            mejor = r
    if mejor is None:
        return None
    n, k = len(t), 4
    chi2r = 2 * mejor.cost / max(n - k, 1)
    try:
        cov = np.linalg.pinv(mejor.jac.T @ mejor.jac) * max(chi2r, 1.0)
        sig = np.sqrt(np.clip(np.diag(cov), 0, None))
        d = np.sqrt(np.clip(np.diag(cov), 1e-300, None))
        with np.errstate(all="ignore"):
            cc = np.clip(cov[0] / (d[0] * d), -1.0, 1.0)
        cc[np.diag(cov) <= 0] = 0
        corr = float(np.nanmax(np.abs(np.delete(cc, 0))))
    except Exception:
        sig = np.full(4, np.nan)
        corr = math.nan
    L, Ls = mejor.x[0] / 3600.0, sig[0] / 3600.0
    av = []
    if L - 2 * Ls <= 0:
        av.append(Msg("mod_L0"))
    if corr > 0.95:
        av.append(Msg("mod_corr_des", r=corr))
    lim = [nm for nm, v, lo, hi in zip(["L", "B", "t0", "n"], mejor.x, lb, ub)
           if nm != "L" and (v >= 0.999 * hi or (lo > 0 and v <= 1.001 * lo))]
    if lim:
        av.append(Msg("mod_lim", p=", ".join(lim)))
    tf = np.logspace(math.log10(t.min()), math.log10(Th), 200)
    return ResultadoModelo("dP/dt = L + B·(t+t0)^-n", dict(zip(["L", "B", "t0", "n"], mejor.x)),
                           dict(zip(["L", "B", "t0", "n"], sig)), L, Ls, math.sqrt(chi2r), math.nan,
                           corr_max_L=corr, avisos=av, curva=(tf * 3600.0, f(tf, *mejor.x) / 3600.0))


# =============================================================================
# 7. ANÁLISIS COMPLETO
# =============================================================================
@dataclass
class Criterio:
    volumen_L: Optional[float] = None
    incert_volumen: float = 0.10       # fracción
    q_admisible: Optional[float] = None  # mbar·L/s
    area_cm2: Optional[float] = None     # superficie interna expuesta al vacío


@dataclass
class Resultado:
    version: str
    fichero: str
    sha256: str
    sensor: str
    sensor_ref: Optional[str]
    unidad: str
    t_cierre: np.datetime64
    t_fin: np.datetime64
    motivo_fin: str
    cierre_auto: bool
    cierre_confirmado_ref: bool
    duracion_s: float
    config: Dict
    # datos usados
    t: np.ndarray            # s desde el cierre (tras exclusión)
    p: np.ndarray            # mbar (corregida)
    p_bruta: np.ndarray      # mbar sin corregir
    t_todo: np.ndarray       # s desde cierre, ventana completa (sin exclusión)
    p_todo: np.ndarray
    escalones: List[Escalon]
    n_picos: int
    # resultados sin modelo
    pend: Pendientes
    s_final: float
    s_final_sig: float
    ventana_final: Tuple[float, float]
    cota_L: float            # mbar/s (2 sigma)
    beta: float
    beta_sig: float
    n_beta: int
    n_neg: int
    clasificacion: str
    estacionario: bool
    explicacion: str
    # modelos
    derivada: Optional[ResultadoModelo]
    modelos: List[ResultadoModelo]
    L_estimada: Optional[Tuple[float, float, str]]  # (L, sigma, origen) o None si no separable
    # criterio
    criterio: Criterio
    Q_cota: Optional[float]
    Q_estimada: Optional[Tuple[float, float]]
    veredicto: str
    veredicto_motivo: str
    fraccion_pirani: float
    temperaturas: Dict[str, Tuple[float, float]]
    avisos: List[str]
    recomendaciones: List[str]
    # carga de gas por unidad de superficie al final del ensayo (si hay V y A):
    # (q, sigma, cota) en mbar·L·s^-1·cm^-2. 1 mbar·L·s^-1·cm^-2 = 1e3 Pa·m^3·s^-1·m^-2
    carga_especifica: Optional[Tuple[float, float, float]] = None


def analizar(reg: Registro, sensor: str, unidad: str = "mbar",
             i0: Optional[int] = None, i1: Optional[int] = None,
             sensor_ref: Optional[str] = None, criterio: Optional[Criterio] = None,
             config: Optional[Dict] = None, temperaturas: Optional[Registro] = None,
             con_modelos: bool = True, ventana_detectada: Optional[Ventana] = None) -> Resultado:
    """Análisis completo de un ensayo de subida de presión.

    i0/i1: índices de la ventana (None = detección automática). Si la ventana
    viene de una detección previa (p.ej. la propuesta en la interfaz), pásela
    en `ventana_detectada` para que el informe lo refleje correctamente."""
    cfg = dict(CONFIG_DEFECTO)
    if config:
        cfg.update(config)
    crit = criterio or Criterio()
    f = UNIDADES[unidad]
    t_abs = reg.segundos
    P = reg.columnas[sensor] * f
    R = reg.columnas[sensor_ref] * f if sensor_ref else None
    avisos = list(reg.avisos) + comprobar_unidades(reg, unidad)

    auto = i0 is None
    confirmado = False
    motivo_fin = "seleccionado por el usuario"
    if i0 is None:
        v = detectar_ensayo(t_abs, P, R)
        if v is None:
            raise ValueError("No se ha detectado ningún cierre de válvula (subida brusca y sostenida > 1 h). "
                             "Seleccione la ventana manualmente sobre la gráfica.")
        i0, i1d, confirmado, motivo_fin = v.i0, v.i1, v.confirmado_ref, v.motivo_fin
        if i1 is None:
            i1 = i1d
    elif ventana_detectada is not None and ventana_detectada.i0 == i0 and ventana_detectada.i1 == i1:
        auto, confirmado, motivo_fin = True, ventana_detectada.confirmado_ref, ventana_detectada.motivo_fin
    if i1 is None:
        i1, motivo_fin = detectar_final(t_abs, P, i0)
    if i1 - i0 < 10:
        raise ValueError("La ventana seleccionada tiene muy pocos puntos.")
    if sensor_ref and auto and not confirmado:
        avisos.append(Msg("ref_no_confirma"))

    sl = slice(i0, i1 + 1)
    t = t_abs[sl] - t_abs[i0]
    p = P[sl].copy()
    ok = np.isfinite(p) & (p > 0)
    t, p = t[ok], p[ok]
    n_picos = 0
    if cfg["eliminar_picos"] and len(p) > 10:
        m = quitar_picos(t, p)
        n_picos = int((~m).sum())
        t, p = t[m], p[m]
    p_bruta = p.copy()
    escalones: List[Escalon] = []
    if cfg["corregir_escalon"]:
        escalones = detectar_escalones(t, p, reg.digitos, tuple(cfg["banda_escalon"]))
        p = corregir_escalones(t, p, escalones)
    t_todo, p_todo = t.copy(), p.copy()
    excl = cfg["excluir_inicio_min"] * 60.0
    m = t >= excl
    if m.sum() < 10:
        raise ValueError("Tras excluir el transitorio inicial quedan muy pocos puntos.")
    t, p = t[m], p[m]
    T = float(t_todo[-1])
    if T < 12 * 3600:
        avisos.append(Msg("ensayo_corto", h=T / 3600))

    # --- sin modelo
    pend = pendientes_ventana(t, p, reg.digitos)
    wf = max(cfg["fraccion_final"] * (T - t[0]), cfg["ventana_final_min_h"] * 3600.0)
    wf = min(wf, T - t[0])
    mf = t >= T - wf
    q = float(np.nanmedian(resolucion(p[mf], reg.digitos)))
    s_f, s_sig, _ = regresion_lineal(t[mf], p[mf], q)
    cota = s_f + 2 * s_sig
    beta, beta_sig, n_beta, n_neg = tendencia_beta(pend, T)

    if not np.isfinite(s_f):
        clas, expl = "INDETERMINADO", Msg("exp_nan")
    elif s_f - 2 * s_sig <= 0:
        clas = "SIN SUBIDA SIGNIFICATIVA"
        expl = Msg("exp_sin_subida")
    elif not np.isfinite(beta):
        clas, expl = "INDETERMINADO", Msg("exp_pocas")
    elif beta >= cfg["beta_fuga"] and beta - 2 * beta_sig > cfg["beta_desgas"]:
        clas = "FUGA DOMINANTE"
        expl = Msg("exp_fuga", b=beta, s=2 * beta_sig)
        if beta > 0.3:
            avisos.append(Msg("beta_pos"))
    elif beta <= cfg["beta_desgas"] and beta + 2 * beta_sig < cfg["beta_fuga"]:
        clas = "DESGASIFICACIÓN DOMINANTE"
        expl = Msg("exp_desgas", b=beta, s=2 * beta_sig)
    else:
        clas = "MIXTO / NO CONCLUYENTE"
        expl = Msg("exp_mixto", b=beta, s=2 * beta_sig)
    # dP/dt que AUMENTA de forma significativa durante el ensayo: no estacionario
    estacionario = True
    if len(pend.s) >= 4:
        i_min = 0
        for j in range(1, len(pend.s)):
            if pend.s[j] < pend.s[i_min]:
                i_min = j
                continue
            a, b = pend.s[i_min], pend.s[j]
            if a > 0 and b > 1.5 * a and b - a > 2 * math.hypot(pend.sig[i_min], pend.sig[j]):
                k = int(np.argmax(pend.s[j:])) + j
                estacionario = False
                avisos.append(Msg("no_estac_aumenta", a=a, b=pend.s[k], t1=pend.t[i_min] / 3600, t2=pend.t[k] / 3600))
                break
    # estabilidad antes del cierre: ¿subía la presión con la válvula abierta?
    pre_a = (t_abs >= t_abs[i0] - 24 * 3600) & (t_abs < t_abs[i0] - 23 * 3600) & np.isfinite(P) & (P > 0)
    pre_b = (t_abs >= t_abs[i0] - 3600) & (t_abs < t_abs[i0]) & np.isfinite(P) & (P > 0)
    if pre_a.sum() > 5 and pre_b.sum() > 5:
        ratio_pre = np.median(P[pre_b]) / np.median(P[pre_a])
        if ratio_pre > 2:
            estacionario = False
            avisos.append(Msg("pre_cierre", r=ratio_pre))
    if n_neg and n_beta + n_neg > 0 and n_neg / (n_beta + n_neg) > 0.2:
        avisos.append(Msg("ventanas_neg", n=n_neg))

    # --- modelos
    der = ajustar_derivada(pend, T) if con_modelos else None
    mods = ajustar_modelos(t, p, cfg["tau_max_factor"], cota) if con_modelos else []
    # Estimación de L solo si es robusta: fuga dominante (L ≈ pendiente final) o
    # acuerdo entre el modelo de dP/dt y los modelos P(t) relevantes (peso > 10 %),
    # todos separables y sin parámetros en el límite.
    L_est = None
    def _limpio(mo):
        return mo is not None and mo.tiene_L and not any(
            k in a for a in mo.avisos for k in ("compatible con 0", "no separable", "límite", "inconsistente"))
    if _limpio(der) and der.L - 2 * der.L_sig <= cota:
        relevantes = [mo for mo in mods if mo.peso > 0.10]
        if relevantes and all(_limpio(mo) and abs(mo.L - der.L) <= 2 * math.hypot(mo.L_sig, der.L_sig)
                              for mo in relevantes if mo.tiene_L) and any(mo.tiene_L for mo in relevantes):
            L_est = (der.L, der.L_sig, Msg("lest_modelo"))
    if clas == "FUGA DOMINANTE":
        L_est = (s_f, s_sig, Msg("lest_fuga"))
    if not estacionario:
        L_est = None
        expl = Msg.unir(expl, Msg("atencion_no_estac"))

    # --- Pirani y temperaturas
    frac_pir = float(np.mean(p_todo > cfg["umbral_pirani_mbar"]))
    if frac_pir > 0:
        avisos.append(Msg("pirani", pct=100 * frac_pir, u=cfg["umbral_pirani_mbar"]))
    for e in escalones:
        avisos.append(Msg("escalon", t=e.t_s / 3600, p=e.p_antes, s=e.salto, pct=100 * e.salto / e.p_antes))
    if n_picos:
        avisos.append(Msg("picos", n=n_picos))
    temps: Dict[str, Tuple[float, float]] = {}
    if temperaturas is not None:
        ta = temperaturas.tiempo
        mt = (ta >= reg.tiempo[i0]) & (ta <= reg.tiempo[i1])
        for c in temperaturas.columnas:
            v = temperaturas.columnas[c][mt]
            v = v[np.isfinite(v)]
            if len(v):
                temps[c] = (float(v.min()), float(v.max()))
                if v.max() - v.min() > cfg["umbral_temp_K"]:
                    avisos.append(Msg("temp_varia", c=c, d=v.max() - v.min()))
        if not temps:
            avisos.append(Msg("temp_no_cubre"))

    # --- criterio
    Q_cota = Q_est = None
    ver, ver_mot = "SIN CRITERIO", Msg("ver_sin")
    if crit.volumen_L:
        V, dV = crit.volumen_L, crit.incert_volumen
        Q_cota = cota * V * (1 + dV)
        if L_est is not None:
            Q_est = (L_est[0] * V, math.hypot(L_est[1] * V, L_est[0] * V * dV))
        if crit.q_admisible:
            Qa = crit.q_admisible
            s_inf = s_f - 2 * s_sig
            if Q_cota <= Qa:
                ver = "APTO"
                ver_mot = Msg("ver_apto", q=Q_cota, qa=Qa)
            elif clas == "FUGA DOMINANTE" and estacionario and s_inf * V * (1 - dV) > Qa:
                ver = "NO APTO"
                ver_mot = Msg("ver_noapto_fuga", q=s_inf * V * (1 - dV), qa=Qa)
            elif Q_est is not None and Q_est[0] - 2 * Q_est[1] > Qa:
                ver = "NO APTO"
                ver_mot = Msg("ver_noapto_est", q=Q_est[0], s=2 * Q_est[1], qa=Qa)
            else:
                ver = "NO CONCLUYENTE"
                ver_mot = Msg("ver_nc", q=Q_cota, qa=Qa)

    rec = []
    if ver == "NO CONCLUYENTE" or clas in ("MIXTO / NO CONCLUYENTE", "DESGASIFICACIÓN DOMINANTE"):
        rec.append(Msg("rec_repetir"))
        rec.append(Msg("rec_prolongar"))
    if not estacionario:
        rec.append(Msg("rec_estabilizar"))
    if (clas == "FUGA DOMINANTE" and estacionario) or ver == "NO APTO":
        rec.append(Msg("rec_helio"))
    if frac_pir > 0.5:
        rec.append(Msg("rec_pirani"))

    # carga de gas por unidad de superficie: q = V·dP/dt / A. Si la subida final es
    # desgasificación, es la tasa de desgasificación específica; si hay fuga, una
    # cota superior de ella (idea tomada de la rutina MATLAB del DEPMEC, con las
    # unidades corregidas: allí se dividía dP/dt entre el área sin multiplicar por V).
    carga = None
    if crit.volumen_L and crit.area_cm2 and np.isfinite(s_f):
        V, dV, A = crit.volumen_L, crit.incert_volumen, crit.area_cm2
        q = s_f * V / A
        carga = (float(q), float(math.hypot(s_sig * V / A, q * dV)), float(cota * V * (1 + dV) / A))

    return Resultado(VERSION, reg.ruta, reg.sha256, sensor, sensor_ref, unidad,
                     reg.tiempo[i0], reg.tiempo[i1], motivo_fin, auto, confirmado, T, cfg,
                     t, p, p_bruta, t_todo, p_todo, escalones, n_picos,
                     pend, float(s_f), float(s_sig), (float(T - wf), float(T)), float(cota),
                     beta, beta_sig, n_beta, n_neg, clas, estacionario, expl,
                     der, mods, L_est, crit, Q_cota, Q_est, ver, ver_mot, frac_pir, temps, avisos, rec,
                     carga)


# =============================================================================
# 8. COMPARACIÓN DE ENSAYOS REPETIDOS
# =============================================================================
@dataclass
class Comparacion:
    etiquetas: List[str]
    tiempos_h: np.ndarray
    ratios: List[np.ndarray]   # dP/dt_i / dP/dt_0 en tiempos comunes
    ratio_medio: List[float]
    conclusion: str
    cota_L: float


def comparar(resultados: Sequence[Resultado], etiquetas: Sequence[str]) -> Comparacion:
    """Compara dP/dt a igual tiempo desde el cierre entre ensayos repetidos."""
    if len(resultados) < 2:
        raise ValueError("Se necesitan al menos dos ensayos.")
    base = resultados[0].pend
    t_lo = max(r.pend.t.min() for r in resultados if len(r.pend.t))
    t_hi = min(r.pend.t.max() for r in resultados if len(r.pend.t))
    if t_hi <= t_lo:
        raise ValueError("Los ensayos no tienen intervalos de tiempo comunes.")
    tc = np.logspace(math.log10(t_lo), math.log10(t_hi), 12)

    def interp(pd: Pendientes):
        m = pd.s > 0
        return 10 ** np.interp(np.log10(tc), np.log10(pd.t[m]), np.log10(pd.s[m]))
    s0 = interp(base)
    ratios, medios = [], []
    for r in resultados[1:]:
        rr = interp(r.pend) / s0
        ratios.append(rr)
        medios.append(float(np.exp(np.mean(np.log(rr[len(rr) // 2:])))))
    cota = min(r.cota_L for r in resultados)
    ult = medios[-1]
    if 0.8 <= ult <= 1.25:
        concl = Msg("comp_fuga", r=ult)
    elif ult < 0.8:
        concl = Msg("comp_desgas", r=ult, c=cota)
    else:
        concl = Msg("comp_aumenta", r=ult)
    return Comparacion(list(etiquetas), tc / 3600.0, ratios, medios, concl, cota)


# =============================================================================
# 9. TEXTO DE RESULTADOS
# =============================================================================
def fmt(x: Optional[float], u: str = "", d: int = 2) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    if abs(x) < 1e-25:
        return f"0 {u}".strip()
    return f"{x:.{d}e} {u}".strip()


def resumen_texto(r: Resultado) -> str:
    L = []
    L.append(f"ANALIZADOR DE FUGAS DEPMEC v{r.version}")
    L.append(f"Fichero: {r.fichero.replace(chr(92), '/').split('/')[-1]}   SHA-256: {r.sha256[:16]}…")
    L.append(f"Sensor: {r.sensor}" + (f"   Ref. turbo: {r.sensor_ref}" if r.sensor_ref else ""))
    L.append(f"Cierre: {str(r.t_cierre).replace('T', ' ')} ({'automático' if r.cierre_auto else 'manual'}"
             + (", confirmado por sensor turbo" if r.cierre_confirmado_ref else "") + ")")
    L.append(f"Fin:    {str(r.t_fin).replace('T', ' ')} ({r.motivo_fin})   Duración: {r.duracion_s / 3600:.2f} h")
    L.append("")
    L.append(f"DIAGNÓSTICO: {r.clasificacion}")
    L.append("  " + r.explicacion)
    L.append("")
    L.append(f"dP/dt final ({r.ventana_final[0] / 3600:.1f}-{r.ventana_final[1] / 3600:.1f} h): "
             f"{fmt(r.s_final, 'mbar/s')} ± {fmt(2 * r.s_final_sig)} (2σ)")
    L.append(f"COTA SUPERIOR de la fuga:  L ≤ {fmt(r.cota_L, 'mbar/s')}  ({fmt(r.cota_L * 3600, 'mbar/h')})")
    if r.L_estimada:
        L.append(f"Fuga estimada: {fmt(r.L_estimada[0], 'mbar/s')} ± {fmt(2 * r.L_estimada[1])} (2σ)  [{r.L_estimada[2]}]")
    else:
        L.append("Fuga estimada: no separable de la desgasificación con estos datos (use la cota superior).")
    if r.criterio.volumen_L:
        L.append(f"Volumen: {r.criterio.volumen_L:g} L ± {100 * r.criterio.incert_volumen:.0f} %")
        L.append(f"  Q ≤ {fmt(r.Q_cota, 'mbar·L/s')}" + (f"   Q estimado = {fmt(r.Q_estimada[0])} ± {fmt(2 * r.Q_estimada[1])}" if r.Q_estimada else ""))
    if r.carga_especifica:
        q, sq, qc = r.carga_especifica
        L.append(f"Superficie interna: {r.criterio.area_cm2:g} cm²")
        L.append(f"  Carga de gas específica al final (V·dP/dt/A): {fmt(q)} ± {fmt(2 * sq)} mbar·L·s⁻¹·cm⁻² "
                 f"(≤ {fmt(qc)}; = {fmt(q * 1e3)} Pa·m³·s⁻¹·m⁻²)")
        L.append("  Si la subida final es desgasificación, es la tasa de desgasificación específica; "
                 "si hay fuga, una cota superior de ella.")
    L.append(f"VEREDICTO: {r.veredicto}  {('— ' + r.veredicto_motivo) if r.veredicto != 'SIN CRITERIO' else ''}")
    if r.avisos:
        L.append("")
        L.append("AVISOS:")
        L += ["  • " + a for a in r.avisos]
    if r.recomendaciones:
        L.append("")
        L.append("RECOMENDACIONES:")
        L += ["  • " + a for a in r.recomendaciones]
    return "\n".join(L)
