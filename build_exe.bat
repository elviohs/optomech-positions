@echo off
REM ============================================================
REM  Genera el ejecutable dist\optomech-positions.exe (PyInstaller)
REM  Solo lo necesita quien prepara versiones; los usuarios usan el .exe.
REM ============================================================
set PYTHON_PATH=

cd /d "%~dp0"
if defined PYTHON_PATH (
    set "PY=%PYTHON_PATH%"
) else (
    where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo No se encuentra Python 3.
    pause
    exit /b 1
)

%PY% -m pip install -r requirements.txt pyinstaller --quiet --disable-pip-version-check
%PY% -m PyInstaller --noconfirm --clean optomech-positions.spec
if errorlevel 1 (
    echo ERROR al generar el ejecutable.
    pause
    exit /b 1
)
copy /Y materiales.json dist\ >nul
echo.
echo Ejecutable generado: dist\optomech-positions.exe
echo (materiales.json se ha copiado al lado para poder editarlo)
pause
