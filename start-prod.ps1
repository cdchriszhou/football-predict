# ============================================================
#  2026 World Cup Predictor — Production Launcher (Windows)
#  Serves built frontend (dist/) + backend API
#  Usage: powershell -NoProfile -ExecutionPolicy Bypass -File start-prod.ps1
#         or double-click start-prod.bat
# ============================================================

$ErrorActionPreference = "Stop"

$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Dir "backend"
$FrontendDir = Join-Path $Dir "frontend"
$BackendPort = 8888
$FrontendPort = 4173
$VenvPython = Join-Path $BackendDir "venv\Scripts\python.exe"

function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

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

function Stop-ListenPort([int]$Port) {
    foreach ($procId in (Get-ListeningPids $Port)) {
        & taskkill /PID $procId /T /F 2>$null | Out-Null
    }
}

function Test-HttpOk([string]$Url) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Import-DotEnv([string]$Path) {
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        Set-Item -Path "Env:$key" -Value $val
    }
}

function Find-Python {
    $candidates = @(
        @{ Cmd = "py";     Args = @("-3") },
        @{ Cmd = "python"; Args = @() },
        @{ Cmd = "python3"; Args = @() }
    )
    foreach ($c in $candidates) {
        $found = Get-Command $c.Cmd -ErrorAction SilentlyContinue
        if (-not $found) { continue }
        try {
            $ver = & $c.Cmd @($c.Args) -c "import sys; print(sys.version_info[0])" 2>$null
            if ("$ver".Trim() -eq "3") {
                return @{ Exe = $found.Source; Args = $c.Args }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Start-HiddenProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$LogPath
    )
    if (Test-Path -LiteralPath $LogPath) {
        Remove-Item -LiteralPath $LogPath -Force -ErrorAction SilentlyContinue
    }
    # cmd /s /c "..." so paths with spaces work; stdout/stderr go to the log file
    # (not a pipe to this script, which would block after we exit).
    $inner = "`"$FileName`" $Arguments > `"$LogPath`" 2>&1"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $env:ComSpec
    $psi.Arguments = "/s /c `"$inner`""
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()
    return $proc
}

Write-Host "=============================================="
Write-Host " 2026 World Cup Predictor — Production Mode"
Write-Host "=============================================="

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Err "Node.js not found. Install Node.js LTS, then re-run."
    exit 1
}

$python = Find-Python
if (-not $python) {
    Write-Err "Python 3 not found. Install Python 3.x (and tick 'Add python.exe to PATH')."
    exit 1
}

$distIndex = Join-Path $FrontendDir "dist\index.html"
if (-not (Test-Path -LiteralPath $distIndex)) {
    Write-Err "frontend\dist\ not found. Run 'cd frontend && npm run build' first."
    exit 1
}

$serverJs = Join-Path $FrontendDir "server.js"
if (-not (Test-Path -LiteralPath $serverJs)) {
    Write-Err "frontend\server.js not found."
    exit 1
}

Write-Ok "Checks passed"

$envFile = Join-Path $Dir ".env"
if (Test-Path -LiteralPath $envFile) {
    Import-DotEnv $envFile
    Write-Ok "Loaded $envFile"
}

if (-not $env:APP_ENV) { $env:APP_ENV = "production" }
if ($env:APP_ENV -eq "production") {
    if (-not $env:ADMIN_PASSWORD -or $env:ADMIN_PASSWORD -eq "change-me-in-production") {
        Write-Err "APP_ENV=production but ADMIN_PASSWORD is unset or still placeholder — edit .env"
        exit 1
    }
    if (-not $env:JWT_SECRET -or $env:JWT_SECRET -eq "change-me-in-production") {
        Write-Err "APP_ENV=production but JWT_SECRET is unset or still placeholder — edit .env"
        exit 1
    }
    Write-Ok "APP_ENV=production"
}

$venvDir = Join-Path $BackendDir "venv"
if ((Test-Path -LiteralPath $venvDir) -and -not (Test-Path -LiteralPath $VenvPython)) {
    if (Test-Path -LiteralPath (Join-Path $venvDir "bin\activate")) {
        Write-Warn "Linux venv at $venvDir cannot run on Windows — recreating"
    } else {
        Write-Warn "Invalid venv at $venvDir — recreating"
    }
    Remove-Item -LiteralPath $venvDir -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "[..] Creating Python venv..."
    & $python.Exe @($python.Args) -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
        Write-Err "venv creation failed"
        exit 1
    }
}
Write-Ok "Python venv ready"

$reqFile = Join-Path $BackendDir "requirements.txt"
Write-Host "[..] Installing Python dependencies..."
& $VenvPython -m pip install -r $reqFile -q
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip install failed — see output above"
    exit 1
}
Write-Ok "Python dependencies up to date"

Write-Host ""
Write-Host "[1/2] Starting backend API (port $BackendPort)..."
Stop-ListenPort $BackendPort
Start-Sleep -Seconds 1

$backendLog = Join-Path $Dir "backend.log"
$backendProc = Start-HiddenProcess `
    -FileName $VenvPython `
    -Arguments "-m uvicorn main:app --host 0.0.0.0 --port $BackendPort" `
    -WorkingDirectory $BackendDir `
    -LogPath $backendLog
$backendProc.Id | Set-Content -LiteralPath (Join-Path $Dir ".backend.pid") -Encoding ASCII
Write-Ok "Backend started (PID $($backendProc.Id))"

$healthUrl = "http://127.0.0.1:$BackendPort/api/v1/system/health"
$healthy = $false
for ($i = 1; $i -le 45; $i++) {
    $backendProc.Refresh()
    if ($backendProc.HasExited) { break }
    if (Test-HttpOk $healthUrl) { $healthy = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    Write-Err "Backend failed health check after ~90s — last 30 lines of backend.log:"
    if (Test-Path -LiteralPath $backendLog) {
        Get-Content -LiteralPath $backendLog -Tail 30
    }
    Write-Err "Check .env (ADMIN_PASSWORD, JWT_SECRET) or see backend.log"
    exit 1
}
Write-Ok "Backend health OK"

Write-Host "[2/2] Starting frontend server (port $FrontendPort)..."
Stop-ListenPort $FrontendPort
Start-Sleep -Seconds 1

$frontendLog = Join-Path $Dir "frontend.log"
$nodeExe = (Get-Command node).Source
$frontendProc = Start-HiddenProcess `
    -FileName $nodeExe `
    -Arguments "server.js" `
    -WorkingDirectory $FrontendDir `
    -LogPath $frontendLog
$frontendProc.Id | Set-Content -LiteralPath (Join-Path $Dir ".frontend.pid") -Encoding ASCII
Write-Ok "Frontend started (PID $($frontendProc.Id))"

Start-Sleep -Seconds 2
if (Test-HttpOk "http://127.0.0.1:$FrontendPort/health") {
    Write-Ok "Frontend health OK"
} else {
    Write-Warn "Frontend health check failed — see frontend.log"
}

Write-Host ""
Write-Host "=============================================="
Write-Host "  Production server started!"
Write-Host ""
Write-Host "  Open in browser: http://localhost:$FrontendPort"
Write-Host "  Login -> server URL: leave EMPTY (uses /api proxy)"
Write-Host ""
Write-Host "  Frontend: http://localhost:$FrontendPort"
Write-Host "  Backend:  http://localhost:$BackendPort"
Write-Host "  API docs: http://localhost:$BackendPort/docs"
Write-Host ""
Write-Host "  Run stop-prod.bat to stop all services"
Write-Host "=============================================="
exit 0
