# -*- mode: python ; coding: utf-8 -*-
"""Independent PyInstaller onefile builds for Qt GUI and headless CLI."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata


common_datas = copy_metadata('certscope')
common_binaries = []
common_hiddenimports = []
for package in ('pkilint', 'pyasn1_fasder', 'iso4217', 'iso3166', 'iso639',
                'publicsuffixlist'):
    data, binaries, hiddenimports = collect_all(package)
    common_datas += data
    common_binaries += binaries
    common_hiddenimports += hiddenimports

gui_datas = common_datas + [
    (str(Path('assets/certscope.png').resolve()), 'assets'),
    *((str(file), 'certscope/assets') for file in Path('src/certscope/assets').glob('*')
      if file.is_file()),
]


def build_executable(entrypoint, name, console, datas, excludes):
    analysis = Analysis(
        [entrypoint],
        pathex=['src'],
        binaries=common_binaries,
        datas=datas,
        hiddenimports=common_hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=excludes,
        noarchive=False,
    )
    archive = PYZ(analysis.pure)
    return EXE(
        archive,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
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


gui_exe = build_executable('gui_launcher.py', 'certscope', False, gui_datas, [])
cli_exe = build_executable(
    'cli_launcher.py', 'certscope-cli', True, common_datas, ['PySide6', 'shiboken6']
)
