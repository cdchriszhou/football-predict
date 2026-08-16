@echo off
setlocal
cd /d "%~dp0"

REM Keep system code page. Scripts are ASCII-only.
REM Forcing UTF-8 code page often garbles Chinese pause text with raster fonts.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-prod.ps1"
set EXITCODE=%ERRORLEVEL%

if /i "%~1"=="-nopause" exit /b %EXITCODE%
echo.
echo Press any key to close...
pause >nul
exit /b %EXITCODE%
