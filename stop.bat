@echo off
chcp 65001 >nul

echo Stopping JavaDoctor services...

echo   Stopping backend window...
taskkill /FI "WINDOWTITLE eq JavaDoctor-Backend*" /T /F >nul 2>&1

echo   Stopping frontend window...
taskkill /FI "WINDOWTITLE eq JavaDoctor-Frontend*" /T /F >nul 2>&1

echo   Releasing ports 8000 / 5173...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1

echo.
echo Stopped. Ollama is left running for reuse; end ollama.exe manually if needed.
pause
