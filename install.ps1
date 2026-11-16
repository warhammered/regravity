# Regravity Universal PowerShell Installer
# Local execution:  powershell -ExecutionPolicy Bypass -File .\install.ps1
# Remote execution: irm https://raw.githubusercontent.com/warhammered/regravity/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

function Find-Python {
    $candidates = @("python", "py", "python3")
    foreach ($cmd in $candidates) {
        try {
            $ver = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $ver -match "Python 3") {
                return $cmd
            }
        } catch {}
    }
    return $null
}

$pythonExe = Find-Python
if (-not $pythonExe) {
    Write-Host "[!] Python 3 is required to install Regravity." -ForegroundColor Red
    Write-Host "    Install via winget:  winget install Python.Python.3.12" -ForegroundColor Yellow
    Write-Host "    Or download from:    https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

$isRemote = $false
$scriptDir = $PSScriptRoot
if (-not $scriptDir -or -not (Test-Path (Join-Path $scriptDir "install.py"))) {
    $isRemote = $true
}

if (-not $isRemote) {
    & $pythonExe (Join-Path $scriptDir "install.py") @args
    exit $LASTEXITCODE
}

# --- Remote 1-Liner Installation Flow ---
Write-Host ""
Write-Host "  ===============================================================" -ForegroundColor Cyan
Write-Host "    Regravity - Native Multi-Account Manager for Antigravity     " -ForegroundColor Cyan
Write-Host "    Remote 1-Liner Installer                                      " -ForegroundColor Cyan
Write-Host "  ===============================================================" -ForegroundColor Cyan
Write-Host ""

$tempId = [System.Guid]::NewGuid().ToString().Substring(0, 8)
$tempDir = Join-Path $env:TEMP "regravity-install-$tempId"
$zipPath = Join-Path $tempDir "regravity.zip"

try {
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    Write-Host "[i] Fetching latest Regravity release from GitHub..." -ForegroundColor Cyan
    $repoZipUrl = "https://github.com/warhammered/regravity/archive/refs/heads/main.zip"
    Invoke-WebRequest -Uri $repoZipUrl -OutFile $zipPath -UseBasicParsing

    Write-Host "[i] Extracting package..." -ForegroundColor Cyan
    Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

    $extractedDir = Join-Path $tempDir "regravity-main"
    if (-not (Test-Path (Join-Path $extractedDir "install.py"))) {
        $found = Get-ChildItem -Path $tempDir -Recurse -Filter "install.py" | Select-Object -First 1
        if ($found) {
            $extractedDir = $found.DirectoryName
        } else {
            throw "Failed to locate install.py in downloaded package."
        }
    }

    Write-Host "[i] Launching installer..." -ForegroundColor Cyan
    & $pythonExe (Join-Path $extractedDir "install.py") @args
    $exitCode = $LASTEXITCODE
} catch {
    Write-Host "[!] Remote installation failed: $_" -ForegroundColor Red
    $exitCode = 1
} finally {
    if (Test-Path $tempDir) {
        Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

exit $exitCode
