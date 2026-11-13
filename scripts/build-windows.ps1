$ErrorActionPreference = 'Stop'
uv sync --group dev
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run pyinstaller --noconfirm --clean certscope.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& '.\dist\CertScope-CLI.exe' --help
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (!(Test-Path '.\dist\CertScope.exe')) { throw 'GUI executable missing' }
if (!(Test-Path '.\dist\CertScope-CLI.exe')) { throw 'CLI executable missing' }

uv run python -c "import pefile; from pathlib import Path; p = Path('dist'); assert pefile.PE(str(p / 'CertScope.exe')).OPTIONAL_HEADER.Subsystem == 2; assert pefile.PE(str(p / 'CertScope-CLI.exe')).OPTIONAL_HEADER.Subsystem == 3"
exit $LASTEXITCODE
