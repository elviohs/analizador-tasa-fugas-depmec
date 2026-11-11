# -*- coding: utf-8 -*-
"""
Analizador de Tasa de Fugas DEPMEC — V3 (interfaz gráfica)
Línea de Vacío y Criogenia · Departamento de Mecánica · IAC

Sustituye a DET_FUGAS_IAC_V1 y V2. Basado en el prototipo de Haroldo; esta
versión corrige los problemas detectados en la revisión de noviembre de 2026
(ver nucleo_fugas.py para el método).

Uso:  python analizador_fugas_v3.py  [fichero1.txt fichero2.txt ...]
"""
from __future__ import annotations

import os
import re
import queue
import sys
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.dates as mdates  # noqa: E402
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.widgets import SpanSelector  # noqa: E402

import graficos as gr  # noqa: E402
import nucleo_fugas as nf  # noqa: E402
from textos import IDIOMAS  # noqa: E402
# El informe PDF (fpdf2) se importa solo al generarlo: si falta el paquete,
# el programa abre igual y avisa al pulsar «Generar informe».

FMT_FECHA = "%d/%m/%Y %H:%M:%S"
NINGUNO = "(ninguno)"

AYUDA = f"""ANALIZADOR DE TASA DE FUGAS DEPMEC  v{nf.VERSION}

CÓMO SE USA
1. «Añadir ficheros…»: puede seleccionar varios ficheros del CryoMonitor a la vez.
   Cada cierre de válvula que se detecte es un ENSAYO en la lista (un mismo
   fichero puede tener varios). Renombre los ensayos con doble clic.
2. Para cada ensayo el programa propone qué sensor es la cámara y cuál el lado
   turbo (tras la guillotina), y detecta el cierre y el final. Revíselo en la
   pestaña «Datos»: puede cambiar la ventana arrastrando con el ratón sobre la
   gráfica o escribiendo las fechas.
3. Indique, si los conoce, el volumen (con su incertidumbre) y el caudal
   admisible. Cada ensayo guarda sus propios datos y opciones.
4. ANALIZAR analiza el ensayo seleccionado; «Analizar todos», toda la lista.
5. «Generar informe…»: PDF en español o en inglés, de un ensayo, de los
   seleccionados o de todos, con tabla resumen y comparación opcional.

QUÉ CALCULA
• dP/dt en ventanas a lo largo del ensayo (pestaña dP/dt, escala log-log).
• COTA SUPERIOR de la fuga = dP/dt final + 2σ. Es el resultado fiable: la
  desgasificación nunca resta, así que la fuga no puede ser mayor.
• Tendencia β (dP/dt ∝ t^β al final): β ≈ 0 → fuga dominante (subida lineal);
  β ≈ −1 o menor → desgasificación dominante.
• Estimación de la fuga solo cuando es separable. Si no lo es, se dice y se usa
  la cota.
• Veredicto APTO / NO APTO / NO CONCLUYENTE si da volumen y caudal admisible,
  siempre del lado conservador.

ENSAYOS REPETIDOS (lo más fiable)
Seleccione en la lista (Ctrl+clic) dos o más ensayos repetidos del MISMO
sistema y pulse «Comparar seleccionados». Si dP/dt se repite a igual tiempo
desde el cierre, es fuga; si baja, es desgasificación.

LIMITACIONES
• Por encima de ~1e-2 mbar la galga de rango completo mide con la Pirani, que
  depende del gas (p.ej. vapor de agua).
• El cambio Pirani/cátodo frío produce un escalón (~5e-3 mbar) que se corrige.
• Cambios de temperatura alteran la presión y la desgasificación: cargue el
  fichero de temperaturas cuando lo haya.
• Confirme siempre los resultados críticos con detector de helio.
"""

CAMPOS_DEFECTO = {
    "vol": "", "dvol": "10", "qadm": "", "area": "",
    "excl": f"{nf.CONFIG_DEFECTO['excluir_inicio_min']:g}",
    "ffin": f"{100 * nf.CONFIG_DEFECTO['fraccion_final']:g}",
    "tau": f"{nf.CONFIG_DEFECTO['tau_max_factor']:g}",
    "escalon": True, "picos": True, "modelos": True, "obs": "",
}


def recurso(nombre):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nombre)


def fecha_txt(t64) -> str:
    return datetime.strptime(str(t64)[:19], "%Y-%m-%dT%H:%M:%S").strftime(FMT_FECHA)


@dataclass
class Ensayo:
    """Un ensayo de subida: fichero + ventana + sensores + datos de criterio + resultado."""
    nombre: str
    reg: nf.Registro
    unidad: str = "mbar"
    sensor: str = ""
    ref: str = NINGUNO
    i0: Optional[int] = None
    i1: Optional[int] = None
    ventana_det: Optional[nf.Ventana] = None
    auto: bool = True
    nota_ventana: str = ""
    temps: Optional[nf.Registro] = None
    campos: dict = field(default_factory=lambda: dict(CAMPOS_DEFECTO))
    res: Optional[nf.Resultado] = None
    iid: str = ""


class PanelScroll(ttk.Frame):
    """Marco con barra de desplazamiento vertical para el panel de controles."""

    def __init__(self, padre, ancho=400):
        super().__init__(padre)
        self.canvas = tk.Canvas(self, width=ancho, highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.interior = ttk.Frame(self.canvas, padding=(8, 6))
        self.interior.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._rueda, add="+")

    def _rueda(self, e):
        w = self.winfo_containing(e.x_root, e.y_root)
        while w is not None:
            if isinstance(w, ttk.Treeview):
                return
            if w is self.canvas:
                self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
                return
            w = w.master


