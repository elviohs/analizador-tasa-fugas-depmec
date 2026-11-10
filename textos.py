# -*- coding: utf-8 -*-
"""Textos traducibles (español / inglés) del Analizador de Fugas V3.

`Msg` es un str (en español, para que todo el código y los tests sigan
funcionando igual) que además recuerda su clave y parámetros para poder
reescribirse en inglés al generar el informe:  tr(msg, "en").
"""
from __future__ import annotations

IDIOMAS = {"es": "Español", "en": "English"}

# --------------------------------------------------------------------------
# Códigos fijos (se comparan como texto en el programa)
# --------------------------------------------------------------------------
CODIGOS = {
    "FUGA DOMINANTE": "LEAK DOMINATED",
    "DESGASIFICACIÓN DOMINANTE": "OUTGASSING DOMINATED",
    "MIXTO / NO CONCLUYENTE": "MIXED / INCONCLUSIVE",
    "SIN SUBIDA SIGNIFICATIVA": "NO SIGNIFICANT RISE",
    "INDETERMINADO": "UNDETERMINED",
    "APTO": "PASS",
    "NO APTO": "FAIL",
    "NO CONCLUYENTE": "INCONCLUSIVE",
    "SIN CRITERIO": "NO CRITERION",
    "venteo": "venting",
    "re-bombeo o apertura de válvula": "re-pumping or valve opening",
    "fin del registro": "end of log",
    "seleccionado por el usuario": "selected by the user",
    "Exponencial + fuga (V2)": "Exponential + leak (V2)",
    "Doble exponencial + fuga": "Double exponential + leak",
    "Potencia + fuga": "Power law + leak",
    "Logarítmico + fuga": "Logarithmic + leak",
    "Exponencial (sin fuga)": "Exponential (no leak)",
    "Potencia (sin fuga)": "Power law (no leak)",
}

