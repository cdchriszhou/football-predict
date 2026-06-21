@echo off
echo ======================================
echo    WorldCup 2026 Predict - Starting
echo ======================================

echo [1/3] Starting backend...
cd /d "%~dp0backend"
start "WorldCup-Backend" cmd /k "venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8888"

echo [2/3] Starting frontend...
cd /d "%~dp0frontend"
start "WorldCup-Frontend" cmd /k "npm run dev"

echo ======================================
echo   Started successfully!
echo   Frontend:  http://localhost:5173
echo   Backend:   http://localhost:8888
echo   API Docs:  http://localhost:8888/docs
echo ======================================
pause
