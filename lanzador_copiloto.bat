@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0

echo Buscando procesos que ocupen el puerto 8000...
for /f "tokens=*" %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).OwningProcess"') do (
    echo Matando proceso PID %%P...
    taskkill /PID %%P /F >nul 2>&1
)

echo Iniciando backend...
start "BACKEND - FastAPI" cmd /k "cd /d "%ROOT%backend" && call venv\Scripts\activate.bat && uvicorn main:app --port 8000"

echo Iniciando frontend...
start "FRONTEND - Tauri" cmd /k "cd /d "%ROOT%desktop-ui" && npm run tauri dev"

echo Sistema iniciado.