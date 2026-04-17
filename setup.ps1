#Requires -Version 5.1
<#
.SYNOPSIS
    cmake-ctl setup script for Windows.
    Adds the bin folder to PATH and optionally configures VSCode settings.

.PARAMETER Scope
    PATH scope: User (default) or Machine (requires admin).

.PARAMETER VSCode
    Write cmake.cmakePath into VSCode user settings.json.

.PARAMETER Uninstall
    Remove cmake-ctl from PATH and VSCode settings.

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -VSCode
    .\setup.ps1 -Scope Machine -VSCode
    .\setup.ps1 -Uninstall
#>
param(
    [ValidateSet("User","Machine")]
    [string]$Scope = "User",
    [switch]$VSCode,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$BinDir = Join-Path $PSScriptRoot "bin"
$ProxyExe = Join-Path $BinDir "cmake.exe"

# ── helpers ──────────────────────────────────────────────────────────────────
function Write-OK   { param([string]$m) Write-Host "  [OK] $m" -ForegroundColor Green }
function Write-Info { param([string]$m) Write-Host "  [..] $m" -ForegroundColor Cyan }
function Write-Warn { param([string]$m) Write-Host "  [!!] $m" -ForegroundColor Yellow }
function Write-Fail { param([string]$m) Write-Host "  [XX] $m" -ForegroundColor Red }

function Get-VSCodeSettingsPath {
    # Standard locations for VSCode user settings on Windows
    $candidates = @(
        "$env:APPDATA\Code\User\settings.json",
        "$env:APPDATA\Code - Insiders\User\settings.json"
    )
    # Also check scoop-installed VSCode (data\user-data\User\settings.json sibling to the exe)
    $codeExe = Get-Command "code" -ErrorAction SilentlyContinue
    if ($codeExe) {
        $scoopData = Join-Path (Split-Path (Split-Path $codeExe.Source)) "data\user-data\User\settings.json"
        $candidates = @($scoopData) + $candidates
    }
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    # Return the first standard path even if it doesn't exist yet
    return $candidates[0]
}

function Update-VSCodeSettings {
    param([string]$SettingsPath, [bool]$Remove)

    $proxyPath = $ProxyExe -replace "\\", "/"

    if (-not (Test-Path $SettingsPath)) {
        if ($Remove) { Write-Warn "VSCode settings not found – nothing to remove."; return }
        New-Item -ItemType File -Force -Path $SettingsPath | Out-Null
        Set-Content -Path $SettingsPath -Value "{}" -Encoding UTF8
    }

    $raw = Get-Content $SettingsPath -Raw -Encoding UTF8
    # Parse with ConvertFrom-Json (PowerShell 5 returns PSCustomObject)
    try {
        $settings = $raw | ConvertFrom-Json
    } catch {
        Write-Fail "Could not parse $SettingsPath – skipping VSCode update."
        return
    }

    if ($Remove) {
        $settings.PSObject.Properties.Remove("cmake.cmakePath")
        Write-OK "Removed cmake.cmakePath from $SettingsPath"
    } else {
        if ($settings.PSObject.Properties["cmake.cmakePath"]) {
            $settings."cmake.cmakePath" = $proxyPath
        } else {
            $settings | Add-Member -MemberType NoteProperty -Name "cmake.cmakePath" -Value $proxyPath
        }
        Write-OK "Set cmake.cmakePath = $proxyPath in $SettingsPath"
    }

    # ConvertTo-Json depth 10 to preserve nested objects
    $settings | ConvertTo-Json -Depth 10 | Set-Content -Path $SettingsPath -Encoding UTF8
}

# ── PATH helpers ──────────────────────────────────────────────────────────────
function Add-ToPath {
    $current = [Environment]::GetEnvironmentVariable("Path", $Scope)
    $entries = $current -split ";" | Where-Object { $_ -ne "" }
    if ($entries -contains $BinDir) {
        Write-Warn "$BinDir is already in $Scope PATH."
        return
    }
    $newPath = ($entries + $BinDir) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, $Scope)
    Write-OK "Added $BinDir to $Scope PATH."
    Write-Warn "Restart your terminal (or reload your shell) for the change to take effect."
}

function Remove-FromPath {
    $current = [Environment]::GetEnvironmentVariable("Path", $Scope)
    $entries = $current -split ";" | Where-Object { $_ -ne "" -and $_ -ne $BinDir }
    [Environment]::SetEnvironmentVariable("Path", ($entries -join ";"), $Scope)
    Write-OK "Removed $BinDir from $Scope PATH."
}

# ── main ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "cmake-ctl setup" -ForegroundColor Blue
Write-Host ("─" * 50) -ForegroundColor DarkGray
Write-Info "Bin directory : $BinDir"
Write-Info "Proxy exe     : $ProxyExe"
Write-Info "PATH scope    : $Scope"
Write-Host ""

if ($Uninstall) {
    Write-Info "Uninstalling cmake-ctl..."
    Remove-FromPath
    $vscPath = Get-VSCodeSettingsPath
    Update-VSCodeSettings -SettingsPath $vscPath -Remove $true
    Write-Host ""
    Write-OK "Uninstall complete."
    exit 0
}

# Validate proxy exists
if (-not (Test-Path $ProxyExe)) {
    Write-Fail "Proxy not found at $ProxyExe. Run build.bat first."
    exit 1
}

# Add to PATH
Add-ToPath

# Update VSCode settings
if ($VSCode) {
    $vscPath = Get-VSCodeSettingsPath
    Write-Info "VSCode settings: $vscPath"
    Update-VSCodeSettings -SettingsPath $vscPath -Remove $false
} else {
    Write-Warn "Skipping VSCode setup (pass -VSCode to enable)."
}

Write-Host ""
Write-OK "Setup complete. You can now use 'cmake' and 'cmake-ctl' from any terminal."
Write-Host ""
