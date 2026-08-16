@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-prod.ps1"
set EXITCODE=%ERRORLEVEL%

if /i "%~1"=="-nopause" exit /b %EXITCODE%
echo.
pause
exit /b %EXITCODE%
