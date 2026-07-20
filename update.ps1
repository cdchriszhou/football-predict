# ============================================================
#  Windows helper: build package for Linux server update
#  Usage: powershell -File update.ps1
#  (On server, use /mnt/update.sh with uploaded zip)
# ============================================================

$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=============================================="
Write-Host " Build production zip for server update"
Write-Host "=============================================="

& "$Dir\build.bat"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$zip = Get-ChildItem -Path $Dir -Filter "worldcup-predict-prod-*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) {
    Write-Host "[ERROR] No zip produced by build.bat" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[OK] Package ready: $($zip.Name)" -ForegroundColor Green
Write-Host "Upload to server /mnt/ and run: bash /mnt/update.sh"
Write-Host "After update, open http://<server>:4173 — login server URL leave empty"
