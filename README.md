<img src="logo_depmec.png" alt="IAC DEPMEC" width="260">

# Analizador de tasa de fugas DEPMEC (v3)

Herramienta de escritorio para analizar **ensayos de subida de presión** (*rate-of-rise*) en criostatos de vacío a partir de los registros del **CryoMonitor** (galgas Pfeiffer de rango completo). Distingue, cuando los datos lo permiten, entre **fuga real** y **desgasificación**, y da siempre una **cota superior de la fuga**.

Desarrollada en la Línea de Vacío y Criogenia del Departamento de Mecánica (DEPMEC) del Instituto de Astrofísica de Canarias. Está basada en el prototipo V1/V2 de Haroldo.

> **Software en pruebas.** Revise los resultados y confirme los críticos con un detector de helio.

## Descarga (Windows)

Descargue `DET_FUGAS_IAC_V3.exe` desde **[Releases](https://github.com/elviohs/analizador-tasa-fugas-depmec/releases/latest)**. No hace falta instalar Python. El ejecutable no está firmado, así que Windows SmartScreen puede pedir confirmación la primera vez («Más información → Ejecutar de todas formas»).

## Qué hace

- **Lee los ficheros del CryoMonitor tal cual.** Toma las columnas de la cabecera y usa fecha y hora como base de tiempos. Tolera huecos, duplicados, valores no numéricos y coma decimal.
- **Admite varios ficheros y varios ensayos a la vez.** Cada cierre de válvula detectado es un ensayo de la lista.
- **Detecta el ensayo automáticamente:** el cierre de la válvula (confirmado con el sensor del lado turbo) y el final (venteo o re-bombeo). También propone qué sensor es la cámara y cuál el lado turbo.
- **Preprocesa los datos:** corrige el escalón de la galga al cambiar de Pirani a cátodo frío (~5e-3 mbar), elimina picos aislados y excluye el transitorio inicial.
- **Da un resultado principal sin modelo:**
  - dP/dt en ventanas a lo largo del ensayo.
  - Cota superior de la fuga: dP/dt final + 2σ.
  - Tendencia β (dP/dt ∝ t^β): ≈ 0 indica fuga dominante; ≈ −1 o menor, desgasificación dominante.
- **Hace una estimación secundaria con modelos:** exponencial, doble exponencial, potencia y logarítmico, con y sin fuga. Compara los modelos por AIC, da intervalos de confianza y avisa de los casos «no separable», «compatible con 0» o «inconsistente».
- **Avisa de ensayos no estacionarios,** de la zona Pirani (lectura dependiente del gas) y de variaciones de temperatura si se carga ese fichero.
- **Aplica un criterio de aceptación:** APTO / NO APTO / NO CONCLUYENTE a partir del volumen (± incertidumbre) y el caudal admisible.
- **Calcula la carga de gas por superficie:** con el volumen y la superficie interna, q = V·(dP/dt)/A en mbar·L·s⁻¹·cm⁻² y Pa·m³·s⁻¹·m⁻² (desgasificación específica, o una cota de ella si hay fuga).
- **Compara ensayos repetidos:** misma dP/dt a igual tiempo desde el cierre indica fuga; dP/dt menor indica desgasificación.
- **Genera un informe PDF en español o en inglés,** de uno o varios ensayos, con tabla resumen, gráficas, modelos y trazabilidad (SHA-256 del fichero, ventana analizada, configuración y versión). También exporta a CSV.
- **Exporta las gráficas para publicaciones** en español o en inglés: PNG a 300 ppp, PDF, EPS y SVG.

## Uso

1. Pulse **Añadir ficheros…** y seleccione uno o varios registros del CryoMonitor.
2. Revise en la pestaña **Datos** la ventana detectada. Puede corregirla arrastrando con el ratón o escribiendo las fechas.
3. Introduzca, si los conoce, el volumen y el caudal admisible. **Copiar criterio y opciones a todos** los aplica a toda la lista.
4. Pulse **ANALIZAR** o **Analizar todos**.
5. Revise **Resultado** y **dP/dt**. Para ensayos repetidos del mismo sistema, selecciónelos con Ctrl+clic y pulse **Comparar seleccionados**.
6. Pulse **Generar informe… (ES / EN)**.

## Ejecutar desde el código

Requiere Python 3.10 a 3.12 con tkinter (incluido en el instalador de python.org).

```bat
py -m pip install -r requirements.txt
py analizador_fugas_v3.py
```

En Windows, `ejecutar_v3.bat` comprueba el entorno, ofrece instalar los paquetes que falten y arranca el programa.

## Tests

```bat
py -m pip install pytest
py -m pytest -q tests
```

Los tests usan curvas sintéticas con fuga conocida. Comprueban, entre otras cosas, que la cota superior nunca queda por debajo de la fuga real. Los tests con ficheros reales se saltan si no está la carpeta `Ejemplos de datos`.

## Compilar el ejecutable

- **En local:** `build_exe.bat` crea un entorno aislado, pasa los tests y genera `dist\DET_FUGAS_IAC_V3.exe` con PyInstaller.
- **En GitHub:** el flujo `.github/workflows/compilar-exe.yml` compila en Windows cada vez que se sube una etiqueta `v*`. Antes de publicar el `.exe` en Releases, lo prueba con `--autotest` (análisis y PDF sin ventanas).

## Estructura

| Fichero | Contenido |
|---|---|
| `nucleo_fugas.py` | Lectura, detección, análisis, modelos y criterio. No depende de la interfaz. |
| `graficos.py` | Gráficas, compartidas por la ventana y el informe. |
| `informe_pdf.py` | Informe PDF de uno o varios ensayos (ES/EN). |
| `textos.py` | Textos traducibles español/inglés. |
| `analizador_fugas_v3.py` | Interfaz gráfica (Tkinter + matplotlib). |
| `comprobar_entorno.py` | Comprobación de dependencias que usa `ejecutar_v3.bat`. |
| `logo_depmec.png`, `icono.png`, `icono.ico` | Logo del Departamento de Mecánica (informe y ventana) e icono del ejecutable. |
| `tests/` | Tests automáticos (pytest). |

## Limitaciones

- Con una sola curva, fuga y desgasificación suelen no ser separables. En ese caso el programa lo indica y la referencia es la cota superior.
- Por encima de ~1e-2 mbar la galga de rango completo mide con la Pirani, cuya lectura depende del gas.
- Los cambios de temperatura durante el ensayo alteran la presión y la desgasificación.
- Si la presión baja al final del ensayo (criobombeo, readsorción, válvula que no cierra), la subida no acota la fuga: el programa da «no acotable» y NO CONCLUYENTE.
- El cambio de hora se corrige para las fechas oficiales de la UE (último domingo de marzo y de octubre).
- El formato del fichero de temperaturas del CryoMonitor se ha supuesto igual al de presiones y está pendiente de validar con un fichero real.
- Los umbrales de clasificación de β (−0,2 y −0,6) son empíricos y conviene validarlos con más ensayos.

## Referencias

- Leybold, *Pressure rise and drop tests* (fundamentos de detección de fugas).
- Pfeiffer Vacuum, *Pressure Decay Methods* (Knowledge Hub, 2026).
- EN 13184: Ensayos no destructivos. Ensayo de fugas. Método de cambio de presión.

Historial de cambios: [CHANGELOG.md](CHANGELOG.md).
