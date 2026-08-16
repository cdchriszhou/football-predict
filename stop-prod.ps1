# ============================================================
#  2026 World Cup Predictor - Production Stopper (Windows)
#  Usage: powershell -NoProfile -ExecutionPolicy Bypass -File stop-prod.ps1
#         or double-click stop-prod.bat
# ============================================================

$ErrorActionPreference = "Continue"

# Keep host console code page. Messages below are ASCII-only.

$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendPort = 8888
$FrontendPort = 4173

function Get-ListeningPids([int]$Port) {
    $pids = @()
    $output = & netstat -ano -p tcp 2>$null
    foreach ($line in $output) {
        if ($line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            $procId = [int]$Matches[1]
            if ($procId -gt 4) { $pids += $procId }
        }
    }
    return @($pids | Select-Object -Unique)
}

function Stop-PidFile([string]$PidFile, [string]$Name) {
    if (-not (Test-Path -LiteralPath $PidFile)) { return }
    $raw = (Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue)
    if (-not $raw) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        return
    }
    $procId = $raw.Trim()
    if ($procId -match '^\d+$') {
        $running = Get-Process -Id ([int]$procId) -ErrorAction SilentlyContinue
        if ($running) {
            & taskkill /PID $procId /T /F 2>$null | Out-Null
            Write-Host "  $Name (PID $procId) stopped"
        }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Stop-ListenPort([int]$Port) {
    $pids = Get-ListeningPids $Port
    foreach ($procId in $pids) {
        & taskkill /PID $procId /T /F 2>$null | Out-Null
        Write-Host "  Released port $Port (PID $procId)"
    }
}

Write-Host "======================================"
Write-Host "  Stopping 2026 World Cup Predictor..."
Write-Host "======================================"

Stop-PidFile (Join-Path $Dir ".backend.pid")  "Backend API"
Stop-PidFile (Join-Path $Dir ".frontend.pid") "Frontend server"

Stop-ListenPort $BackendPort
Stop-ListenPort $FrontendPort

Write-Host "  Done."
exit 0