# --------------------------------------------------------------------------
# Mensajes con parámetros: clave -> (español, inglés)
# --------------------------------------------------------------------------
MENSAJES = {
    # lectura
    "lec_desordenado": ("Las marcas de tiempo no estaban ordenadas; se han ordenado.",
                        "Timestamps were not in order; they have been sorted."),
    "lec_duplicados": ("{n} filas con marca de tiempo duplicada descartadas.",
                       "{n} rows with duplicated timestamps discarded."),
    "lec_huecos": ("{n} huecos en el registro (> 10 veces el periodo de muestreo de {paso:.0f} s).",
                   "{n} gaps in the log (> 10 times the {paso:.0f} s sampling period)."),
    "lec_no_num": ("{n} valores no numéricos (p.ej. 'Overrange') tratados como ausentes.",
                   "{n} non-numeric values (e.g. 'Overrange') treated as missing."),
    "lec_descartadas": ("{n} líneas sin formato de datos descartadas.",
                        "{n} lines without data format discarded."),
    "uni_max": ("{c}: máximo {mx:.3g} mbar (> 2 bar). ¿Unidad incorrecta? (¿Pa en lugar de mbar?)",
                "{c}: maximum {mx:.3g} mbar (> 2 bar). Wrong unit? (Pa instead of mbar?)"),
    "uni_neg": ("{c}: contiene valores <= 0, que se ignoran.",
                "{c}: contains values <= 0, which are ignored."),
    # análisis
    "ref_no_confirma": ("El sensor del lado turbo no confirma el cierre de la válvula en el punto detectado: revise la ventana.",
                        "The turbo-side gauge does not confirm the valve closure at the detected point: check the test window."),
    "ensayo_corto": ("Ensayo corto ({h:.1f} h). Con menos de 12-24 h la separación fuga/desgasificación es poco fiable.",
                     "Short test ({h:.1f} h). With less than 12-24 h, separating leak from outgassing is unreliable."),
    "exp_nan": ("No se pudo calcular la pendiente final.", "The final slope could not be computed."),
    "exp_sin_subida": ("La presión no sube de forma significativa en la ventana final. La fuga está por debajo de la "
                       "cota superior indicada (limitada por la resolución del registro y la duración).",
                       "Pressure does not rise significantly in the final window. The leak is below the stated upper "
                       "bound (limited by the logging resolution and the test duration)."),
    "exp_pocas": ("Pocas ventanas válidas para evaluar la tendencia de dP/dt.",
                  "Too few valid windows to assess the dP/dt trend."),
    "exp_fuga": ("dP/dt es prácticamente constante al final del ensayo (beta = {b:.2f} ± {s:.2f}). "
                 "La subida final es, en su mayor parte, fuga real.",
                 "dP/dt is practically constant at the end of the test (beta = {b:.2f} ± {s:.2f}). "
                 "The final rise is mostly a real leak."),
    "exp_desgas": ("dP/dt sigue disminuyendo al final del ensayo (beta = {b:.2f} ± {s:.2f}). "
                   "La subida está dominada por desgasificación; la fuga real es menor que la cota superior.",
                   "dP/dt is still decreasing at the end of the test (beta = {b:.2f} ± {s:.2f}). "
                   "The rise is dominated by outgassing; the real leak is smaller than the upper bound."),
    "exp_mixto": ("dP/dt disminuye lentamente (beta = {b:.2f} ± {s:.2f}): fuga y desgasificación contribuyen de "
                  "forma comparable. Use la cota superior o prolongue / repita el ensayo.",
                  "dP/dt decreases slowly (beta = {b:.2f} ± {s:.2f}): leak and outgassing contribute comparably. "
                  "Use the upper bound or extend / repeat the test."),
    "atencion_no_estac": ("ATENCIÓN: el ensayo no es estacionario (ver avisos); el diagnóstico es orientativo y solo "
                          "la cota superior es fiable.",
                          "WARNING: the test is not stationary (see warnings); the diagnosis is indicative and only "
                          "the upper bound is reliable."),
    "beta_pos": ("dP/dt AUMENTA con el tiempo (beta > 0,3): ¿temperatura subiendo o fuga que empeora?",
                 "dP/dt INCREASES with time (beta > 0.3): rising temperature or a worsening leak?"),
    "no_estac_aumenta": ("dP/dt AUMENTA durante el ensayo (de {a:.1e} a {b:.1e} mbar/s entre {t1:.1f} h y {t2:.1f} h): "
                         "el ensayo no es estacionario (¿la temperatura sube? ¿fuga que empeora?). Revise las temperaturas.",
                         "dP/dt INCREASES during the test (from {a:.1e} to {b:.1e} mbar/s between {t1:.1f} h and "
                         "{t2:.1f} h): the test is not stationary (rising temperature? worsening leak?). Check the temperatures."),
    "pre_cierre": ("Antes del cierre la presión subía con la válvula abierta (×{r:.1f} en las 24 h previas): el sistema "
                   "no estaba estabilizado (¿calentándose tras una fase fría?). La desgasificación puede crecer durante el ensayo.",
                   "Before closure the pressure was rising with the valve open (×{r:.1f} over the previous 24 h): the "
                   "system was not stabilised (warming up after a cold phase?). Outgassing may increase during the test."),
    "ventanas_neg": ("{n} ventanas con dP/dt <= 0 al final del ensayo: subida no monótona (¿cambios de temperatura, "
                     "readsorción?). La cota superior puede no ser estricta.",
                     "{n} windows with dP/dt <= 0 at the end of the test: non-monotonic rise (temperature changes, "
                     "re-adsorption?). The upper bound may not be strict."),
    "pirani": ("El {pct:.0f} % de la ventana está por encima de {u:.0e} mbar, donde la galga de rango completo mide con "
               "la Pirani: la lectura depende del tipo de gas (p.ej. vapor de agua) y su incertidumbre es mayor.",
               "{pct:.0f} % of the window is above {u:.0e} mbar, where the full-range gauge measures with the Pirani: "
               "the reading depends on the gas type (e.g. water vapour) and is more uncertain."),
    "escalon": ("Escalón de galga corregido a t = {t:.2f} h (p ≈ {p:.2e} mbar): salto de {s:.2e} mbar ({pct:.0f} %).",
                "Gauge step corrected at t = {t:.2f} h (p ≈ {p:.2e} mbar): jump of {s:.2e} mbar ({pct:.0f} %)."),
    "picos": ("{n} picos aislados eliminados.", "{n} isolated spikes removed."),
    "temp_varia": ("Temperatura {c}: varía {d:.1f} durante el ensayo. La presión del gas y la desgasificación dependen "
                   "de la temperatura: interprete la dP/dt con cuidado.",
                   "Temperature {c}: varies by {d:.1f} during the test. Gas pressure and outgassing depend on "
                   "temperature: interpret dP/dt with care."),
    "temp_no_cubre": ("El fichero de temperaturas no cubre la ventana del ensayo.",
                      "The temperature file does not cover the test window."),
    "lest_modelo": ("dP/dt = L + B·(t+t0)^-n, coherente con los modelos P(t)",
                    "dP/dt = L + B·(t+t0)^-n, consistent with the P(t) models"),
    "lest_fuga": ("pendiente final (fuga dominante)", "final slope (leak dominated)"),
    # veredicto
    "ver_sin": ("No se ha indicado volumen y/o caudal admisible.", "No volume and/or acceptable leak rate given."),
    "ver_apto": ("La cota superior de la fuga ({q:.2e} mbar·L/s) es menor que el admisible ({qa:.2e}).",
                 "The leak upper bound ({q:.2e} mbar·L/s) is below the acceptable value ({qa:.2e})."),
    "ver_noapto_fuga": ("Fuga dominante con caudal mínimo {q:.2e} mbar·L/s > admisible {qa:.2e}.",
                        "Leak dominated, with a minimum leak rate of {q:.2e} mbar·L/s > acceptable {qa:.2e}."),
    "ver_noapto_est": ("La fuga estimada ({q:.2e} ± {s:.2e}) supera el admisible ({qa:.2e}).",
                       "The estimated leak ({q:.2e} ± {s:.2e}) exceeds the acceptable value ({qa:.2e})."),
    "ver_nc": ("La cota superior ({q:.2e}) supera el admisible ({qa:.2e}) pero no se puede atribuir a fuga: parte de "
               "la subida es desgasificación.",
               "The upper bound ({q:.2e}) exceeds the acceptable value ({qa:.2e}) but cannot be attributed to a leak: "
               "part of the rise is outgassing."),
    # recomendaciones
    "rec_repetir": ("Repetir el ensayo tras volver a bombear y comparar dP/dt a igual tiempo desde el cierre (pestaña "
                    "Comparación): si se mantiene es fuga; si baja, desgasificación.",
                    "Repeat the test after pumping down again and compare dP/dt at the same time after closure: if it "
                    "is unchanged it is a leak; if it decreases, outgassing."),
    "rec_prolongar": ("Prolongar el ensayo hasta que dP/dt se estabilice o bombear más tiempo (o en caliente) antes de cerrar.",
                      "Extend the test until dP/dt stabilises, or pump longer (or while baking) before closing the valve."),
    "rec_estabilizar": ("Repetir el ensayo con el criostato estabilizado en temperatura (y cargar el fichero de "
                        "temperaturas) para que el diagnóstico sea concluyente.",
                        "Repeat the test with the cryostat temperature-stabilised (and load the temperature file) to "
                        "obtain a conclusive diagnosis."),
    "rec_helio": ("Localizar la fuga con detector de helio.", "Locate the leak with a helium leak detector."),
    "rec_pirani": ("Gran parte del ensayo está en zona Pirani: si se busca precisión, considere un medidor independiente "
                   "del gas (capacitivo) para la subida.",
                   "Most of the test is in the Pirani range: for higher accuracy, consider a gas-independent "
                   "(capacitance) gauge for the rise."),
    # modelos
    "mod_L0": ("L compatible con 0", "L compatible with 0"),
    "mod_corr": ("L muy correlada con otro parámetro (|r|={r:.2f}): no separable",
                 "L strongly correlated with another parameter (|r|={r:.2f}): not separable"),
    "mod_corr_des": ("L muy correlada con la desgasificación (|r|={r:.2f}): no separable",
                     "L strongly correlated with outgassing (|r|={r:.2f}): not separable"),
    "mod_incons": ("L mayor que la subida medida al final: inconsistente",
                   "L larger than the measured final rise: inconsistent"),
    "mod_lim": ("parámetros en el límite: {p}", "parameters at their bounds: {p}"),
    # comparación
    "comp_fuga": ("dP/dt se repite entre ensayos (ratio ≈ {r:.2f}) a igual tiempo desde el cierre: la subida es "
                  "mayoritariamente FUGA REAL.",
                  "dP/dt repeats between tests (ratio ≈ {r:.2f}) at the same time after closure: the rise is mainly "
                  "a REAL LEAK."),
    "comp_desgas": ("dP/dt baja entre ensayos (ratio ≈ {r:.2f}): la subida está dominada por DESGASIFICACIÓN, que "
                    "disminuye con el bombeo. La fuga es como máximo {c:.2e} mbar/s (menor cota de los ensayos).",
                    "dP/dt decreases between tests (ratio ≈ {r:.2f}): the rise is dominated by OUTGASSING, which "
                    "decreases with pumping. The leak is at most {c:.2e} mbar/s (lowest bound of the tests)."),
    "comp_aumenta": ("dP/dt aumenta entre ensayos (ratio ≈ {r:.2f}): revise condiciones (temperatura, exposición a "
                     "aire, fuga que empeora).",
                     "dP/dt increases between tests (ratio ≈ {r:.2f}): check conditions (temperature, air exposure, "
                     "worsening leak)."),
}


