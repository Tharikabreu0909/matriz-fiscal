from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('uvicorn') + collect_submodules('pdfplumber')

a = Analysis(
    ['desktop_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static')],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CheckFiscal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='CheckFiscal',
)
