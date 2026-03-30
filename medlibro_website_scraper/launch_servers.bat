@echo off
REM ============================================================================
REM QUICK SERVER LAUNCHER (LOCAL MODE)
REM ============================================================================
REM Use this ONLY if you've already built the mirror (run run_exact_copy.bat first).
REM This just starts the server - it does NOT scrape or build.
REM
REM To scrape + build + start: use run_exact_copy.bat instead.
REM
REM Starts ONE server on port 8080:
REM   - Serves the mirror (static files)
REM   - Handles ALL API calls locally (no external calls)
REM   - Login/auth handled locally
REM
REM Open: http://localhost:8080
REM You will be redirected to /login automatically if not logged in.
REM Login: Use any email/password (e.g. test@test.com / password)
REM ============================================================================
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel% equ 0 (set PY=py) else (set PY=python)

%PY% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python and add it to PATH.
    pause
    exit /b 1
)

if not exist "mirror\index.html" (
    echo [WARN] Mirror not built. Run build_mirror.py first, or run run_exact_copy.bat
    echo.
)

echo Starting MedLibro Local Mirror server (port 8080)...
echo   All API calls handled locally.
echo.
echo   Open in browser: http://localhost:8080
echo   Login: any email / any password (e.g. test@test.com / password)
echo   Press Ctrl+C to stop.
echo ============================================================================
echo.
call %PY% serve_mirror.py
