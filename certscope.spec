# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata


block_cipher = None
assets = [(str(Path('assets/certscope.png').resolve()), 'assets')]
assets += [(str(file), 'certscope/assets') for file in Path('src/certscope/assets').glob('*') if file.is_file()]
assets += copy_metadata('certscope')
pkilint_datas, pkilint_binaries, pkilint_hiddenimports = collect_all('pkilint')
fasder_datas, fasder_binaries, fasder_hiddenimports = collect_all('pyasn1_fasder')
assets += pkilint_datas + fasder_datas
a = Analysis(
    ['launcher.py'],
    pathex=['src'],
    binaries=pkilint_binaries + fasder_binaries,
    datas=assets,
    hiddenimports=pkilint_hiddenimports + fasder_hiddenimports,
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
