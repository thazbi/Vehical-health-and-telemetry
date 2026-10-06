$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $launcher) {
        throw "Python 3.11 is required. Install Python 3.11, then run this launcher again."
    }

    Write-Host "Creating the project Python 3.11 environment..." -ForegroundColor Cyan
    & py -3.11 -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create .venv. Confirm Python 3.11 is installed (py -3.11 --version)."
    }
}

Write-Host "Checking/installing the project's pinned Python dependencies..." -ForegroundColor Cyan
& $python -m pip install -r requirements-dev.txt -r services/vehicle_service/requirements.txt -r services/telemetry_service/requirements.txt -r services/alert_service/requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Dependency setup failed. Check your internet connection and Python 3.11 installation."
}

Write-Host "Starting the local services and opening the live project dashboard..." -ForegroundColor Green
& $python scripts/demo_host.py
if ($LASTEXITCODE -ne 0) {
    throw "The local demo host exited with an error. Review the output above."
}
