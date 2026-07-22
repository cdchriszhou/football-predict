@echo off
setlocal enabledelayedexpansion

set DIR=%~dp0
set DIR=%DIR:~0,-1%

:: Timestamp via PowerShell
for /f "delims=" %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set TS=%%I
set ZIP_NAME=worldcup-predict-prod-%TS%.zip
set BUILD_DIR=%DIR%\.build-tmp
set STAGE=%BUILD_DIR%\worldcup-predict

echo ==============================================
echo  2026 World Cup Predictor - Build ^& Package
echo ==============================================

:: ---- 1. Build frontend ---------------------------------

echo [1/4] Building frontend...

cd /d "%DIR%\frontend"

if not exist "node_modules" (
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed
        exit /b 1
    )
)

call npm run build
if %errorlevel% neq 0 (
    echo [ERROR] Frontend build failed
    exit /b 1
)
echo [OK] Frontend built

:: ---- 2. Prepare staging --------------------------------

echo [2/4] Preparing staging directory...

if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
mkdir "%STAGE%"
mkdir "%STAGE%\backend"
mkdir "%STAGE%\frontend"
mkdir "%STAGE%\lib"

:: ---- 3. Copy backend (exclude venv/caches/db) -----------
:: xcopy of a tree that still contains Windows venv often aborts mid-copy
:: (path length / volume of files) and silently leaves api/db/service missing.
:: robocopy with /XD avoids that.

echo [3/4] Copying backend...

robocopy "%DIR%\backend" "%STAGE%\backend" /E ^
  /XD venv .venv __pycache__ .pytest_cache tests .mypy_cache .ruff_cache ^
  /XF *.pyc *.db *.db-shm *.db-wal .DS_Store ^
  /NFL /NDL /NJH /NJS /nc /ns /np
set RC=%ERRORLEVEL%
if %RC% GEQ 8 (
    echo [ERROR] robocopy backend failed with code %RC%
    exit /b 1
)

:: Extra sweep for nested caches that may still appear under packages
powershell -NoProfile -Command ^
  "$r='%STAGE%\backend'; @('venv','.venv','__pycache__','.pytest_cache') | ForEach-Object { $n=$_; Get-ChildItem -LiteralPath $r -Recurse -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq $n } | Sort-Object { $_.FullName.Length } -Descending | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }; Get-ChildItem -LiteralPath $r -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.pyc','.db' -or $_.Name -match '\.db-(shm|wal)$' -or $_.Name -eq '.DS_Store' } | Remove-Item -Force -ErrorAction SilentlyContinue"

:: Hard-fail if critical backend packages are missing (root cause of ModuleNotFoundError: db)
for %%D in (db api service alembic data utils crawler llm middleware scheduler) do (
    if not exist "%STAGE%\backend\%%D" (
        echo [ERROR] Staged backend missing required directory: %%D
        exit /b 1
    )
)
if not exist "%STAGE%\backend\main.py" (
    echo [ERROR] Staged backend missing main.py
    exit /b 1
)
if not exist "%STAGE%\backend\db\__init__.py" (
    echo [ERROR] Staged backend missing db\__init__.py
    exit /b 1
)
if not exist "%STAGE%\backend\alembic\env.py" (
    echo [ERROR] Staged backend missing alembic\env.py
    exit /b 1
)

echo [OK] Backend staged

:: ---- 4. Copy frontend dist + server.js ----------------

xcopy /e /i /q "%DIR%\frontend\dist"     "%STAGE%\frontend\dist" >nul
copy /y  "%DIR%\frontend\server.js"      "%STAGE%\frontend\server.js"      >nul
copy /y  "%DIR%\frontend\package.json"   "%STAGE%\frontend\package.json"   >nul

if not exist "%STAGE%\frontend\dist\index.html" (
    echo [ERROR] frontend\dist\index.html missing after copy
    exit /b 1
)

echo [OK] Frontend staged

:: ---- 5. Copy scripts ----------------------------------

