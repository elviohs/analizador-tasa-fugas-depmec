# Historial de cambios

## v3.2.0 (noviembre 2026)

- **Carga de gas específica.** Nuevo campo **Superficie interna (cm²)**. Con el volumen y la superficie se calcula q = V·(dP/dt)/A al final del ensayo, en mbar·L·s⁻¹·cm⁻² y en Pa·m³·s⁻¹·m⁻², con su incertidumbre y su cota. Aparece en el resultado, en el informe PDF y en el CSV.
- **Exportar gráficas…** dP/dt, subida P(t), serie completa con temperaturas y, con dos o más ensayos seleccionados, la comparación. En español o en inglés; PNG a 300 ppp, PDF, EPS y SVG.
- **Aviso** si el fichero de temperaturas no coincide en fechas con el de presiones.
- **Gráficas más legibles:** la leyenda de dP/dt ya no tapa la cota y la etiqueta «cierre» ya no se superpone a la leyenda.

## v3.1.0 (noviembre 2026)

- **Varios ensayos a la vez.**
  - **Añadir ficheros…** admite selección múltiple, y cada cierre de válvula detectado es un ensayo de la lista (un mismo fichero puede tener varios).
  - Cada ensayo guarda su ventana, sus sensores, su criterio y sus opciones.
  - Nuevos botones **Analizar todos** y **Copiar criterio y opciones a todos**. Los ensayos se renombran con doble clic.
- **Comparar seleccionados:** compara los ensayos marcados en la lista.
- **Generar informe… (ES / EN):**
  - Informe PDF en español o en inglés del ensayo actual, de los seleccionados o de todos.
  - Incluye tabla resumen y, opcionalmente, la comparación entre ensayos.
  - Analiza antes los ensayos que falten.
- **Detección más robusta.** Descarta los falsos cierres causados por caídas momentáneas del sensor de la turbo y las ventanas en las que la cámara no sube.
- **Modo `--autotest`:** análisis y PDF sin ventanas, usado por la compilación automática.

## v3.0.1

- **`ejecutar_v3.bat` más robusto:**
  - Busca Python (`py -3` o `python`).
  - Comprueba los paquetes con `comprobar_entorno.py` y ofrece instalar los que falten.
  - Si algo falla, deja la ventana abierta con el error.
- **El programa abre aunque falte `fpdf2`,** que solo se necesita para el informe PDF.
- **Errores de arranque visibles:** si el arranque falla, se muestra el error y se guarda en `error_v3.log`.

## v3.0.0 (versión inicial de la v3)

Rehecha a partir de la revisión del prototipo V1/V2.

- **Diagnóstico:**
  - El resultado principal se calcula sin modelo: la cota superior de la fuga es dP/dt final + 2σ.
  - Se añaden dP/dt en ventanas logarítmicas y el exponente β al final del ensayo.
  - Se sustituyen el criterio R² ≥ 0,92 (V1) y el criterio A > L·T (V2).
  - La fuga solo se estima si es separable de la desgasificación. Si no lo es, se indica.
  - Modelos P(t) con parámetros escalados, varios puntos de partida, τ ≤ T, AIC, IC de L y avisos.
  - Si un ajuste falla, ya no se diagnostica «fuga» por defecto.
  - Se detectan los ensayos no estacionarios.
  - Criterio APTO / NO APTO / NO CONCLUYENTE.
  - Comparación de ensayos repetidos.
- **Datos:**
  - Columnas leídas de la cabecera y tiempo por fecha y hora.
  - Detección del cierre (confirmado con el lado turbo) y del final del ensayo.
  - Corrección del escalón Pirani/cátodo frío, eliminación de picos y exclusión del transitorio inicial.
  - Avisos de zona Pirani y de unidades. Fichero de temperaturas opcional.
- **Software:**
  - Cálculo separado de la interfaz, tests automáticos e informe PDF trazable.
  - Exportación CSV y análisis en segundo plano.
