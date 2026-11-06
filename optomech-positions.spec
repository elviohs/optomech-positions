# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist/optomech-positions(.exe), un único ejecutable con interfaz gráfica.
# Uso:  pyinstaller --noconfirm --clean optomech-positions.spec

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=[],
    datas=[("materiales.json", ".")],
    hiddenimports=["openpyxl"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["numpy", "pandas", "matplotlib", "PIL", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="optomech-positions",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # sin ventana de consola
    disable_windowed_traceback=False,
)