def _render(clave, lang, params):
    es, en = MENSAJES[clave]
    plantilla = en if lang == "en" else es
    p = {k: tr(v, lang) for k, v in params.items()}
    return plantilla.format(**p)


class Msg(str):
    """Texto traducible que se comporta como str en español."""

    def __new__(cls, clave, **params):
        obj = super().__new__(cls, _render(clave, "es", params))
        obj.clave, obj.params, obj.partes = clave, params, None
        return obj

    @classmethod
    def unir(cls, *msgs, sep=" "):
        obj = str.__new__(cls, sep.join(str(m) for m in msgs))
        obj.clave, obj.params, obj.partes = None, {}, (list(msgs), sep)
        return obj

    def tr(self, lang="es"):
        if self.partes is not None:
            msgs, sep = self.partes
            return sep.join(tr(m, lang) for m in msgs)
        return _render(self.clave, lang, self.params)

    def __reduce__(self):  # permite copiar/serializar
        return (str, (str(self),))


def tr(x, lang="es"):
    """Traduce un Msg, un código fijo o deja el texto como está."""
    if isinstance(x, Msg):
        return x.tr(lang)
    if isinstance(x, str) and lang == "en":
        return CODIGOS.get(x, x)
    return x


# --------------------------------------------------------------------------
# Etiquetas del informe y de las gráficas
# --------------------------------------------------------------------------
ETIQ = {
    "titulo": ("Informe de ensayo de subida de presión (tasa de fuga)", "Pressure rise test report (leak rate)"),
    "titulo_multi": ("Informe de ensayos de subida de presión (tasa de fuga)", "Pressure rise tests report (leak rate)"),
    "generado": ("Generado el {f} · Analizador de fugas DEPMEC v{v}", "Generated on {f} · DEPMEC leak analyser v{v}"),
    "pie": ("Línea de Vacío y Criogenia · Dpto. de Mecánica · IAC — Analizador de fugas v{v} — página {p}/{{nb}}",
            "Vacuum and Cryogenics Line · Mechanical Dept. · IAC — Leak analyser v{v} — page {p}/{{nb}}"),
    "veredicto": ("VEREDICTO", "VERDICT"),
    "resumen": ("Resumen de ensayos", "Summary of tests"),
    "ensayo": ("Ensayo", "Test"),
    "resultados": ("Resultados", "Results"),
    "dpdt_final": ("dP/dt en la ventana final", "dP/dt in the final window"),
    "entre": ("entre {a:.1f} h y {b:.1f} h", "between {a:.1f} h and {b:.1f} h"),
    "cota": ("Cota superior de la fuga", "Leak upper bound"),
    "tendencia": ("Tendencia de dP/dt (β)", "dP/dt trend (β)"),
    "tendencia_nota": ("[≈0: fuga constante; ≈ −1 o menor: desgasificación]", "[≈0: constant leak; ≈ −1 or lower: outgassing]"),
    "fuga_est": ("Fuga estimada", "Estimated leak"),
    "no_separable": ("No separable de la desgasificación con estos datos: se informa la cota superior.",
                     "Not separable from outgassing with these data: the upper bound is reported."),
    "volumen": ("Volumen", "Volume"),
    "q_cota": ("Caudal de fuga (cota)", "Leak rate (upper bound)"),
    "q_est": ("Caudal de fuga estimado", "Estimated leak rate"),
    "q_adm": ("Caudal admisible", "Acceptable leak rate"),
    "area": ("Superficie interna", "Internal surface area"),
    "q_esp": ("Carga de gas específica al final", "Specific gas load at the end"),
    "q_esp_txt": ("V·dP/dt/A = {q} ± {s} mbar·L·s⁻¹·cm⁻² (2σ; cota {c}) = {qsi} Pa·m³·s⁻¹·m⁻². Si la subida final "
                  "es desgasificación, es la tasa de desgasificación específica; si hay fuga, una cota superior de ella.",
                  "V·dP/dt/A = {q} ± {s} mbar·L·s⁻¹·cm⁻² (2σ; bound {c}) = {qsi} Pa·m³·s⁻¹·m⁻². If the final rise is "
                  "outgassing, this is the specific outgassing rate; if there is a leak, an upper bound of it."),
    "identificacion": ("Identificación del ensayo", "Test identification"),
    "fichero": ("Fichero", "File"),
    "sistema": ("Sistema", "System"),
    "responsable": ("Responsable", "Responsible"),
    "objetivo": ("Objetivo", "Purpose"),
    "inicio_reg": ("Inicio del registro", "Log start"),
    "sensor_cam": ("Sensor de cámara", "Chamber gauge"),
    "unidad": ("unidad", "unit"),
    "sensor_ref": ("Sensor lado turbo", "Turbo-side gauge"),
    "cierre": ("Cierre de válvula", "Valve closure"),
    "auto": ("detectado automáticamente", "detected automatically"),
    "manual": ("seleccionado manualmente", "selected manually"),
    "confirmado": (", confirmado por el sensor del lado turbo", ", confirmed by the turbo-side gauge"),
    "fin": ("Fin del ensayo", "End of test"),
    "duracion": ("Duración analizada", "Analysed duration"),
    "preproceso": ("Preprocesado", "Preprocessing"),
    "preproceso_txt": ("Transitorio excluido: {e:g} min · Ventana final: {f:.0f} % (mín. {m:g} h) · Corrección de "
                       "escalón: {c} · Eliminación de picos: {p} ({n} eliminados)",
                       "Excluded transient: {e:g} min · Final window: {f:.0f} % (min. {m:g} h) · Step correction: {c} · "
                       "Spike removal: {p} ({n} removed)"),
    "si": ("sí", "yes"), "no": ("no", "no"),
    "temps": ("Temperaturas (mín–máx)", "Temperatures (min–max)"),
    "observaciones": ("Observaciones", "Remarks"),
    "avisos": ("Avisos", "Warnings"),
    "recomendaciones": ("Recomendaciones", "Recommendations"),
    "graficas": ("Gráficas", "Plots"),
    "modelos": ("Modelos (estimación secundaria)", "Models (secondary estimate)"),
    "modelos_txt": ("Ajustes de P(t) por mínimos cuadrados con parámetros escalados, varios puntos de partida y "
                    "τ ≤ {t:g}·T. ΔAIC < 2: modelos equivalentes. Una L con IC que incluye 0, muy correlada con la "
                    "desgasificación o mayor que la cota superior no se usa como medida de fuga.",
                    "Least-squares P(t) fits with scaled parameters, multiple starting points and τ ≤ {t:g}·T. "
                    "ΔAIC < 2: equivalent models. An L whose CI includes 0, strongly correlated with outgassing or "
                    "larger than the upper bound is not used as a leak measurement."),
    "col_modelo": ("Modelo", "Model"), "col_peso": ("Peso", "Weight"), "col_obs": ("Observaciones", "Remarks"),
    "sin_fuga": ("(sin fuga)", "(no leak)"),
    "comparacion": ("Comparación de ensayos repetidos", "Comparison of repeated tests"),
    "comparacion_nota": ("Solo tiene sentido entre ensayos repetidos del mismo sistema. Ratio = dP/dt del ensayo / "
                         "dP/dt del primero, a igual tiempo desde el cierre.",
                         "Only meaningful between repeated tests of the same system. Ratio = dP/dt of the test / "
                         "dP/dt of the first one, at the same time after closure."),
    "ratio": ("Ratio dP/dt", "dP/dt ratio"),
    "metodo": ("Método y limitaciones", "Method and limitations"),
    "metodo_txt": (
        "dP/dt = fuga + desgasificación. La desgasificación decrece con el tiempo y no es negativa, por lo que la "
        "pendiente al final del ensayo es una cota superior de la fuga (salvo readsorción o descensos de temperatura, "
        "que se avisan). El exponente β describe cómo evoluciona dP/dt al final: una fuga mantiene dP/dt constante "
        "(β≈0); la desgasificación la hace disminuir (β≈−1 en metales). Con una sola curva fuga y desgasificación "
        "suelen no ser separables; el método más fiable es repetir el ensayo tras bombear de nuevo y comparar dP/dt a "
        "igual tiempo desde el cierre, y localizar con helio. Por encima de ~1e-2 mbar las galgas de rango completo "
        "miden con la Pirani, cuya lectura depende del gas. Referencias: Leybold, «Pressure rise and drop tests»; "
        "Pfeiffer Vacuum, «Pressure Decay Methods» (2026); EN 13184 (método de cambio de presión).",
        "dP/dt = leak + outgassing. Outgassing decreases with time and is never negative, so the slope at the end of "
        "the test is an upper bound of the leak (except for re-adsorption or temperature drops, which are flagged). "
        "The exponent β describes how dP/dt evolves at the end: a leak keeps dP/dt constant (β≈0); outgassing makes "
        "it decrease (β≈−1 for metals). With a single curve, leak and outgassing are often not separable; the most "
        "reliable method is to repeat the test after pumping down again, compare dP/dt at the same time after "
        "closure, and locate leaks with helium. Above ~1e-2 mbar full-range gauges measure with the Pirani, whose "
        "reading depends on the gas. References: Leybold, 'Pressure rise and drop tests'; Pfeiffer Vacuum, "
        "'Pressure Decay Methods' (2026); EN 13184 (pressure change method)."),
    "col_cierre": ("Cierre", "Closure"), "col_dur": ("Dur. (h)", "Dur. (h)"),
    "col_diag": ("Diagnóstico", "Diagnosis"), "col_cota": ("Fuga ≤ (mbar/s)", "Leak ≤ (mbar/s)"),
    "col_q": ("Q ≤ (mbar·L/s)", "Q ≤ (mbar·L/s)"), "col_ver": ("Veredicto", "Verdict"),
    "obs_generales": ("Observaciones generales", "General remarks"),
    "comp_error": ("No se pudo comparar: {e}", "Comparison not possible: {e}"),
    "ensayo_n": ("Ensayo {i}: {n}", "Test {i}: {n}"),
    "conclusion": ("Conclusión", "Conclusion"),
    "fmt_fecha": ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"),
    "fmt_fecha_corta": ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"),
    # gráficas
    "g_presion": ("Presión (mbar)", "Pressure (mbar)"),
    "g_camara": (" (cámara)", " (chamber)"),
    "g_turbo": (" (lado turbo)", " (turbo side)"),
    "g_cierre": ("  cierre", "  closure"),
    "g_temperatura": ("Temperatura", "Temperature"),
    "g_original": ("Lectura original (con escalón de galga)", "Original reading (with gauge step)"),
    "g_p_camara": ("Presión cámara", "Chamber pressure"),
    "g_corregido": (" (escalón corregido)", " (step corrected)"),
    "g_transitorio": (" transitorio excluido", " excluded transient"),
    "g_pendiente": ("Pendiente final: {x:.2e} mbar/s", "Final slope: {x:.2e} mbar/s"),
    "g_modelo": ("Modelo: {n} (ΔAIC={d:.0f})", "Model: {n} (ΔAIC={d:.0f})"),
    "g_horas": ("Horas desde el cierre de la válvula", "Hours since valve closure"),
    "g_subida": ("Subida de presión", "Pressure rise"),
    "g_dpdt_med": ("dP/dt medida (±2σ)", "Measured dP/dt (±2σ)"),
    "g_neg": ("ventanas con dP/dt ≤ 0", "windows with dP/dt ≤ 0"),
    "g_cota": ("Cota superior de la fuga: {x:.2e} mbar/s", "Leak upper bound: {x:.2e} mbar/s"),
    "g_fuga_est": ("Fuga estimada: {x:.2e} ± {s:.1e}", "Estimated leak: {x:.2e} ± {s:.1e}"),
    "g_ajuste": ("Ajuste dP/dt = L + B·(t+t0)^-n", "Fit dP/dt = L + B·(t+t0)^-n"),
    "g_velocidad": ("Velocidad de subida — {c}", "Rate of rise — {c}"),
    "g_comp": ("Comparación de ensayos repetidos: misma dP/dt → fuga; dP/dt menor → desgasificación",
               "Repeated tests: same dP/dt → leak; lower dP/dt → outgassing"),
}


def et(clave, lang="es", **kw):
    es, en = ETIQ[clave]
    s = en if lang == "en" else es
    return s.format(**kw) if kw else s
