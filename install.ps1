# ============================================================
#  2026 World Cup Predictor - Windows Dependency Installer
#  Run once after unzipping the production package, before start-prod.bat
#  Usage: powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
#         or double-click install.bat
# ============================================================

$ErrorActionPreference = "Stop"

try {
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [Console]::InputEncoding = $utf8
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
    chcp 65001 | Out-Null
} catch {}

$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Dir "backend"
$FrontendDir = Join-Path $Dir "frontend"
$VenvPython = Join-Path $BackendDir "venv\Scripts\python.exe"
$VenvPip = Join-Path $BackendDir "venv\Scripts\pip.exe"

function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

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
            $ver = & $c.Cmd @($c.Args) -c "import sys; print('%d.%d' % (sys.version_info[0], sys.version_info[1]))" 2>$null
            $major = ("$ver".Trim() -split '\.')[0]
            if ($major -eq "3") {
                return @{ Exe = $found.Source; Args = $c.Args; Version = "$ver".Trim() }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Merge-EnvFile([string]$Example, [string]$Target) {
    if (-not (Test-Path -LiteralPath $Example)) {
        Write-Host "[merge-env] Skip: no $Example"
        return
    }
    if (-not (Test-Path -LiteralPath $Target)) {
        New-Item -ItemType File -Path $Target -Force | Out-Null
    }
    $existing = @{}
    Get-Content -LiteralPath $Target -ErrorAction SilentlyContinue | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $existing[$line.Substring(0, $eq).Trim()] = $true
    }
    $added = 0
    $toAppend = New-Object System.Collections.Generic.List[string]
    Get-Content -LiteralPath $Example | ForEach-Object {
        $raw = $_
        $line = ($raw -replace '#.*$', '').Trim()
        if (-not $line) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $key = $line.Substring(0, $eq).Trim()
        if (-not $key -or $existing.ContainsKey($key)) { return }
        $toAppend.Add($line) | Out-Null
        $existing[$key] = $true
        $added++
    }
    if ($added -gt 0) {
        $enc = New-Object System.Text.UTF8Encoding $false
        $block = ($toAppend -join "`n") + "`n"
        [System.IO.File]::AppendAllText($Target, $block, $enc)
        Write-Host "[merge-env] Added $added key(s) to $(Split-Path -Leaf $Target) from $(Split-Path -Leaf $Example)"
    }
}

Write-Host "=============================================="
Write-Host " 2026 World Cup Predictor - Install Dependencies"
Write-Host "=============================================="
Write-Host "  Platform: Windows"
Write-Host ""

# -- 1. Prerequisites (cannot apt-install on Windows) ------

Write-Host "[1/5] Checking system prerequisites..."

$python = Find-Python
if (-not $python) {
    Write-Err "Python 3 not found."
    Write-Host "  Install from https://www.python.org/downloads/"
    Write-Host "  Tick 'Add python.exe to PATH', then re-run install.bat"
    exit 1
}
Write-Ok "Python $($python.Version)"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Err "Node.js not found."
    Write-Host "  Install LTS from https://nodejs.org/ then re-run install.bat"
    exit 1
}
$nodeVer = & node -v 2>$null
Write-Ok "Node.js $nodeVer"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Err "npm not found (comes with Node.js)."
    exit 1
}
Write-Ok "npm $(npm -v)"

# -- 2. Redis (optional) -----------------------------------

Write-Host "[2/5] Checking Redis..."
$redisOk = $false
if (Get-Command redis-cli -ErrorAction SilentlyContinue) {
    try {
        $pong = & redis-cli ping 2>$null
        if ("$pong".Trim() -eq "PONG") { $redisOk = $true }
    } catch {}
}
if ($redisOk) {
    Write-Ok "Redis is running"
} else {
    Write-Warn "Redis not detected - app can use in-memory cache"
    Write-Host "  Optional: install Memurai / Redis for Windows, or skip"
}

# -- 3. Python venv + dependencies -------------------------

Write-Host "[3/5] Installing Python dependencies..."

$reqFile = Join-Path $BackendDir "requirements.txt"
if (-not (Test-Path -LiteralPath $reqFile)) {
    Write-Err "Missing $reqFile"
    exit 1
}

$venvDir = Join-Path $BackendDir "venv"
if ((Test-Path -LiteralPath $venvDir) -and -not (Test-Path -LiteralPath $VenvPython)) {
    if (Test-Path -LiteralPath (Join-Path $venvDir "bin\activate")) {
        Write-Warn "Linux venv at $venvDir cannot run on Windows - recreating"
    } else {
        Write-Warn "Invalid venv at $venvDir - recreating"
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

& $VenvPython -m pip install --upgrade pip -q
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip upgrade failed"
    exit 1
}
Write-Ok "pip upgraded"

& $VenvPython -m pip install -r $reqFile
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip install failed"
    exit 1
}
Write-Ok "Python packages installed"

# -- 4. Playwright browser ---------------------------------

Write-Host "[4/5] Installing Playwright Chromium..."
$playwrightPy = Join-Path $BackendDir "venv\Scripts\playwright.exe"
if (Test-Path -LiteralPath $playwrightPy) {
    & $playwrightPy install chromium
} else {
    & $VenvPython -m playwright install chromium
}
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Playwright Chromium install failed - Sporttery browser fallback may not work"
} else {
    Write-Ok "Playwright Chromium installed"
}

# -- 5. Frontend dependencies ------------------------------

Write-Host "[5/5] Frontend dependencies..."
$distIndex = Join-Path $FrontendDir "dist\index.html"
$pkgJson = Join-Path $FrontendDir "package.json"
$serverJs = Join-Path $FrontendDir "server.js"

if ((Test-Path -LiteralPath $distIndex) -and (Test-Path -LiteralPath $serverJs)) {
    Write-Ok "Production frontend present (dist/ + server.js) - skip npm install"
} elseif (Test-Path -LiteralPath $pkgJson) {
    Push-Location $FrontendDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Err "npm install failed"
            exit 1
        }
        Write-Ok "Frontend packages installed"
    } finally {
        Pop-Location
    }
} else {
    Write-Warn "No frontend/package.json or dist/ - skip frontend step"
}

# -- Environment file --------------------------------------

$envExample = Join-Path $Dir ".env.example"
$envFile = Join-Path $Dir ".env"
if (-not (Test-Path -LiteralPath $envFile) -and (Test-Path -LiteralPath $envExample)) {
    Copy-Item -LiteralPath $envExample -Destination $envFile
    Write-Ok "Created .env from .env.example"
}
Merge-EnvFile $envExample $envFile

# -- Done --------------------------------------------------

Write-Host ""
Write-Host "=============================================="
Write-Host "  Installation complete!"
Write-Host ""
Write-Host "  Edit .env (set APP_ENV=production, ADMIN_PASSWORD, JWT_SECRET), then:"
Write-Host "    start-prod.bat   # Launch production services"
Write-Host "    stop-prod.bat    # Stop all services"
Write-Host ""
Write-Host "  Production URLs:"
Write-Host "    Frontend: http://localhost:4173  (login: server URL empty)"
Write-Host "    Backend:  http://localhost:8888/docs"
Write-Host ""
Write-Host "  Firewall: allow TCP 4173 and 8888 if accessed from LAN"
Write-Host "=============================================="
exit 0
