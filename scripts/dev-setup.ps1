#Requires -Version 5.1
<#
.SYNOPSIS
    One-time Zuzu host development setup for Windows.
.DESCRIPTION
    Installs Python and Node dependencies, creates .env from .env.example
    with generated secrets, and prints the commands needed to start the
    API and web dev servers.

    This uses SQLite and the mock AI provider by default, so no Docker or
    external database is required. For Docker Compose deployment, use
    scripts/setup.ps1.
#>
param(
    [switch]$Force,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
Set-Location $ProjectRoot

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command 'python')) {
    if (Test-Command 'py') { $python = 'py' } else {
        throw 'Python 3.12+ is required. Install from https://www.python.org/downloads/'
    }
} else { $python = 'python' }

if (-not (Test-Command 'node')) { throw 'Node.js is required. Install from https://nodejs.org/' }
if (-not (Test-Command 'npm')) { throw 'npm is required (included with Node.js).' }

$major = & $python -c 'import sys; print(sys.version_info.major * 10 + sys.version_info.minor)'
if ($major -lt 312) { throw 'Python 3.12 or newer is required.' }

$envFile = Join-Path $ProjectRoot '.env'
$exampleFile = Join-Path $ProjectRoot '.env.example'

if (-not (Test-Path $exampleFile)) { throw '.env.example not found.' }

$example = Get-Content -Raw $exampleFile
$generate = $false

if (Test-Path $envFile) {
    if ($Force) {
        Write-Host '.env exists but -Force supplied; regenerating secrets.'
        $generate = $true
    } else {
        Write-Host '.env already exists; preserving existing secrets.'
    }
} else {
    $generate = $true
}

if ($generate) {
    $apiKey = & $python -c 'import secrets; print(secrets.token_urlsafe(32))'

    $content = $example
    $content = $content -replace '(?m)^ZUZU_API_KEY=.*$', "ZUZU_API_KEY=$apiKey"
    # Normalize to LF and ensure trailing newline.
    $content = ($content -replace "`r`n", "`n").TrimEnd() + "`n"
    $content | Set-Content -NoNewline -Path $envFile -Encoding UTF8
    Write-Host '.env created with generated secrets (SQLite + mock provider by default).'
} else {
    # Ensure .env uses LF line endings even if it was edited on Windows.
    $content = (Get-Content -Raw $envFile) -replace "`r`n", "`n"
    $content.TrimEnd() + "`n" | Set-Content -NoNewline -Path $envFile -Encoding UTF8
}

$content = Get-Content -Raw $envFile
if ($content -match '@db:5432') {
    Write-Warning 'DATABASE_URL still points to the Docker hostname (@db:5432).'
    Write-Host "Host dev will not start until you update it or re-run with -Force." -ForegroundColor Yellow
}

Write-Host 'Installing Python dependencies...'
& $python -m pip install -e ".[dev]"

Write-Host 'Installing Node dependencies...'
Push-Location (Join-Path $ProjectRoot 'apps/web')
& npm install
Pop-Location

Write-Host @"

Setup complete. Next steps:

1. Start the API dev server:
     scripts\dev.ps1

2. In another terminal, start the web dev server:
     cd apps\web
     npm run dev

Web UI: http://localhost:3000
API:    http://127.0.0.1:8000/api/v1/health

To use live NVIDIA chat instead of the mock provider, set AI_PROVIDER=nvidia
and NVIDIA_API_KEY in .env, then restart the API. For a full Docker Compose
stack with PostgreSQL, run scripts\setup.ps1.
"@
