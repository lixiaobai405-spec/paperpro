@echo off
setlocal
cd /d "%~dp0"
echo.
echo  PaperPro Resume Studio
echo  http://127.0.0.1:8766/
echo.
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/health' -TimeoutSec 2; if ($r.service -eq 'paperpro') { exit 0 } } catch {}; exit 1"
if not errorlevel 1 (
  echo [OK] PaperPro is already running. Opening browser...
  start "" "http://127.0.0.1:8766/"
  exit /b 0
)
where uv >nul 2>&1
if errorlevel 1 (
  echo [ERROR] uv not found. Install uv first.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo [ERROR] Frontend is not built. Run npm ci and npm run build in frontend folder.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8766/"
uv run --python 3.12 python -m uvicorn app.main:app --host 127.0.0.1 --port 8766
if errorlevel 1 pause
