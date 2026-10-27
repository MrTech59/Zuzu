#Requires -Version 5.1
<#
.SYNOPSIS
    Unified Zuzu install script.
.DESCRIPTION
    Asks whether to install the Docker Compose stack (PostgreSQL + NVIDIA
    live-chat ready) or the host development environment (SQLite + mock
    provider, no Docker required), then runs the appropriate setup script.

    Non-interactive usage:
      .\scripts\install.ps1 -Docker    # Docker Compose setup
      .\scripts\install.ps1 -Host      # Host development setup
      .\scripts\install.ps1 -Docker -SkipBuild
#>
param(
    [switch]$UseDocker,
    [switch]$UseHost,
    [switch]$SkipBuild,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
Set-Location $ProjectRoot

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

$useDocker = $UseDocker
$useHost = $UseHost

if (-not $useDocker -and -not $useHost) {
    Write-Host @"

How would you like to run Zuzu?

  [H] Host development (SQLite + mock AI provider, no Docker)
  [D] Docker Compose (PostgreSQL + NVIDIA live-chat ready)
"@
    $choice = Read-Host "Enter H or D (default H)"
    switch -Regex ($choice.Trim().ToUpper()) {
        'D' { $useDocker = $true }
        default { $useHost = $true }
    }
}

if ($useDocker) {
    if (-not (Test-Command 'docker')) {
        throw 'Docker is required for the Docker Compose path. Install Docker Desktop from https://www.docker.com/products/docker-desktop/'
    }
    $skip = if ($SkipBuild) { '-SkipBuild' } else { '' }
    $cmd = "& '$ProjectRoot\scripts\setup.ps1' $skip".TrimEnd()
    Write-Host "Running Docker Compose setup..."
    Invoke-Expression $cmd
} else {
    $cmd = "& '$ProjectRoot\scripts\dev-setup.ps1'"
    if ($SkipBuild) {
        Write-Warning '-SkipBuild is only used by the Docker path; ignoring.'
    }
    Write-Host "Running host development setup..."
    Invoke-Expression $cmd
}
