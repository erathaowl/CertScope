$ErrorActionPreference = 'Stop'
uv sync --group dev
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run pyinstaller --noconfirm --clean certscope.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& '.\dist\CertScope.exe' --help
exit $LASTEXITCODE
