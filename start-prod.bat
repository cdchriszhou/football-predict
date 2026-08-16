@echo off
setlocal
cd /d "%~dp0"

REM UTF-8 console so Chinese Windows does not mojibake script output
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-prod.ps1"
set EXITCODE=%ERRORLEVEL%

if /i "%~1"=="-nopause" exit /b %EXITCODE%
echo.
pause
exit /b %EXITCODE%