copy /y "%DIR%\install.sh"       "%STAGE%\install.sh"       >nul
copy /y "%DIR%\start-prod.sh"    "%STAGE%\start-prod.sh"    >nul
copy /y "%DIR%\stop-prod.sh"     "%STAGE%\stop-prod.sh"     >nul
copy /y "%DIR%\update.sh"        "%STAGE%\update.sh"        >nul
copy /y "%DIR%\lib\ensure-venv.sh"  "%STAGE%\lib\ensure-venv.sh"  >nul
copy /y "%DIR%\lib\merge-env.sh"    "%STAGE%\lib\merge-env.sh"    >nul
copy /y "%DIR%\lib\health-check.sh" "%STAGE%\lib\health-check.sh" >nul
copy /y "%DIR%\lib\fix-crlf.sh"       "%STAGE%\lib\fix-crlf.sh"       >nul
copy /y "%DIR%\lib\reset-admin.sh"    "%STAGE%\lib\reset-admin.sh"    >nul
powershell -NoProfile -Command "Get-ChildItem -Path '%STAGE%' -Recurse -Filter '*.sh' | ForEach-Object { $c = [IO.File]::ReadAllText($_.FullName) -replace \"`r`n\", \"`n\" -replace \"`r\", \"\"; [IO.File]::WriteAllText($_.FullName, $c) }"

if exist "%DIR%\.env.example" (
    copy /y "%DIR%\.env.example" "%STAGE%\.env.example" >nul
)

echo [OK] Scripts staged

:: ---- 5b. Verify no venv in package --------------------

if exist "%STAGE%\backend\venv" (
    echo [ERROR] Package still contains backend\venv — build aborted
    exit /b 1
)
if exist "%STAGE%\backend\.venv" (
    echo [ERROR] Package still contains backend\.venv — build aborted
    exit /b 1
)
echo [OK] Verified: backend venv not in package

:: ---- 6. Create ZIP (forward-slash entries for Linux unzip) ---

echo [..] Creating %ZIP_NAME%...

powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Add-Type -AssemblyName System.IO.Compression; Add-Type -AssemblyName System.IO.Compression.FileSystem;" ^
  "$src = '%STAGE%'; $zipPath = '%DIR%\%ZIP_NAME%';" ^
  "if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force };" ^
  "$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create);" ^
  "try {" ^
  "  $rootLen = $src.TrimEnd('\').Length + 1;" ^
  "  Get-ChildItem -LiteralPath $src -Recurse -File | ForEach-Object {" ^
  "    $rel = $_.FullName.Substring($rootLen) -replace '\\','/';" ^
  "    [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, ('worldcup-predict/' + $rel), [System.IO.Compression.CompressionLevel]::Optimal)" ^
  "  }" ^
  "} finally { $zip.Dispose() }"
if %errorlevel% neq 0 (
    echo [ERROR] ZIP creation failed
    exit /b 1
)

:: Verify zip contains critical backend modules
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Add-Type -AssemblyName System.IO.Compression.FileSystem;" ^
  "$z=[IO.Compression.ZipFile]::OpenRead('%DIR%\%ZIP_NAME%');" ^
  "try {" ^
  "  $names=@($z.Entries | ForEach-Object { $_.FullName -replace '\\','/' });" ^
  "  $need=@('worldcup-predict/backend/db/__init__.py','worldcup-predict/backend/api/','worldcup-predict/backend/service/','worldcup-predict/backend/alembic/env.py','worldcup-predict/backend/main.py');" ^
  "  foreach($n in $need){" ^
  "    if (-not ($names | Where-Object { $_ -like ($n.TrimEnd('/') + '*') })) { throw \"ZIP missing required entry: $n\" }" ^
  "  };" ^
  "  $backendCount = @($names | Where-Object { $_ -like 'worldcup-predict/backend/*' }).Count;" ^
  "  if ($backendCount -lt 50) { throw \"ZIP backend entry count too low: $backendCount (expected >= 50)\" };" ^
  "  Write-Host \"[OK] ZIP verified: $backendCount backend entries\"" ^
  "} finally { $z.Dispose() }"
if %errorlevel% neq 0 (
    echo [ERROR] ZIP integrity check failed — package not safe to deploy
    del /f /q "%DIR%\%ZIP_NAME%" 2>nul
    exit /b 1
)

:: Cleanup
cd /d "%DIR%"
rmdir /s /q "%BUILD_DIR%"

:: ---- Done ---------------------------------------------

for %%F in ("%DIR%\%ZIP_NAME%") do set SIZE=%%~zF
set /a SIZE_MB=%SIZE% / 1048576

echo.
echo ==============================================
echo   Build complete!
echo   Package: %ZIP_NAME% (!SIZE_MB! MB)
echo.
echo   Deploy to server:
echo     1. Upload %ZIP_NAME% to server /mnt/
echo     2. cd /mnt ^&^& ./update.sh
echo.
echo   Services (use :4173 in browser, leave login server URL empty):
echo     Frontend: http://^<ip^>:4173
echo     Backend:  http://^<ip^>:8888
echo ==============================================
