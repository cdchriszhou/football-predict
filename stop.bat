@echo off
echo ======================================
echo    WorldCup 2026 Predict - Stopping
echo ======================================

echo Stopping backend...
taskkill /f /im python.exe 2>nul

echo Stopping frontend...
taskkill /f /im node.exe 2>nul

echo All services stopped
pause
