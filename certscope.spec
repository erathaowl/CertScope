# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


block_cipher = None
assets = [(str(Path('assets/certscope.png').resolve()), 'assets')]
assets += [(str(file), 'certscope/assets') for file in Path('src/certscope/assets').glob('*') if file.is_file()]
a = Analysis(
    ['launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=assets,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CertScope',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon='assets/certscope.ico',
)
