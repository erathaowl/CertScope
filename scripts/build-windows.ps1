$ErrorActionPreference = 'Stop'
if ($env:CERTSCOPE_VERSION) {
    uv run --no-project python scripts/set-release-version.py $env:CERTSCOPE_VERSION
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
uv sync --group dev
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run python -m certscope.version_info
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run pyinstaller --noconfirm --clean certscope.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& '.\dist\certscope-cli.exe' --help
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (!(Test-Path '.\dist\certscope.exe')) { throw 'GUI executable missing' }
if (!(Test-Path '.\dist\certscope-cli.exe')) { throw 'CLI executable missing' }

uv run python -c "import pefile; from pathlib import Path; p = Path('dist'); gui = pefile.PE(str(p / 'certscope.exe')); cli = pefile.PE(str(p / 'certscope-cli.exe')); assert gui.OPTIONAL_HEADER.Subsystem == 2; assert cli.OPTIONAL_HEADER.Subsystem == 3; assert gui.VS_FIXEDFILEINFO[0].FileVersionMS == cli.VS_FIXEDFILEINFO[0].FileVersionMS; assert any(entry.get(b'ProductName') == b'CertScope' for info in gui.FileInfo for section in info for table in getattr(section, 'StringTable', []) for entry in [table.entries])"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run python -m certscope.windows_package
exit $LASTEXITCODE
