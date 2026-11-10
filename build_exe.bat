@echo off
setlocal
REM ==================================================================
REM  Compila DET_FUGAS_IAC_V3.exe (Windows, un solo fichero)
REM  Requisitos: Python 3.10-3.12. El .exe queda en la carpeta dist
REM ==================================================================
cd /d "%~dp0"
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY (python -c "import sys" >nul 2>&1 && set "PY=python")
if not defined PY goto sinpython

if not exist .venv_build %PY% -m venv .venv_build
if errorlevel 1 goto error
call .venv_build\Scripts\activate.bat
if errorlevel 1 goto error
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller pytest
if errorlevel 1 goto error
echo.
echo === Ejecutando tests ===
python -m pytest -q tests
if errorlevel 1 goto error
echo.
echo === Compilando ===
pyinstaller --noconfirm --clean --onefile --windowed --name DET_FUGAS_IAC_V3 --icon icono.ico --add-data "logo_depmec.png;." --add-data "icono.png;." analizador_fugas_v3.py
if errorlevel 1 goto error
echo.
echo Ejecutable generado: %~dp0dist\DET_FUGAS_IAC_V3.exe
pause
exit /b 0

:sinpython
echo No se encuentra Python. Instalelo desde https://www.python.org y repita.
:error
echo.
echo *** ERROR durante la compilacion: revise los mensajes de arriba ***
pause
exit /b 1
