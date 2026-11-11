# -*- coding: utf-8 -*-
"""Gráficas del Analizador de Fugas V3 (compartidas por la ventana y el informe PDF).
Todas aceptan lang="es" | "en" para los textos."""
from __future__ import annotations

from typing import Optional, Sequence

import matplotlib.dates as mdates
import numpy as np

import nucleo_fugas as nf
from textos import et, tr

# Paleta (validada para daltonismo; los colores de estado van siempre con texto)
AZUL, NARANJA, AQUA, AMARILLO, VIOLETA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"
SERIES = [AZUL, NARANJA, AQUA, AMARILLO, "#e87ba4", "#008300", VIOLETA, "#e34948"]
TINTA, TINTA2, GRIS, REJILLA = "#0b0b0b", "#52514e", "#a9a8a2", "#e4e3df"
ESTADO = {"APTO": "#0ca30c", "NO APTO": "#d03b3b", "NO CONCLUYENTE": "#fab219", "SIN CRITERIO": "#d9d8d3"}


def estilo(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#bdbcb6")
    ax.tick_params(colors=TINTA2, labelsize=8.5)
    ax.grid(True, which="major", color=REJILLA, lw=0.8)
    ax.grid(True, which="minor", color=REJILLA, lw=0.4, alpha=0.6)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(TINTA2)
    ax.yaxis.label.set_color(TINTA2)


def _fechas(tiempo):
    return mdates.date2num(tiempo.astype("datetime64[ms]").astype(object))


def dibujar_datos(fig, reg: nf.Registro, unidad: str, sensor: Optional[str], ref: Optional[str],
                  res: Optional[nf.Resultado] = None, temps: Optional[nf.Registro] = None,
                  ventana=None, lang: str = "es", otras_ventanas=()):
    """Serie completa (escala log) con la ventana del ensayo resaltada.
    `otras_ventanas`: otros ensayos del mismo fichero (se marcan más tenues).
    Devuelve el eje de presión (para el selector de ventana)."""
    fig.clear()
    if temps is not None:
        gs = fig.add_gridspec(2, 1, height_ratios=[3, 1.2], hspace=0.08)
        ax = fig.add_subplot(gs[0])
        axt = fig.add_subplot(gs[1], sharex=ax)
    else:
        ax = fig.add_subplot(111)
        axt = None
    f = nf.UNIDADES[unidad]
    x = _fechas(reg.tiempo)
    cols = reg.columnas_presion()
    for i, c in enumerate(cols):
        y = reg.columnas[c] * f
        y = np.where(y > 0, y, np.nan)
        papel = et("g_camara", lang) if c == sensor else (et("g_turbo", lang) if c == ref else "")
        canal = reg.etiquetas.get(c, "")
        ax.plot(x, y, color=SERIES[i % len(SERIES)], lw=1.2 if c == sensor else 0.9,
                alpha=1.0 if c in (sensor, ref) else 0.6, label=f"{c}{(' · ' + canal) if canal else ''}{papel}")
    ax.set_yscale("log")
    ax.set_ylabel(et("g_presion", lang))
    for a, b in otras_ventanas:
        ax.axvspan(_fechas(np.array([a]))[0], _fechas(np.array([b]))[0], color=GRIS, alpha=0.12, lw=0)
    if ventana is not None:
        a, b = ventana
        xa, xb = _fechas(np.array([a]))[0], _fechas(np.array([b]))[0]
        ax.axvspan(xa, xb, color=AZUL, alpha=0.10, lw=0)
        ax.axvline(xa, color=AZUL, lw=1.2, ls="--")
        ax.text(xa, 0.03, " " + et("g_cierre", lang), transform=ax.get_xaxis_transform(), rotation=90,
                va="bottom", ha="left", fontsize=8, color=TINTA2)
    estilo(ax)
    leg = ax.legend(loc="upper left", fontsize=8, frameon=False)
    for t in leg.get_texts():
        t.set_color(TINTA)
    loc = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    if axt is not None:
        xt = _fechas(temps.tiempo)
        for i, c in enumerate(temps.columnas):
            axt.plot(xt, temps.columnas[c], lw=1.0, color=SERIES[(i + 2) % len(SERIES)], label=c)
        axt.set_ylabel(et("g_temperatura", lang))
        estilo(axt)
        if len(temps.columnas) <= 8:
            axt.legend(loc="upper left", fontsize=7.5, frameon=False, ncol=4)
        if ventana is not None:
            axt.axvspan(_fechas(np.array([ventana[0]]))[0], _fechas(np.array([ventana[1]]))[0],
                        color=AZUL, alpha=0.10, lw=0)
        ax.tick_params(labelbottom=False)
    if len(x) > 1:
        ax.set_xlim(x[0], x[-1])
    titulo = reg.meta.get("Test Purpose", "")
    ax.set_title(titulo, loc="left", fontsize=10, color=TINTA)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.12)
    return ax


