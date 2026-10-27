#Requires -Version 5.1
<#
.SYNOPSIS
    Unified Zuzu install script.
.DESCRIPTION
    Asks whether to install the Docker Compose stack (PostgreSQL + NVIDIA
    live-chat ready) or the host development environment (SQLite + mock
    provider, no Docker required), then runs the appropriate setup script.

    On Windows, the host path can install Python 3.12 and Node.js via winget
    when the script is run as Administrator.

    Non-interactive usage:
      .\scripts\install.ps1 -UseDocker    # Docker Compose setup
      .\scripts\install.ps1 -UseHost      # Host development setup
      .\scripts\install.ps1 -UseDocker -SkipBuild
      .\scripts\install.ps1 -Update -UseHost
#>
param(
    [switch]$UseDocker,
    [switch]$UseHost,
    [switch]$SkipBuild,
    [switch]$Update,
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
Set-Location $ProjectRoot

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-PythonVersion($Cmd) {
    try {
        $output = & $Cmd --version 2>&1
        if ($output -match 'Python\s+(\d+)\.(\d+)') {
            return [version]"$($matches[1]).$($matches[2])"
        }
    } catch {}
    return $null
}

function Install-WithWinget($Id) {
    Write-Host "Installing $Id via winget..."
    & winget install --id $Id --accept-source-agreements --accept-package-agreements --silent
    if ($LASTEXITCODE -ne 0) { throw "winget install $Id failed" }
}

function Install-Prereqs {
    $needs = @()

    $pythonCmds = @('python3', 'python')
    $pythonOk = $false
    foreach ($cmd in $pythonCmds) {
        if (Test-Command $cmd) {
            $ver = Get-PythonVersion $cmd
            if ($ver -and $ver.Major -eq 3 -and $ver.Minor -ge 12) {
                $pythonOk = $true
                break
            }
        }
    }
    if (-not $pythonOk) { $needs += 'Python 3.12+' }

    if (-not (Test-Command 'node')) { $needs += 'Node.js' }
    if (-not (Test-Command 'npm')) { $needs += 'npm' }

    if ($needs.Count -eq 0) { return }

    Write-Host "Missing prerequisites: $($needs -join ', ')" -ForegroundColor Yellow

    if (-not (Test-Command 'winget')) {
        Write-Host 'Install manually, then re-run this script:' -ForegroundColor Yellow
        Write-Host '  Python: https://www.python.org/downloads/ (3.12+)' -ForegroundColor Cyan
        Write-Host '  Node.js: https://nodejs.org/' -ForegroundColor Cyan
        throw 'Prerequisites missing and winget is unavailable.'
    }

    if (-not (Test-Admin)) {
        Write-Host 'Run this script as Administrator to install prerequisites automatically, or install them manually:' -ForegroundColor Yellow
        Write-Host '  Python: https://www.python.org/downloads/ (3.12+)' -ForegroundColor Cyan
        Write-Host '  Node.js: https://nodejs.org/' -ForegroundColor Cyan
        throw 'Administrator privileges required to install prerequisites.'
    }

    if (-not $pythonOk) {
        Install-WithWinget 'Python.Python.3.12'
        # Refresh PATH so subsequent checks see the new Python.
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    }
    if (-not (Test-Command 'node')) {
        Install-WithWinget 'OpenJS.NodeJS'
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    }

    # Final verification.
    $pythonOk = $false
    foreach ($cmd in $pythonCmds) {
        if (Test-Command $cmd) {
            $ver = Get-PythonVersion $cmd
            if ($ver -and $ver.Major -eq 3 -and $ver.Minor -ge 12) {
                $pythonOk = $true
                break
            }
        }
    }
    if (-not $pythonOk -or -not (Test-Command 'node') -or -not (Test-Command 'npm')) {
        throw 'Prerequisites still missing after install. Restart the terminal and re-run.'
    }
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

if ($Update -and -not $useDocker -and -not $useHost) {
    $useHost = $true
}

if ($Update) {
    Write-Host "Pulling latest code..."
    & git -C $ProjectRoot pull origin main
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
    if ($SkipBuild) {
        Write-Warning '-SkipBuild is only used by the Docker path; ignoring.'
    }
    Install-Prereqs
    $cmd = "& '$ProjectRoot\scripts\dev-setup.ps1'"
    Write-Host "Running host development setup..."
    Invoke-Expression $cmd
}
