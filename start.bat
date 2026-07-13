@echo off
chcp 65001 >nul
cd /d %~dp0

echo ============================================
echo   JavaDoctor - One-click Start
echo ============================================

echo [1/4] Starting Ollama service...
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    start "" ollama serve
    timeout /t 2 >nul
) else (
    echo     Ollama already running, skip
)

echo [2/4] Starting backend FastAPI on port 8000...
if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul
start "JavaDoctor-Backend" cmd /k "cd backend && python -m uvicorn app.main:app --reload --port 8000"

echo [3/4] Starting frontend Vite on port 5173...
start "JavaDoctor-Frontend" cmd /k "cd frontend && npm run dev"

echo [4/4] Opening browser...
timeout /t 6 >nul
start http://localhost:5173

echo.
echo Started!
echo   Frontend: http://localhost:5173
echo   Backend : http://localhost:8000/docs
echo   Admin   : admin / 123456
echo.
echo Closing this window does not stop services. Run stop.bat to stop.
pause
