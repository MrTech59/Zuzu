# Zuzu development startup (Windows).
# Starts the API with the mock provider and SQLite by default.
param(
    [string]$Host = '0.0.0.0'
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

$devIp = $Host
if ($Host -eq '0.0.0.0') {
    $devIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'
    } | Select-Object -First 1).IPAddress
    if (-not $devIp) { $devIp = 'localhost' }
}

Write-Host "== Zuzu dev: applying migrations =="
python -m alembic upgrade head

Write-Host "== Zuzu dev: starting API on ${Host}:8000 (reachable at http://${devIp}:8000) =="
python -m uvicorn zuzu.main:app --host $Host --port 8000 --loop zuzu.db.engine:selector_loop_factory
