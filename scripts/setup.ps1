#Requires -Version 5.1
<#
.SYNOPSIS
    One-time Zuzu setup for Windows.
.DESCRIPTION
    Creates .env from .env.example with generated secrets, builds the Docker
    Compose images, and starts the stack. Re-running is safe: existing .env
    secrets are preserved unless -Force is used.
#>
param(
    [switch]$Force,
    [switch]$SkipBuild,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
Set-Location $ProjectRoot

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command 'docker')) { throw 'docker is required.' }
$python = if (Test-Command 'python') { 'python' } elseif (Test-Command 'py') { 'py' } else { throw 'python is required.' }

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
    $pgPassword = & $python -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))"

    $content = $example
    $content = $content -replace '(?m)^AI_PROVIDER=.*$', "AI_PROVIDER=nvidia"
    $content = $content -replace '(?m)^ZUZU_API_KEY=.*$', "ZUZU_API_KEY=$apiKey"
    $content = $content -replace '(?m)^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$pgPassword"
    # Point DATABASE_URL at the Docker Compose database service.
    $content = $content -replace '(?m)^DATABASE_URL=.*$', "DATABASE_URL=postgresql+psycopg://zuzu:$pgPassword@db:5432/zuzu"
    # Normalize to LF and ensure trailing newline.
    $content = ($content -replace "`r`n", "`n").TrimEnd() + "`n"
    $content | Set-Content -NoNewline -Path $envFile -Encoding UTF8
    Write-Host '.env created with generated secrets (database host set to db).'
} else {
    # Ensure .env uses LF line endings even if it was edited on Windows.
    $content = (Get-Content -Raw $envFile) -replace "`r`n", "`n"
    $content.TrimEnd() + "`n" | Set-Content -NoNewline -Path $envFile -Encoding UTF8
    $content = Get-Content -Raw $envFile
    if ($content -match '@127\.0\.0\.1:5432|sqlite') {
        Write-Warning 'DATABASE_URL appears to point to a host database or SQLite.'
        Write-Host "Run with -Force to regenerate a Docker Compose .env, or update DATABASE_URL manually." -ForegroundColor Yellow
    }
}

if ($SkipBuild) {
    Write-Host 'Skipping Docker Compose build because -SkipBuild was specified.'
} else {
    Write-Host 'Building Docker Compose images...'
    docker compose build

    Write-Host 'Starting Zuzu stack...'
    docker compose up -d

    Write-Host "Zuzu is starting."
    Write-Host "  Web UI:   http://127.0.0.1:3000"
    Write-Host "  API:      http://127.0.0.1:8000/api/v1/health"
    Write-Host "To inspect logs: docker compose logs -f"
}