class Grafica:
    """Figura de matplotlib incrustada en una pestaña, con barra de zoom."""

    def __init__(self, padre):
        self.fig = Figure(figsize=(9, 5.5), dpi=100, facecolor="white")
        self.canvas = FigureCanvasTkAgg(self.fig, master=padre)
        barra = NavigationToolbar2Tk(self.canvas, padre, pack_toolbar=False)
        barra.update()
        barra.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    def mensaje(self, texto):
        self.fig.clear()
        self.fig.text(0.5, 0.5, texto, ha="center", va="center", color=gr.TINTA2, fontsize=11)
        self.canvas.draw_idle()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.ensayos: Dict[str, Ensayo] = {}
        self.actual: Optional[Ensayo] = None
        self.span = None
        self.trabajando = False
        self._cargando = False

        root.title(f"Analizador de tasa de fugas DEPMEC v{nf.VERSION} — IAC")
        root.geometry("1460x900")
        root.minsize(1100, 700)
        try:
            self._icono = tk.PhotoImage(file=recurso("icono.png"))
            root.iconphoto(True, self._icono)
        except Exception:
            pass
        estilo = ttk.Style()
        if sys.platform != "win32":
            estilo.theme_use("clam")
        estilo.configure("Accion.TButton", font=("TkDefaultFont", 11, "bold"), padding=8)
        estilo.configure("Seccion.TLabelframe.Label", font=("TkDefaultFont", 10, "bold"))
        estilo.configure("Pista.TLabel", foreground="#52514e")

        pan = ttk.PanedWindow(root, orient="horizontal")
        pan.pack(fill="both", expand=True)
        izq = PanelScroll(pan)
        der = ttk.Frame(pan)
        pan.add(izq, weight=0)
        pan.add(der, weight=1)
        self._panel_controles(izq.interior)
        self._panel_resultados(der)

        barra = ttk.Frame(root, padding=(8, 2))
        barra.pack(side="bottom", fill="x")
        self.estado = ttk.Label(barra, text="Añada uno o varios ficheros del CryoMonitor para empezar.")
        self.estado.pack(side="left")
        self.progreso = ttk.Progressbar(barra, mode="indeterminate", length=160)
        self.progreso.pack(side="right")
        root.protocol("WM_DELETE_WINDOW", self.salir)
        self._habilitar_formulario(False)

    # ================================================================== UI
    def _seccion(self, padre, titulo):
        f = ttk.LabelFrame(padre, text=titulo, style="Seccion.TLabelframe", padding=(8, 6))
        f.pack(fill="x", pady=(0, 8))
        f.columnconfigure(1, weight=1)
        return f

    def _campo(self, padre, fila, texto, var, ancho=14):
        ttk.Label(padre, text=texto).grid(row=fila, column=0, sticky="w", pady=2)
        e = ttk.Entry(padre, textvariable=var, width=ancho)
        e.grid(row=fila, column=1, sticky="ew", pady=2, padx=(6, 0))
        self._editables.append(e)
        return e

    def _panel_controles(self, p):
        self._editables: List[tk.Widget] = []
        try:  # cabecera con el logo del departamento
            self._logo = tk.PhotoImage(file=recurso("logo_depmec.png")).subsample(4)
            cab = ttk.Frame(p)
            cab.pack(fill="x", pady=(0, 8))
            ttk.Label(cab, image=self._logo).pack(side="left")
            ttk.Label(cab, text=f"Analizador de\ntasa de fugas\nv{nf.VERSION}", font=("TkDefaultFont", 10, "bold"),
                      justify="left").pack(side="left", padx=(10, 0))
        except Exception:  # noqa: BLE001 - sin logo el programa funciona igual
            pass
        # ---- 1. Ensayos
        s = self._seccion(p, "1 · Ensayos")
        bf = ttk.Frame(s)
        bf.grid(row=0, column=0, columnspan=2, sticky="ew")
        bf.columnconfigure((0, 1), weight=1)
        ttk.Button(bf, text="Añadir ficheros…", command=self.anadir_ficheros).grid(row=0, column=0, sticky="ew")
        ttk.Button(bf, text="Quitar", command=self.quitar).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        lf = ttk.Frame(s)
        lf.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 4))
        self.lista = ttk.Treeview(lf, columns=("diag", "cota"), show="tree headings", height=6, selectmode="extended")
        self.lista.heading("#0", text="Ensayo")
        self.lista.heading("diag", text="Diagnóstico")
        self.lista.heading("cota", text="Fuga ≤ (mbar/s)")
        self.lista.column("#0", width=175, stretch=True)
        self.lista.column("diag", width=120, stretch=False)
        self.lista.column("cota", width=72, stretch=False, anchor="e")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=sb.set)
        self.lista.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.lista.bind("<<TreeviewSelect>>", self._al_seleccionar_ensayo)
        self.lista.bind("<Double-1>", lambda e: self.renombrar())
        bf2 = ttk.Frame(s)
        bf2.grid(row=2, column=0, columnspan=2, sticky="ew")
        bf2.columnconfigure((0, 1), weight=1)
        ttk.Button(bf2, text="Renombrar", command=self.renombrar).grid(row=0, column=0, sticky="ew")
        ttk.Button(bf2, text="Temperaturas…", command=self.abrir_temps).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Button(bf2, text="Comparar seleccionados", command=self.comparar_seleccionados).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.lbl_info = ttk.Label(s, text="Ctrl+clic para seleccionar varios · doble clic para renombrar",
                                  style="Pista.TLabel", wraplength=320)
        self.lbl_info.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # ---- 2. Sensores
        s = self._seccion(p, "2 · Sensores del ensayo seleccionado")
        ttk.Label(s, text="Cámara de vacío:").grid(row=0, column=0, sticky="w")
        self.v_sensor = tk.StringVar()
        self.cb_sensor = ttk.Combobox(s, textvariable=self.v_sensor, state="readonly", width=18)
        self.cb_sensor.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=2)
        ttk.Label(s, text="Lado turbo:").grid(row=1, column=0, sticky="w")
        self.v_ref = tk.StringVar(value=NINGUNO)
        self.cb_ref = ttk.Combobox(s, textvariable=self.v_ref, state="readonly", width=18)
        self.cb_ref.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=2)
        ttk.Label(s, text="Unidad del fichero:").grid(row=2, column=0, sticky="w")
        self.v_unidad = tk.StringVar(value="mbar")
        self.cb_unidad = ttk.Combobox(s, textvariable=self.v_unidad, values=list(nf.UNIDADES), state="readonly", width=8)
        self.cb_unidad.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=2)
        for c in (self.cb_sensor, self.cb_ref, self.cb_unidad):
            c.bind("<<ComboboxSelected>>", lambda e: self._cambio_sensores())
            self._editables.append(c)

        # ---- 3. Ventana
        s = self._seccion(p, "3 · Ventana del ensayo")
        self.v_ini, self.v_fin = tk.StringVar(), tk.StringVar()
        self._campo(s, 0, "Cierre válvula:", self.v_ini, 19)
        self._campo(s, 1, "Fin:", self.v_fin, 19)
        bf = ttk.Frame(s)
        bf.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        b1 = ttk.Button(bf, text="Detectar", command=self.detectar)
        b1.pack(side="left", expand=True, fill="x")
        b2 = ttk.Button(bf, text="Aplicar fechas", command=self.aplicar_fechas)
        b2.pack(side="left", expand=True, fill="x", padx=(4, 0))
        self._editables += [b1, b2]
        self.lbl_ventana = ttk.Label(s, text="Formato dd/mm/aaaa hh:mm:ss. También puede arrastrar con el ratón "
                                     "sobre la gráfica «Datos».", style="Pista.TLabel", wraplength=320)
        self.lbl_ventana.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # ---- 4. Criterio
        self.vars = {k: (tk.BooleanVar(value=v) if isinstance(v, bool) else tk.StringVar(value=v))
                     for k, v in CAMPOS_DEFECTO.items()}
        s = self._seccion(p, "4 · Criostato y criterio (opcional)")
        self._campo(s, 0, "Volumen (L):", self.vars["vol"])
        self._campo(s, 1, "Incert. volumen (%):", self.vars["dvol"])
        self._campo(s, 2, "Q admisible (mbar·L/s):", self.vars["qadm"])
        self._campo(s, 3, "Superficie interna (cm²):", self.vars["area"])
        ttk.Label(s, text="Ej.: 1e-6. Sin volumen solo se dan tasas (mbar/s). Con volumen y superficie se calcula "
                          "la carga de gas por cm² (desgasificación específica).", style="Pista.TLabel",
                  wraplength=320).grid(row=4, column=0, columnspan=2, sticky="w")
        bc = ttk.Button(s, text="Copiar criterio y opciones a todos los ensayos", command=self.copiar_a_todos)
        bc.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._editables.append(bc)

        # ---- 5. Opciones
        s = self._seccion(p, "5 · Opciones de análisis")
        self._campo(s, 0, "Excluir inicio (min):", self.vars["excl"])
        self._campo(s, 1, "Ventana final (%):", self.vars["ffin"])
        self._campo(s, 2, "τ máx. modelos (×T):", self.vars["tau"])
        for fila, (k, t) in enumerate((("escalon", "Corregir escalón de galga (~5e-3 mbar)"),
                                       ("picos", "Eliminar picos aislados"),
                                       ("modelos", "Ajustar modelos (más lento)")), start=3):
            c = ttk.Checkbutton(s, text=t, variable=self.vars[k])
            c.grid(row=fila, column=0, columnspan=2, sticky="w")
            self._editables.append(c)
        ttk.Label(s, text="Observaciones del ensayo (informe):").grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        e = ttk.Entry(s, textvariable=self.vars["obs"])
        e.grid(row=7, column=0, columnspan=2, sticky="ew")
        self._editables.append(e)

        # ---- acciones
        f = ttk.Frame(p)
        f.pack(fill="x", pady=(2, 0))
        f.columnconfigure((0, 1), weight=1)
        self.b_analizar = ttk.Button(f, text="ANALIZAR", style="Accion.TButton", command=self.analizar)
        self.b_analizar.grid(row=0, column=0, sticky="ew")
        self.b_todos = ttk.Button(f, text="Analizar todos", style="Accion.TButton", command=self.analizar_todos)
        self.b_todos.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Button(f, text="Generar informe…  (ES / EN)", style="Accion.TButton",
                   command=self.dialogo_informe).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(f, text="Exportar CSV…", command=self.exportar_csv).grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(f, text="Exportar gráficas…", command=self.dialogo_graficas).grid(row=2, column=1, sticky="ew",
                                                                                    padx=(4, 0), pady=(6, 0))
        ttk.Button(f, text="Ayuda y método", command=self.ayuda).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(p, text=f"v{nf.VERSION} · Línea de Vacío y Criogenia · DEPMEC · IAC\n"
                          "Revise siempre los resultados críticos (helio).", style="Pista.TLabel",
                  justify="left").pack(anchor="w", pady=(10, 0))

    def _panel_resultados(self, p):
        self.banner = tk.Label(p, text="Añada ficheros de datos para empezar", font=("TkDefaultFont", 13, "bold"),
                               anchor="w", padx=14, pady=9, bg="#efeeea", fg=gr.TINTA)
        self.banner.pack(fill="x")
        self.nb = ttk.Notebook(p)
        self.nb.pack(fill="both", expand=True)

        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  Resultado  ")
        self.txt = tk.Text(f, wrap="word", font=("Consolas" if sys.platform == "win32" else "DejaVu Sans Mono", 10),
                           padx=12, pady=10, relief="flat", bg="white")
        sb = ttk.Scrollbar(f, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True)
        self._set_texto(AYUDA)

        self.g_datos = self._pestana("  Datos  ")
        self.g_subida = self._pestana("  Subida P(t)  ")
        self.g_dpdt = self._pestana("  dP/dt  ")

        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text="  Modelos  ")
        ttk.Label(f, text="Estimación secundaria. Una L marcada como «no separable», «compatible con 0» o «inconsistente» "
                          "no es una medida de fuga.", style="Pista.TLabel", wraplength=900).pack(anchor="w", pady=(0, 4))
        cols = ("dAIC", "peso", "L", "L2s", "obs")
        self.tabla = ttk.Treeview(f, columns=cols, show="tree headings", height=10)
        self.tabla.heading("#0", text="Modelo")
        self.tabla.column("#0", width=230)
        for c, t, w in zip(cols, ("ΔAIC", "Peso", "L (mbar/s)", "±2σ", "Observaciones"), (70, 60, 100, 90, 600)):
            self.tabla.heading(c, text=t)
            self.tabla.column(c, width=w, anchor="w" if c == "obs" else "e")
        self.tabla.pack(fill="both", expand=True)

        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  Comparación  ")
        self.lbl_comp = ttk.Label(f, text="Seleccione en la lista dos o más ensayos repetidos del mismo sistema "
                                          "(Ctrl+clic) y pulse «Comparar seleccionados».", wraplength=900, padding=6)
        self.lbl_comp.pack(anchor="w")
        gf = ttk.Frame(f)
        gf.pack(fill="both", expand=True)
        self.g_comp = Grafica(gf)
        self.g_comp.mensaje("Sin ensayos para comparar")
        for g in (self.g_datos, self.g_subida, self.g_dpdt):
            g.mensaje("Sin datos")

    def _pestana(self, titulo):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text=titulo)
        return Grafica(f)

    def _set_texto(self, texto):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", texto)
        self.txt.configure(state="disabled")

    def _estado(self, texto):
        self.estado.configure(text=texto)

    def _banner(self, texto, color):
        self.banner.configure(text=texto, bg=color)

    def _habilitar_formulario(self, si: bool):
        for w in self._editables:
            try:
                if isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if si else "disabled")
                else:
                    w.configure(state="normal" if si else "disabled")
            except tk.TclError:
                pass

    # ================================================================== lista de ensayos
    def _nombre_unico(self, base):
        nombres = {e.nombre for e in self.ensayos.values()}
        if base not in nombres:
            return base
        k = 2
        while f"{base} ({k})" in nombres:
            k += 1
        return f"{base} ({k})"

    def _fila_lista(self, e: Ensayo):
        if e.res is None:
            vals = ("sin analizar", "")
        else:
            d = e.res.clasificacion.replace(" DOMINANTE", "").replace("DESGASIFICACIÓN", "DESGAS.")
            d = d.replace("MIXTO / NO CONCLUYENTE", "MIXTO").replace("SIN SUBIDA SIGNIFICATIVA", "SIN SUBIDA")
            d = d.replace("PRESIÓN DESCENDENTE", "P. BAJA")
            if e.res.veredicto != "SIN CRITERIO":
                d += f" · {e.res.veredicto}"
            vals = (d, nf.fmt(e.res.cota_L))
        if e.iid and self.lista.exists(e.iid):
            self.lista.item(e.iid, text=e.nombre, values=vals)
        else:
            e.iid = self.lista.insert("", "end", text=e.nombre, values=vals)

    def anadir_ficheros(self, rutas=None):
        rutas = rutas or filedialog.askopenfilenames(
            title="Ficheros de presiones del CryoMonitor (puede seleccionar varios)",
            filetypes=[("Texto", "*.txt *.TXT *.dat *.csv"), ("Todos", "*.*")])
        if not rutas:
            return
        self._guardar_actual()
        nuevos, errores = [], []
        campos = dict(self.actual.campos) if self.actual else dict(CAMPOS_DEFECTO)
        campos["obs"] = ""
        for ruta in rutas:
            self._estado(f"Leyendo {os.path.basename(ruta)}…")
            self.root.update_idletasks()
            try:
                reg = nf.leer_registro(ruta)
                if not reg.columnas_presion():
                    raise ValueError("no contiene columnas de presión")
            except Exception as ex:  # noqa: BLE001
                errores.append(f"{os.path.basename(ruta)}: {ex}")
                continue
            a, b, vs = nf.ensayos_en_registro(reg, "mbar")
            cols = reg.columnas_presion()
            base = os.path.basename(ruta)
            if not vs:
                e = Ensayo(self._nombre_unico(base), reg, sensor=a or cols[0], ref=b or NINGUNO,
                           campos=dict(campos),
                           nota_ventana="No se detectó el cierre: seleccione la ventana arrastrando sobre la gráfica.")
                nuevos.append(e)
            for v in vs:
                nombre = self._nombre_unico(f"{os.path.splitext(base)[0]} · {fecha_txt(reg.tiempo[v.i0])[:16]}")
                nota = (f"Cierre detectado{' y confirmado por el lado turbo' if v.confirmado_ref else ''}. "
                        f"Fin: {v.motivo_fin}.")
                nuevos.append(Ensayo(nombre, reg, sensor=a, ref=b or NINGUNO, i0=v.i0, i1=v.i1, ventana_det=v,
                                     auto=True, nota_ventana=nota, campos=dict(campos)))
        for e in nuevos:
            self.ensayos_add(e)
        if errores:
            messagebox.showwarning("Algunos ficheros no se pudieron leer", "\n".join(errores))
        if nuevos:
            self.lista.selection_set(nuevos[0].iid)
            self.lista.focus(nuevos[0].iid)
            self.lista.see(nuevos[0].iid)
            self._estado(f"Añadidos {len(nuevos)} ensayo(s) de {len(rutas) - len(errores)} fichero(s).")
            self.nb.select(1)

    def ensayos_add(self, e: Ensayo):
        self._fila_lista(e)
        self.ensayos[e.iid] = e

    def quitar(self):
        sel = list(self.lista.selection())
        if not sel:
            return
        if not messagebox.askyesno("Quitar ensayos", f"¿Quitar {len(sel)} ensayo(s) de la lista? "
                                                     "(Los ficheros no se borran.)"):
            return
        for iid in sel:
            if self.actual is not None and self.actual.iid == iid:
                self.actual = None
            self.ensayos.pop(iid, None)
            self.lista.delete(iid)
        hijos = self.lista.get_children()
        if hijos:
            self.lista.selection_set(hijos[0])
            self.lista.focus(hijos[0])
        else:
            self._vaciar_vistas()

    def renombrar(self):
        e = self.actual
        if e is None:
            return
        nuevo = simpledialog.askstring("Renombrar ensayo", "Nombre del ensayo (aparece en el informe):",
                                       initialvalue=e.nombre, parent=self.root)
        if nuevo and nuevo.strip():
            e.nombre = nuevo.strip()
            self._fila_lista(e)

    def copiar_a_todos(self):
        if self.actual is None:
            return
        self._guardar_actual()
        claves = [k for k in CAMPOS_DEFECTO if k != "obs"]
        cambiados = 0
        for e in self.ensayos.values():
            if e is self.actual:
                continue
            nuevo = {**e.campos, **{k: self.actual.campos[k] for k in claves}}
            if nuevo != e.campos:
                e.campos = nuevo
                e.res = None
                self._fila_lista(e)
                cambiados += 1
        self._estado(f"Criterio y opciones copiados a {cambiados} ensayo(s). Pulse «Analizar todos».")

    def _seleccion(self) -> List[Ensayo]:
        orden = list(self.lista.get_children())
        return [self.ensayos[i] for i in orden if i in self.lista.selection() and i in self.ensayos]

    def _al_seleccionar_ensayo(self, _evt=None):
        foco = self.lista.focus()
        sel = self.lista.selection()
        if foco not in sel:
            foco = sel[0] if sel else ""
        e = self.ensayos.get(foco)
        if e is None or e is self.actual:
            return
        self._guardar_actual()
        self._cargar(e)

    def _guardar_actual(self):
        e = self.actual
        if e is None or self._cargando:
            return
        e.campos = {k: v.get() for k, v in self.vars.items()}
        e.unidad = self.v_unidad.get()
        e.sensor = self.v_sensor.get()
        e.ref = self.v_ref.get()

    def _cargar(self, e: Ensayo):
        self._cargando = True
        try:
            self.actual = e
            self._habilitar_formulario(True)
            cols = e.reg.columnas_presion()
            self.cb_sensor.configure(values=cols)
            self.cb_ref.configure(values=[NINGUNO] + cols)
            self.v_sensor.set(e.sensor)
            self.v_ref.set(e.ref)
            self.v_unidad.set(e.unidad)
            for k, v in e.campos.items():
                if k in self.vars:
                    self.vars[k].set(v)
            self.v_ini.set(fecha_txt(e.reg.tiempo[e.i0]) if e.i0 is not None else "")
            self.v_fin.set(fecha_txt(e.reg.tiempo[e.i1]) if e.i1 is not None else "")
            self.lbl_ventana.configure(text=e.nota_ventana or "Formato dd/mm/aaaa hh:mm:ss.")
        finally:
            self._cargando = False
        self.redibujar_datos()
        if e.res is not None:
            self.mostrar(e.res, cambiar_pestana=False)
        else:
            self._mostrar_info_fichero(e)

    def _mostrar_info_fichero(self, e: Ensayo):
        reg = e.reg
        avisos = reg.avisos + nf.comprobar_unidades(reg, e.unidad)
        self._set_texto(f"ENSAYO: {e.nombre}\n\nFichero: {reg.ruta}\nSHA-256: {reg.sha256}\n"
                        f"{len(reg.tiempo)} filas · {fecha_txt(reg.tiempo[0])} → {fecha_txt(reg.tiempo[-1])}\n\nCabecera:\n"
                        + "\n".join(f"  {k}: {v}" for k, v in reg.meta.items())
                        + f"\n\nColumnas de presión: {', '.join(reg.columnas_presion())}\n"
                        f"Cifras significativas del registro: {reg.digitos}\n"
                        + ("\nAvisos de lectura:\n" + "\n".join("  • " + a for a in avisos) if avisos else "")
                        + "\n\nCompruebe la ventana en la pestaña «Datos» y pulse ANALIZAR.")
        self._banner(f"{e.nombre} — sin analizar", "#efeeea")
        for g in (self.g_subida, self.g_dpdt):
            g.mensaje("Ensayo sin analizar")
        for i in self.tabla.get_children():
            self.tabla.delete(i)

    def _vaciar_vistas(self):
        self.actual = None
        self._habilitar_formulario(False)
        self._set_texto(AYUDA)
        self._banner("Añada ficheros de datos para empezar", "#efeeea")
        for g in (self.g_datos, self.g_subida, self.g_dpdt):
            g.mensaje("Sin datos")
        for i in self.tabla.get_children():
            self.tabla.delete(i)

    def abrir_temps(self):
        e = self.actual
        if e is None:
            messagebox.showinfo("Sin ensayo", "Seleccione primero un ensayo de la lista.")
            return
        ruta = filedialog.askopenfilename(title="Fichero de temperaturas (opcional)",
                                          filetypes=[("Texto", "*.txt *.TXT *.dat *.csv"), ("Todos", "*.*")])
        if not ruta:
            return
        try:
            t = nf.leer_registro(ruta)
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("No se pudo leer el fichero de temperaturas",
                                 f"{ex}\n\nEl lector espera el formato del CryoMonitor (cabecera con «Date» y "
                                 "«Local time»). Si el formato es otro, envíe un ejemplo para adaptarlo.")
            return
        ini, fin = max(t.tiempo[0], e.reg.tiempo[0]), min(t.tiempo[-1], e.reg.tiempo[-1])
        if ini >= fin:
            fmt_f = lambda x: str(x)[:16].replace("T", " ")  # noqa: E731
            if not messagebox.askyesno(
                    "Fechas que no coinciden",
                    "El fichero de temperaturas no se solapa en el tiempo con el de presiones:\n\n"
                    f"  Presiones:      {fmt_f(e.reg.tiempo[0])} → {fmt_f(e.reg.tiempo[-1])}\n"
                    f"  Temperaturas: {fmt_f(t.tiempo[0])} → {fmt_f(t.tiempo[-1])}\n\n"
                    "¿Asignarlo de todas formas?"):
                return
        n = 0
        for x in self.ensayos.values():   # todos los ensayos del mismo fichero de presiones
            if x.reg is e.reg:
                x.temps = t
                x.res = None
                self._fila_lista(x)
                n += 1
        self._estado(f"Temperaturas {os.path.basename(ruta)} asignadas a {n} ensayo(s). Vuelva a analizar.")
        self._cargar(e)

    # ================================================================== ventana
    def _cambio_sensores(self):
        if self._cargando or self.actual is None:
            return
        self._guardar_actual()
        self.redibujar_datos()

    def _fijar_ventana(self, i0, i1, auto, nota, det=None):
        e = self.actual
        e.i0, e.i1, e.auto, e.nota_ventana = int(i0), int(i1), auto, nota
        if det is not None:
            e.ventana_det = det
        self.v_ini.set(fecha_txt(e.reg.tiempo[e.i0]))
        self.v_fin.set(fecha_txt(e.reg.tiempo[e.i1]))
        self.lbl_ventana.configure(text=nota)

    def detectar(self):
        e = self.actual
        if e is None:
            return
        self._guardar_actual()
        f = nf.UNIDADES[e.unidad]
        ref = None if e.ref == NINGUNO else e.reg.columnas[e.ref] * f
        vs = nf.detectar_ensayos(e.reg.segundos, e.reg.columnas[e.sensor] * f, ref)
        if not vs:
            messagebox.showinfo("Sin detección", "No se encontró una subida brusca y sostenida (> 1 h). "
                                                 "Seleccione la ventana arrastrando sobre la gráfica «Datos».")
            return
        v = min(vs, key=lambda v: abs(v.i0 - e.i0)) if e.i0 is not None else max(vs, key=lambda v: v.puntuacion)
        self._fijar_ventana(v.i0, v.i1, True, f"Cierre detectado{' y confirmado por el lado turbo' if v.confirmado_ref else ''}. "
                                              f"Fin: {v.motivo_fin}.", v)
        self.redibujar_datos()

    def aplicar_fechas(self):
        e = self.actual
        if e is None:
            return
        try:
            a = np.datetime64(datetime.strptime(self.v_ini.get().strip(), FMT_FECHA))
            b = np.datetime64(datetime.strptime(self.v_fin.get().strip(), FMT_FECHA))
        except ValueError:
            messagebox.showerror("Fecha no válida", "Use el formato dd/mm/aaaa hh:mm:ss")
            return
        if b <= a:
            messagebox.showerror("Ventana no válida", "El fin debe ser posterior al cierre.")
            return
        i0 = int(np.searchsorted(e.reg.tiempo, a))
        i1 = int(np.searchsorted(e.reg.tiempo, b, side="right") - 1)
        if i1 - i0 < 10:
            messagebox.showerror("Ventana no válida", "La ventana tiene muy pocos puntos.")
            return
        self._fijar_ventana(i0, i1, False, "Ventana fijada manualmente.")
        self.redibujar_datos()

    def _al_arrastrar(self, xmin, xmax):
        e = self.actual
        if e is None or xmax - xmin <= 0:
            return
        a = np.datetime64(mdates.num2date(xmin).replace(tzinfo=None), "s")
        b = np.datetime64(mdates.num2date(xmax).replace(tzinfo=None), "s")
        i0 = int(np.searchsorted(e.reg.tiempo, a))
        i1 = int(np.searchsorted(e.reg.tiempo, b, side="right") - 1)
        if i1 - i0 < 10:
            return
        self._fijar_ventana(i0, i1, False, "Ventana seleccionada con el ratón (manual).")
        self.root.after(10, self.redibujar_datos)

    def redibujar_datos(self):
        e = self.actual
        if e is None:
            return
        ref = None if e.ref == NINGUNO else e.ref
        ventana = (e.reg.tiempo[e.i0], e.reg.tiempo[e.i1]) if e.i0 is not None else None
        otras = [(x.reg.tiempo[x.i0], x.reg.tiempo[x.i1]) for x in self.ensayos.values()
                 if x is not e and x.reg is e.reg and x.i0 is not None]
        ax = gr.dibujar_datos(self.g_datos.fig, e.reg, e.unidad, e.sensor, ref, None, e.temps, ventana,
                              otras_ventanas=otras)
        xl = ax.get_xlim()
        self.span = SpanSelector(ax, self._al_arrastrar, "horizontal", useblit=True, minspan=1e-4,
                                 props=dict(alpha=0.2, facecolor=gr.NARANJA), interactive=False)
        ax.set_xlim(xl)  # el selector no debe alterar los límites
        self.g_datos.canvas.draw_idle()

    # ================================================================== análisis
    @staticmethod
    def _num(campos, k, nombre, obligatorio=False, minimo=None):
        s = str(campos.get(k, "")).strip().replace(",", ".")
        if not s:
            if obligatorio:
                raise ValueError(f"Falta {nombre}.")
            return None
        try:
            v = float(s)
        except ValueError:
            raise ValueError(f"{nombre}: «{campos.get(k)}» no es un número.")
        if minimo is not None and v < minimo:
            raise ValueError(f"{nombre} debe ser ≥ {minimo}.")
        return v

    def _parametros(self, e: Ensayo) -> dict:
        if e.i0 is None or e.i1 is None:
            raise ValueError("No hay ventana de ensayo: use «Detectar» o seleccione con el ratón.")
        c = e.campos
        vol = self._num(c, "vol", "Volumen", minimo=0)
        dvol = self._num(c, "dvol", "Incertidumbre del volumen", minimo=0) or 0.0
        qadm = self._num(c, "qadm", "Q admisible", minimo=0)
        if qadm and not vol:
            raise ValueError("Para aplicar el caudal admisible hace falta el volumen.")
        area = self._num(c, "area", "Superficie interna", minimo=0)
        if area and not vol:
            raise ValueError("Para la carga de gas por superficie hace falta el volumen.")
        cfg = {
            "excluir_inicio_min": self._num(c, "excl", "Excluir inicio", True, 0),
            "fraccion_final": self._num(c, "ffin", "Ventana final", True, 1) / 100.0,
            "tau_max_factor": self._num(c, "tau", "τ máx", True, 0.01),
            "corregir_escalon": bool(c.get("escalon", True)),
            "eliminar_picos": bool(c.get("picos", True)),
        }
        if cfg["fraccion_final"] > 0.8:
            raise ValueError("La ventana final no debe superar el 80 %.")
        ref = None if e.ref in (NINGUNO, e.sensor) else e.ref
        return dict(reg=e.reg, sensor=e.sensor, unidad=e.unidad, i0=e.i0, i1=e.i1, sensor_ref=ref,
                    criterio=nf.Criterio(vol or None, dvol / 100.0, qadm or None, area or None), config=cfg,
                    temperaturas=e.temps, con_modelos=bool(c.get("modelos", True)),
                    ventana_detectada=e.ventana_det if e.auto else None)

    def analizar(self):
        if self.actual is None:
            messagebox.showinfo("Sin ensayo", "Añada ficheros y seleccione un ensayo de la lista.")
            return
        self._guardar_actual()
        self._lanzar([self.actual])

    def analizar_todos(self):
        if not self.ensayos:
            return
        self._guardar_actual()
        self._lanzar([self.ensayos[i] for i in self.lista.get_children()])

    def _lanzar(self, lista: List[Ensayo], al_terminar: Optional[Callable[[], None]] = None):
        if self.trabajando:
            return
        trabajos, invalidos = [], []
        for e in lista:
            try:
                trabajos.append((e, self._parametros(e)))
            except ValueError as ex:
                invalidos.append(f"{e.nombre}: {ex}")
        if invalidos:
            messagebox.showwarning("Revise los datos", "\n".join(invalidos)
                                   + ("\n\nEl resto se analizará." if trabajos else ""))
        if not trabajos:
            return
        self.trabajando = True
        for b in (self.b_analizar, self.b_todos):
            b.configure(state="disabled")
        self.progreso.start(12)
        cola: queue.Queue = queue.Queue()
        errores: List[str] = []

        def trabajo():  # hilo secundario: sin llamadas a Tk
            for k, (e, kw) in enumerate(trabajos, 1):
                cola.put(("inicio", e, k))
                try:
                    cola.put(("ok", e, nf.analizar(**kw)))
                except Exception as ex:  # noqa: BLE001
                    cola.put(("error", e, (ex, traceback.format_exc())))
            cola.put(("fin", None, None))

        def sondear():
            try:
                while True:
                    tipo, e, dato = cola.get_nowait()
                    if tipo == "inicio":
                        self._estado(f"Analizando {dato}/{len(trabajos)}: {e.nombre}…")
                    elif tipo == "ok":
                        e.res = dato
                        self._fila_lista(e)
                        if e is self.actual:
                            self.mostrar(dato)
                    elif tipo == "error":
                        ex, tb = dato
                        errores.append(f"{e.nombre}: {ex}")
                        if e is self.actual:
                            self._set_texto(f"ERROR en {e.nombre}\n\n{tb}")
                    elif tipo == "fin":
                        self._fin_analisis(len(trabajos), errores, al_terminar)
                        return
            except queue.Empty:
                pass
            self.root.after(100, sondear)

        threading.Thread(target=trabajo, daemon=True).start()
        self.root.after(100, sondear)

    def _fin_analisis(self, n, errores, al_terminar):
        self.trabajando = False
        for b in (self.b_analizar, self.b_todos):
            b.configure(state="normal")
        self.progreso.stop()
        if errores:
            self._estado(f"Análisis terminado con {len(errores)} error(es).")
            messagebox.showerror("Errores en el análisis", "\n\n".join(errores))
        else:
            self._estado(f"Análisis completado ({n} ensayo{'s' if n > 1 else ''}).")
        if al_terminar is not None:
            al_terminar()

    def mostrar(self, r: nf.Resultado, cambiar_pestana: bool = True):
        e = self.actual
        self._set_texto((f"ENSAYO: {e.nombre}\n" if e else "") + nf.resumen_texto(r))
        texto = (f"{e.nombre}  ·  " if e else "") + r.clasificacion + ("" if r.estacionario else " (no estacionario)")
        texto += (f"  ·  Fuga ≤ {r.cota_L:.2e} mbar/s" if np.isfinite(r.cota_L)
                  else "  ·  Fuga no acotable (la presión baja)")
        if r.Q_cota:
            texto += f"  (Q ≤ {r.Q_cota:.2e} mbar·L/s)"
        texto += f"  ·  {r.veredicto}"
        self._banner(texto, gr.ESTADO.get(r.veredicto, "#efeeea"))
        gr.dibujar_subida(self.g_subida.fig, r)
        self.g_subida.canvas.draw_idle()
        gr.dibujar_dpdt(self.g_dpdt.fig, r)
        self.g_dpdt.canvas.draw_idle()
        for i in self.tabla.get_children():
            self.tabla.delete(i)
        if r.derivada is not None:
            d = r.derivada
            self.tabla.insert("", "end", text=d.nombre, values=("—", "—", nf.fmt(d.L), nf.fmt(2 * d.L_sig),
                                                                "; ".join(d.avisos) or "—"))
        for m in r.modelos:
            self.tabla.insert("", "end", text=m.nombre,
                              values=(f"{m.daic:.1f}", f"{m.peso:.2f}", nf.fmt(m.L) if m.tiene_L else "(sin fuga)",
                                      nf.fmt(2 * m.L_sig) if m.tiene_L else "", "; ".join(m.avisos) or "—"))
        if cambiar_pestana:
            self.nb.select(0)

    # ================================================================== comparación
    def comparar_seleccionados(self):
        self._guardar_actual()
        sel = [e for e in self._seleccion() if e.res is not None]
        sin = [e.nombre for e in self._seleccion() if e.res is None]
        if len(sel) < 2:
            messagebox.showinfo("Comparar ensayos",
                                "Seleccione en la lista (Ctrl+clic) dos o más ensayos ya analizados del mismo sistema."
                                + (f"\n\nSin analizar: {', '.join(sin)}" if sin else ""))
            return
        et = [e.nombre for e in sel]
        rs = [e.res for e in sel]
        gr.dibujar_comparacion(self.g_comp.fig, rs, et)
        self.g_comp.canvas.draw_idle()
        try:
            c = nf.comparar(rs, et)
            self.lbl_comp.configure(text=c.conclusion + "   Ratios de dP/dt respecto a «" + et[0] + "»: "
                                    + ", ".join(f"{n}: {x:.2f}" for n, x in zip(et[1:], c.ratio_medio))
                                    + "   (solo tiene sentido entre ensayos repetidos del mismo sistema)")
        except ValueError as ex:
            self.lbl_comp.configure(text=str(ex))
        self.nb.select(5)

    # ================================================================== informe
    def dialogo_informe(self):
        if not self.ensayos:
            messagebox.showinfo("Sin ensayos", "Añada y analice al menos un ensayo.")
            return
        self._guardar_actual()
        w = tk.Toplevel(self.root)
        w.title("Generar informe PDF")
        w.transient(self.root)
        w.resizable(False, False)
        fr = ttk.Frame(w, padding=14)
        fr.pack(fill="both", expand=True)

        ttk.Label(fr, text="Idioma del informe", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        v_lang = tk.StringVar(value="es")
        for k, (cod, nom) in enumerate(IDIOMAS.items()):
            ttk.Radiobutton(fr, text=nom, value=cod, variable=v_lang).grid(row=1, column=k, sticky="w", padx=(0, 16))

        ttk.Label(fr, text="Ensayos incluidos", font=("TkDefaultFont", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(12, 0))
        sel = self._seleccion()
        todos = [self.ensayos[i] for i in self.lista.get_children()]
        v_alc = tk.StringVar(value="sel" if len(sel) > 1 else "actual")
        opciones = [("actual", f"Ensayo actual ({self.actual.nombre if self.actual else '—'})"),
                    ("sel", f"Ensayos seleccionados en la lista ({len(sel)})"),
                    ("todos", f"Todos los ensayos de la lista ({len(todos)})")]
        for k, (cod, txt) in enumerate(opciones):
            ttk.Radiobutton(fr, text=txt, value=cod, variable=v_alc).grid(row=3 + k, column=0, columnspan=3, sticky="w")

        v_comp = tk.BooleanVar(value=False)
        ttk.Checkbutton(fr, text="Incluir comparación de ensayos (solo ensayos repetidos del mismo sistema)",
                        variable=v_comp).grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Label(fr, text="Observaciones generales (portada):").grid(row=7, column=0, columnspan=3, sticky="w", pady=(10, 2))
        t_obs = tk.Text(fr, width=62, height=4, wrap="word")
        t_obs.grid(row=8, column=0, columnspan=3, sticky="ew")
        bf = ttk.Frame(fr)
        bf.grid(row=9, column=0, columnspan=3, sticky="e", pady=(12, 0))

        def generar():
            alc = v_alc.get()
            lista = ([self.actual] if alc == "actual" and self.actual else sel if alc == "sel" else todos)
            lista = [e for e in lista if e is not None]
            if not lista:
                messagebox.showinfo("Sin ensayos", "No hay ensayos en esa selección.", parent=w)
                return
            lang, comp, obs = v_lang.get(), v_comp.get(), t_obs.get("1.0", "end").strip()
            w.destroy()
            pendientes = [e for e in lista if e.res is None]
            if pendientes:
                if not messagebox.askyesno("Ensayos sin analizar",
                                           f"{len(pendientes)} ensayo(s) aún no están analizados:\n"
                                           + "\n".join("  • " + e.nombre for e in pendientes)
                                           + "\n\n¿Analizarlos ahora y generar después el informe?"):
                    return
                self._lanzar(pendientes, al_terminar=lambda: self._generar_informe(lista, lang, comp, obs))
            else:
                self._generar_informe(lista, lang, comp, obs)

        ttk.Button(bf, text="Cancelar", command=w.destroy).pack(side="right")
        ttk.Button(bf, text="Generar…", style="Accion.TButton", command=generar).pack(side="right", padx=(0, 6))
        w.grab_set()
        w.wait_visibility()
        w.focus_set()

    def _generar_informe(self, lista: List[Ensayo], lang: str, comparar: bool, obs: str):
        try:
            import informe_pdf as ip
        except ImportError as ex:
            messagebox.showerror("Falta un paquete para el PDF",
                                 f"{ex}\n\nPara generar el informe hace falta el paquete fpdf2. "
                                 "Cierre el programa y ejecute de nuevo ejecutar_v3.bat (ofrece instalarlo), "
                                 "o en una consola:\n\n    py -m pip install --user fpdf2")
            return
        analizados = [e for e in lista if e.res is not None]
        if not analizados:
            messagebox.showwarning("Informe", "Ninguno de los ensayos elegidos se pudo analizar.")
            return
        if len(analizados) < len(lista):
            messagebox.showwarning("Informe", f"{len(lista) - len(analizados)} ensayo(s) con error no se incluyen.")
        base = analizados[0].nombre if len(analizados) == 1 else f"{len(analizados)}_ensayos"
        base = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)[:60]
        pref = "Informe_fugas" if lang == "es" else "Leak_report"
        ruta = filedialog.asksaveasfilename(title="Guardar informe PDF", defaultextension=".pdf",
                                            initialfile=f"{pref}_{base}_{lang.upper()}_{datetime.now():%Y%m%d_%H%M}.pdf",
                                            filetypes=[("PDF", "*.pdf")])
        if not ruta:
            return
        try:
            self._estado("Generando informe PDF…")
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            ens = [ip.EnsayoInforme(e.nombre, e.res, e.reg, e.temps, str(e.campos.get("obs", ""))) for e in analizados]
            ip.generar_informe_multi(ens, ruta, lang=lang, comparar=comparar and len(ens) > 1, observaciones=obs)
            self._estado(f"Informe guardado: {ruta}")
            if messagebox.askyesno("Informe PDF", f"Informe guardado en:\n{ruta}\n\n¿Abrirlo ahora?"):
                self._abrir_fichero(ruta)
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("Error al generar el PDF", f"{ex}\n\n{traceback.format_exc()[-800:]}")
        finally:
            self.root.config(cursor="")

    @staticmethod
    def _abrir_fichero(ruta):
        try:
            if sys.platform == "win32":
                os.startfile(ruta)  # noqa: S606
            elif sys.platform == "darwin":
                os.system(f'open "{ruta}"')
            else:
                os.system(f'xdg-open "{ruta}" >/dev/null 2>&1 &')
        except Exception:  # noqa: BLE001
            pass

    # ================================================================== gráficas para publicaciones
    def dialogo_graficas(self):
        """Exporta las gráficas del ensayo actual (y la comparación de los seleccionados)
        en formatos de publicación (PNG 300 ppp, PDF, EPS, SVG), en español o inglés."""
        e = self.actual
        if e is None or e.res is None:
            messagebox.showinfo("Sin resultados", "Analice primero el ensayo seleccionado.")
            return
        w = tk.Toplevel(self.root)
        w.title("Exportar gráficas")
        w.transient(self.root)
        w.resizable(False, False)
        fr = ttk.Frame(w, padding=14)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text="Idioma de las gráficas", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        v_lang = tk.StringVar(value="en")
        for k, (cod, nom) in enumerate(IDIOMAS.items()):
            ttk.Radiobutton(fr, text=nom, value=cod, variable=v_lang).grid(row=1, column=k, sticky="w", padx=(0, 16))
        ttk.Label(fr, text="Formatos", font=("TkDefaultFont", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(10, 0))
        formatos = {"png": tk.BooleanVar(value=True), "pdf": tk.BooleanVar(value=True),
                    "eps": tk.BooleanVar(value=False), "svg": tk.BooleanVar(value=False)}
        for k, (ext, var) in enumerate(formatos.items()):
            ttk.Checkbutton(fr, text=ext.upper() + (" (300 ppp)" if ext == "png" else ""), variable=var).grid(
                row=3, column=k, sticky="w", padx=(0, 10))
        sel = [x for x in self._seleccion() if x.res is not None]
        v_comp = tk.BooleanVar(value=len(sel) > 1)
        c = ttk.Checkbutton(fr, text=f"Incluir la comparación de los ensayos seleccionados ({len(sel)})", variable=v_comp)
        c.grid(row=4, column=0, columnspan=4, sticky="w", pady=(10, 0))
        if len(sel) < 2:
            c.configure(state="disabled")
        ttk.Label(fr, text="Tamaño: 17,8 × 10,7 cm (ancho de doble columna). En EPS las transparencias se "
                           "dibujan opacas.", style="Pista.TLabel", wraplength=420).grid(row=5, column=0, columnspan=4,
                                                                                    sticky="w", pady=(8, 0))

        def exportar():
            exts = [x for x, v in formatos.items() if v.get()]
            if not exts:
                messagebox.showinfo("Formatos", "Elija al menos un formato.", parent=w)
                return
            carpeta = filedialog.askdirectory(title="Carpeta donde guardar las gráficas", parent=w)
            if not carpeta:
                return
            lang = v_lang.get()
            base = re.sub(r"[^\w-]+", "_", e.nombre).strip("_")[:60] or "ensayo"
            r, reg = e.res, e.reg
            ref = None if e.ref == NINGUNO else e.ref
            figuras = [("dpdt", lambda fg: gr.dibujar_dpdt(fg, r, lang)),
                       ("subida", lambda fg: gr.dibujar_subida(fg, r, lang)),
                       ("datos", lambda fg: gr.dibujar_datos(fg, reg, r.unidad, r.sensor, ref, r, e.temps,
                                                             (r.t_cierre, r.t_fin), lang))]
            if v_comp.get() and len(sel) > 1:
                figuras.append(("comparacion", lambda fg: gr.dibujar_comparacion(fg, [x.res for x in sel],
                                                                                 [x.nombre for x in sel], lang)))
            hechos = []
            try:
                for nombre, dib in figuras:
                    fig = Figure(figsize=(7.0, 4.2), dpi=100, facecolor="white")
                    dib(fig)
                    for ext in exts:
                        ruta = os.path.join(carpeta, f"{base}_{nombre}_{lang}.{ext}")
                        fig.savefig(ruta, dpi=300 if ext == "png" else 100, facecolor="white",
                                    bbox_inches="tight", pad_inches=0.04)
                        hechos.append(os.path.basename(ruta))
            except Exception as ex:  # noqa: BLE001
                messagebox.showerror("Error al exportar", str(ex), parent=w)
                return
            w.destroy()
            self._estado(f"{len(hechos)} gráficas guardadas en {carpeta}")
            messagebox.showinfo("Gráficas exportadas", f"Guardadas en {carpeta}:\n" + "\n".join(hechos))

        bf = ttk.Frame(fr)
        bf.grid(row=6, column=0, columnspan=4, sticky="e", pady=(12, 0))
        ttk.Button(bf, text="Cancelar", command=w.destroy).pack(side="right")
        ttk.Button(bf, text="Exportar…", style="Accion.TButton", command=exportar).pack(side="right", padx=(0, 6))
        w.grab_set()
        w.wait_visibility()
        w.focus_set()

    def exportar_csv(self):
        e = self.actual
        if e is None or e.res is None:
            messagebox.showinfo("Sin resultados", "Analice primero el ensayo seleccionado.")
            return
        ruta = filedialog.asksaveasfilename(title="Exportar resultados a CSV", defaultextension=".csv",
                                            filetypes=[("CSV (Excel, separador ;)", "*.csv")])
        if not ruta:
            return
        r = e.res

        def n(x):
            return "" if x is None or not np.isfinite(x) else f"{x:.6e}".replace(".", ",")
        try:
            with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
                f.write("Analizador de fugas DEPMEC;v" + r.version + "\n")
                filas = [("Ensayo", e.nombre), ("Fichero", os.path.basename(r.fichero)), ("SHA-256", r.sha256),
                         ("Sensor", r.sensor), ("Cierre", str(r.t_cierre)), ("Fin", str(r.t_fin)),
                         ("Duración (h)", n(r.duracion_s / 3600)), ("Diagnóstico", r.clasificacion),
                         ("Beta", n(r.beta)), ("Beta sigma", n(r.beta_sig)),
                         ("dP/dt final (mbar/s)", n(r.s_final)), ("dP/dt final sigma", n(r.s_final_sig)),
                         ("Cota L (mbar/s)", n(r.cota_L)),
                         ("L estimada (mbar/s)", n(r.L_estimada[0]) if r.L_estimada else "no separable"),
                         ("Q cota (mbar·L/s)", n(r.Q_cota)), ("Veredicto", r.veredicto)]
                if r.carga_especifica:
                    filas += [("Superficie interna (cm2)", n(r.criterio.area_cm2)),
                              ("Carga específica final (mbar·L/s/cm2)", n(r.carga_especifica[0])),
                              ("Carga específica sigma", n(r.carga_especifica[1])),
                              ("Carga específica cota", n(r.carga_especifica[2]))]
                for k, v in filas:
                    f.write(f"{k};{v}\n")
                f.write("\nt_centro (h);dP/dt (mbar/s);sigma (mbar/s)\n")
                for t, s, sg in zip(r.pend.t, r.pend.s, r.pend.sig):
                    f.write(f"{n(t / 3600)};{n(s)};{n(sg)}\n")
                f.write("\nt (h);P corregida (mbar);P original (mbar)\n")
                for t, p, pb in zip(r.t_todo, r.p_todo, r.p_bruta):
                    f.write(f"{n(t / 3600)};{n(p)};{n(pb)}\n")
            self._estado(f"CSV guardado: {ruta}")
        except OSError as ex:
            messagebox.showerror("No se pudo guardar", str(ex))

    # ================================================================== otros
    def ayuda(self):
        w = tk.Toplevel(self.root)
        w.title("Ayuda y método")
        w.geometry("780x680")
        t = tk.Text(w, wrap="word", padx=14, pady=12, relief="flat")
        t.insert("end", AYUDA)
        t.configure(state="disabled")
        t.pack(fill="both", expand=True)

    def salir(self):
        self.root.quit()
        self.root.destroy()


def autotest(ruta_salida: str) -> int:
    """Comprobación sin ventanas (la usa la compilación automática): genera un
    ensayo sintético, lo analiza con modelos y crea un informe PDF en inglés.
    Escribe «OK» o el error en `ruta_salida` y devuelve el código de salida."""
    import tempfile
    try:
        import informe_pdf as ip
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "sintetico.txt")
            t = np.arange(0, 20 * 3600, 20.0)
            p = np.where(t < 3600, 1e-5, 1e-5 + 1e-8 * (t - 3600))
            r = np.where(t < 3600, 1e-5, 2e-7)
            t0 = datetime(2026, 1, 1, 8, 0, 0)

            def fmt(v):
                m, e = f"{v:.2E}".split("E")
                return f"{m.replace('.', ',')}E{int(e):+d}"
            with open(ruta, "w", encoding="cp1252") as f:
                f.write("Subsystem or prototype:  CryoMonitor\n\n")
                f.write("                                      COM5 C1          COM5 C2\n")
                f.write("Seconds   Date          Local time    Press1(P)        Press2(P)\n")
                for i, (a, b) in enumerate(zip(p, r)):
                    ti = t0 + timedelta(seconds=float(t[i]))
                    f.write(f"{int(t[i]) + 1:<10}{ti:%d/%m/%Y}    {ti.hour}:{ti:%M:%S}       {fmt(a):<17}{fmt(b)}\n")
            reg = nf.leer_registro(ruta)
            sensor, ref, vs = nf.ensayos_en_registro(reg)
            assert vs, "no se detectó el ensayo sintético"
            res = nf.analizar(reg, sensor, sensor_ref=ref, i0=vs[0].i0, i1=vs[0].i1,
                              criterio=nf.Criterio(10, 0.1, 1e-5), ventana_detectada=vs[0])
            assert res.clasificacion == "FUGA DOMINANTE", res.clasificacion
            pdf = os.path.join(d, "autotest.pdf")
            ip.generar_informe_multi([ip.EnsayoInforme("Autotest", res, reg)], pdf, lang="en")
            assert os.path.getsize(pdf) > 20000
            if getattr(sys, "frozen", False):   # en el .exe deben ir el logo y el icono
                for f in ("logo_depmec.png", "icono.png"):
                    assert os.path.exists(recurso(f)), f"falta {f} en el ejecutable"
        with open(ruta_salida, "w", encoding="utf-8") as f:
            f.write(f"OK v{nf.VERSION} L={res.s_final:.3e}\n")
        return 0
    except Exception:  # noqa: BLE001
        with open(ruta_salida, "w", encoding="utf-8") as f:
            f.write("ERROR\n" + traceback.format_exc())
        return 1


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--autotest":
        sys.exit(autotest(sys.argv[2]))
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    app = App(root)
    rutas = [a for a in sys.argv[1:] if os.path.exists(a)]
    if rutas:
        root.after(200, lambda: app.anadir_ficheros(rutas))
    root.mainloop()


def _registrar_error(texto: str) -> str:
    """Guarda el error junto al programa (o en la carpeta temporal) y devuelve la ruta."""
    import tempfile
    for carpeta in (os.path.dirname(os.path.abspath(sys.argv[0])), tempfile.gettempdir()):
        ruta = os.path.join(carpeta, "error_v3.log")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(f"{datetime.now():%d/%m/%Y %H:%M:%S}  v{nf.VERSION}  Python {sys.version}\n\n{texto}")
            return ruta
        except OSError:
            continue
    return ""


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - mostrar cualquier fallo de arranque
        tb = traceback.format_exc()
        ruta = _registrar_error(tb)
        print(tb, file=sys.stderr)
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("El analizador no pudo arrancar",
                                 f"{tb[-1500:]}\n\nDetalle guardado en: {ruta}")
            r.destroy()
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
