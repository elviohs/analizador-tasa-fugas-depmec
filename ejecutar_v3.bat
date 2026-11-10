@echo off
setlocal
REM ==================================================================
REM  Analizador de fugas DEPMEC v3 - arranque desde el codigo fuente
REM  1) busca Python  2) comprueba paquetes (ofrece instalarlos)
REM  3) abre el programa y, si falla, deja el error en pantalla
REM ==================================================================
cd /d "%~dp0"
title Analizador de fugas DEPMEC v3

set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY (python -c "import sys" >nul 2>&1 && set "PY=python")
if not defined PY goto sinpython

echo Comprobando el entorno de Python...
%PY% comprobar_entorno.py
if errorlevel 2 goto fallo
if not errorlevel 1 goto arrancar

echo.
choice /C SN /M "Instalar ahora con pip los paquetes que faltan, solo para su usuario"
if errorlevel 2 goto fallo
%PY% -m pip install --user --upgrade -r requirements.txt
echo.
%PY% comprobar_entorno.py
if errorlevel 1 goto fallo

:arrancar
echo.
echo Abriendo el analizador. No cierre esta ventana mientras lo use.
%PY% analizador_fugas_v3.py %*
if errorlevel 1 goto fallo
exit /b 0

:sinpython
echo.
echo No se encuentra Python en este equipo.
echo Instale Python 3.11 o 3.12 desde https://www.python.org
echo marcando la casilla "Add python.exe to PATH", y vuelva a ejecutar este fichero.
goto fin

:fallo
echo.
echo *** El analizador no ha podido arrancar: revise los mensajes de arriba. ***
if exist "%~dp0error_v3.log" echo Detalle guardado en %~dp0error_v3.log
echo Si pip no puede descargar paquetes, puede ser el proxy de la red: consulte con Informatica.

:fin
echo.
pause
exit /b 1
