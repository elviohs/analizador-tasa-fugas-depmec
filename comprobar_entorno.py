# -*- coding: utf-8 -*-
"""Comprueba que el Python de este equipo tiene lo necesario para la V3.

Códigos de salida: 0 = todo correcto; 1 = faltan paquetes instalables con pip;
2 = problema que pip no resuelve (versión de Python o falta tkinter).
"""
import importlib.util
import sys


def version(mod):
    try:
        m = __import__(mod)
        return getattr(m, "__version__", None) or getattr(m, "FPDF_VERSION", None) or "?"
    except Exception as e:  # noqa: BLE001
        return f"error al importar: {e}"


def vt(v):
    try:
        return tuple(int(x) for x in v.split(".")[:2])
    except Exception:  # noqa: BLE001
        return (0, 0)


def main():
    print(f"Python {sys.version.split()[0]}  ({sys.executable})")
    if sys.version_info < (3, 9):
        print("ERROR: se necesita Python 3.9 o superior (recomendado 3.11 o 3.12).")
        return 2
    if importlib.util.find_spec("tkinter") is None:
        print("ERROR: este Python no tiene tkinter (la librería de ventanas).")
        print("Reinstale Python desde python.org marcando la opción 'tcl/tk and IDLE'.")
        return 2
    faltan, viejos = [], []
    for mod, pkg, minimo in (("numpy", "numpy", (1, 24)), ("scipy", "scipy", (1, 10)),
                             ("matplotlib", "matplotlib", (3, 5)), ("fpdf", "fpdf2", (2, 7))):
        if importlib.util.find_spec(mod) is None:
            faltan.append(pkg)
            print(f"  FALTA      {pkg}")
            continue
        v = version(mod)
        if vt(v) < minimo:
            viejos.append(pkg)
            print(f"  ANTIGUO    {pkg} {v} (se necesita >= {'.'.join(map(str, minimo))})")
        else:
            print(f"  correcto   {pkg} {v}")
    if faltan or viejos:
        if "fpdf2" in viejos:
            print("  Nota: hay instalado el paquete antiguo 'fpdf' (PyFPDF). fpdf2 lo sustituye.")
        print("Faltan o están desactualizados: " + ", ".join(faltan + viejos))
        return 1
    print("Entorno correcto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
