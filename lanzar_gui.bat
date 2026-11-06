@echo off
REM ============================================================
REM  Posiciones optomecanicas - Zemax / CREO / ANSYS
REM  - Funciona desde cualquier carpeta (local o red).
REM  - Busca Python automaticamente. Si tienes varios, pon la ruta
REM    completa en PYTHON_PATH (ej: C:\...\Python311\python.exe).
REM  - Puedes arrastrar un perfil .json encima de este .bat.
REM ============================================================
set PYTHON_PATH=

cd /d "%~dp0"
if defined PYTHON_PATH (
    set PY="%PYTHON_PATH%"
) else (
    where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo No se encuentra Python 3. Instalalo desde python.org marcando "Add to PATH".
    pause
    exit /b 1
)

%PY% -m pip install openpyxl --quiet --disable-pip-version-check
%PY% "%~dp0gui.py" %*
if errorlevel 1 pause
