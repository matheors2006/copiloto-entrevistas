$RootDir = $PSScriptRoot
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "desktop-ui"

$BackendCommand = "`$Host.UI.RawUI.WindowTitle = 'BACKEND - FastAPI'; Set-Location '$BackendDir'; .\venv\Scripts\Activate.ps1; uvicorn main:app --port 8000"
Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $BackendCommand)

$FrontendCommand = "`$Host.UI.RawUI.WindowTitle = 'FRONTEND - Tauri'; Set-Location '$FrontendDir'; npm run tauri dev"
Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $FrontendCommand)

Write-Host "Backend y frontend lanzados en ventanas independientes."