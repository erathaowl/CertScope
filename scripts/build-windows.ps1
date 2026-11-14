$ErrorActionPreference = 'Stop'

if ($env:CERTSCOPE_VERSION) {
    uv run --no-project python scripts/set-release-version.py $env:CERTSCOPE_VERSION
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

uv sync --group dev
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run python scripts/build_nuitka.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& '.\dist\certscope-cli.exe' --help
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run python scripts/smoke-frozen-lint.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$previousPlatform = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = 'offscreen'
$guiProcess = Start-Process -FilePath '.\dist\certscope.exe' -PassThru -WindowStyle Hidden
try {
    Start-Sleep -Seconds 10
    $guiProcess.Refresh()
    if ($guiProcess.HasExited) {
        throw "Frozen Nuitka GUI exited prematurely: $($guiProcess.ExitCode)"
    }
    Write-Host 'Nuitka GUI started successfully'
} finally {
    if (!$guiProcess.HasExited) { Stop-Process -Id $guiProcess.Id -Force }
    $env:QT_QPA_PLATFORM = $previousPlatform
}

uv run python scripts/check_nuitka.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run python -m certscope.windows_package
exit $LASTEXITCODE