def dibujar_subida(fig, r: nf.Resultado, lang: str = "es"):
    """P(t) en la ventana: datos, corrección de escalón, ventana final y modelos."""
    fig.clear()
    ax = fig.add_subplot(111)
    th = r.t_todo / 3600.0
    if r.escalones:
        ax.plot(th, r.p_bruta, color=GRIS, lw=1.0, label=et("g_original", lang))
    ax.plot(th, r.p_todo, color=AZUL, lw=1.6,
            label=et("g_p_camara", lang) + (et("g_corregido", lang) if r.escalones else ""))
    excl = r.config["excluir_inicio_min"] / 60.0
    if excl > 0:
        ax.axvspan(0, excl, color=GRIS, alpha=0.18, lw=0)
        ax.text(excl, 0.02, et("g_transitorio", lang), transform=ax.get_xaxis_transform(), fontsize=7.5, color=TINTA2)
    a, b = r.ventana_final
    ax.axvspan(a / 3600, b / 3600, color=AZUL, alpha=0.08, lw=0)
    m = r.t >= a
    if m.any() and np.isfinite(r.s_final):
        tm = r.t[m]
        pm = np.interp(tm.mean(), r.t[m], r.p[m])
        ax.plot(tm / 3600, pm + r.s_final * (tm - tm.mean()), color=NARANJA, lw=2.2,
                label=et("g_pendiente", lang, x=r.s_final))
    mods = [mo for mo in r.modelos if mo.curva is not None][:2]
    for mo, c in zip(mods, (AQUA, VIOLETA)):
        tc, pc = mo.curva
        ax.plot(tc / 3600, pc, color=c, lw=1.4, ls="--", label=et("g_modelo", lang, n=tr(mo.nombre, lang), d=mo.daic))
    for e in r.escalones:
        ax.axvline(e.t_s / 3600, color=AMARILLO, lw=1.0, ls=":")
    ax.set_xlabel(et("g_horas", lang))
    ax.set_ylabel(et("g_presion", lang))
    estilo(ax)
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    ax.set_title(et("g_subida", lang), loc="left", fontsize=10, color=TINTA)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.92, bottom=0.11)


def dibujar_dpdt(fig, r: nf.Resultado, lang: str = "es"):
    """dP/dt en ventanas (log-log): la clave para distinguir fuga de desgasificación."""
    fig.clear()
    ax = fig.add_subplot(111)
    pd = r.pend
    pos = pd.s > 0
    if pos.any():
        ax.errorbar(pd.t[pos] / 3600, pd.s[pos], yerr=2 * pd.sig[pos], fmt="o-", color=AZUL, ms=4.5,
                    lw=1.6, elinewidth=0.9, capsize=2, label=et("g_dpdt_med", lang))
    if (~pos).any():
        ax.plot(pd.t[~pos] / 3600, np.full((~pos).sum(), max(pd.s[pos].min() if pos.any() else 1e-12, 1e-15)),
                "v", color=NARANJA, ms=6, label=et("g_neg", lang))
    if np.isfinite(r.cota_L) and r.cota_L > 0:
        ax.axhline(r.cota_L, color=NARANJA, lw=2.0, ls="--", label=et("g_cota", lang, x=r.cota_L))
    if r.L_estimada:
        L, s, _ = r.L_estimada
        ax.axhspan(max(L - 2 * s, 1e-30), L + 2 * s, color=AQUA, alpha=0.25, lw=0,
                   label=et("g_fuga_est", lang, x=L, s=2 * s))
    limpio = r.derivada is not None and not any(
        k in a for a in r.derivada.avisos for k in ("compatible con 0", "no separable", "límite"))
    if limpio and r.derivada.curva is not None:
        tc, sc = r.derivada.curva
        ax.plot(tc / 3600, sc, color=VIOLETA, lw=1.2, ls=":", label=et("g_ajuste", lang))
    T = r.duracion_s / 3600
    if np.isfinite(r.beta):
        ax.axvspan(T / 10 ** 0.5, T, color=GRIS, alpha=0.12, lw=0)
        ax.text(T / 10 ** 0.25, 0.97, f"β = {r.beta:.2f}", transform=ax.get_xaxis_transform(),
                ha="center", va="top", fontsize=9, color=TINTA)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(et("g_horas", lang))
    ax.set_ylabel("dP/dt (mbar/s)")
    estilo(ax)
    ax.legend(loc="best", fontsize=8, frameon=False)
    ax.set_title(et("g_velocidad", lang, c=tr(r.clasificacion, lang)), loc="left", fontsize=10, color=TINTA)
    fig.subplots_adjust(left=0.11, right=0.98, top=0.92, bottom=0.11)


def dibujar_comparacion(fig, resultados: Sequence[nf.Resultado], etiquetas: Sequence[str], lang: str = "es"):
    fig.clear()
    ax = fig.add_subplot(111)
    for i, (r, e) in enumerate(zip(resultados, etiquetas)):
        pd = r.pend
        m = pd.s > 0
        ax.errorbar(pd.t[m] / 3600, pd.s[m], yerr=2 * pd.sig[m], fmt="o-", ms=4, lw=1.5, capsize=2,
                    color=SERIES[i % len(SERIES)], label=e)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(et("g_horas", lang))
    ax.set_ylabel("dP/dt (mbar/s)")
    estilo(ax)
    if resultados:
        ax.legend(loc="lower left", fontsize=8, frameon=False)
    ax.set_title(et("g_comp", lang), loc="left", fontsize=10, color=TINTA)
    fig.subplots_adjust(left=0.11, right=0.98, top=0.92, bottom=0.11)
