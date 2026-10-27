# Zuzu check runner (Windows): lint + typecheck + backend tests.

$ErrorActionPreference = 'Continue'
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "== ruff lint =="
python -m ruff check apps/api/src tests migrations scripts
Write-Host "== mypy =="
python -m mypy apps/api/src
Write-Host "== pytest =="
python -m pytest tests -q
