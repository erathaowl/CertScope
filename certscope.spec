# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata


block_cipher = None
assets = [(str(Path('assets/certscope.png').resolve()), 'assets')]
assets += [(str(file), 'certscope/assets') for file in Path('src/certscope/assets').glob('*') if file.is_file()]
assets += copy_metadata('certscope')
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
def build_executable(name, console):
    return EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
        icon='assets/certscope.ico',
        version=str(Path('build') / f'{name}-version.txt'),
    )


# The GUI must use the Windows subsystem; the CLI needs a real console.
gui_exe = build_executable('certscope', console=False)
cli_exe = build_executable('certscope-cli', console=True)
