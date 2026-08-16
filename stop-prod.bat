@echo off
setlocal
cd /d "%~dp0"

REM UTF-8 console so Chinese Windows does not mojibake script output
chcp 65001 >nul

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-prod.ps1"
set EXITCODE=%ERRORLEVEL%

if /i "%~1"=="-nopause" exit /b %EXITCODE%
echo.
pause
exit /b %EXITCODE%
