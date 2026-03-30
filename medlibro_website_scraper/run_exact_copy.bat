@echo off
REM ============================================================================
REM MEDLIBRO MIRROR - MAIN LAUNCHER
REM ============================================================================
REM This script does everything:
REM   1. Scrapes the real MedLibro website (opens Chrome, logs in, saves HTML)
REM   2. Builds the local mirror (downloads assets, patches JS for local API)
REM   3. Starts both servers (API proxy + Mirror server)
REM
REM Usage:
REM   run_exact_copy.bat          - Full scrape + build + start server (all-in-one)
REM   run_exact_copy.bat quick    - Skip scrape, use existing real_pages (faster)
REM
REM After running, open: http://localhost:8080
REM You will be redirected to /login automatically if not logged in.
REM Login: Use any email/password (e.g. test@test.com / password) - all local API.
REM ============================================================================

if "%~1" neq "run" goto LAUNCH

cd /d "%~dp0"
echo [DEBUG] Changed to folder: %CD%

if not exist "save_real_pages.py" goto NO_SCRIPT
echo [DEBUG] Found save_real_pages.py

chcp 65001 >nul 2>&1
title MedLibro Exact Copy

echo ============================================================================
echo MEDLIBRO EXACT COPY
echo ============================================================================
echo Folder: %CD%
echo.

echo [DEBUG] Checking for Python...
where py >nul 2>&1
if %errorlevel% equ 0 goto USE_PY
set PY=python
goto CHECK_PYTHON
:USE_PY
set PY=py

:CHECK_PYTHON
echo [DEBUG] Using Python command: %PY%
%PY% --version 2>nul
if errorlevel 1 goto NO_PYTHON
echo [OK] Python found: %PY%
echo.

if "%~2" equ "quick" goto SKIP_SAVE
echo [STEP 1] Saving real MedLibro HTML (full page load, fonts, design) - Chrome will open...
call %PY% save_real_pages.py
if errorlevel 1 goto SAVE_FAILED
echo.
goto BUILD_MIRROR
:SKIP_SAVE
echo [STEP 1] Quick mode - using existing real_pages (skip re-scrape)
goto BUILD_MIRROR

:BUILD_MIRROR
echo [STEP 2] Building mirror...
call %PY% build_mirror.py
if errorlevel 1 goto BUILD_FAILED
echo.

echo [STEP 3] Starting local mirror server on port 8080...
echo   (Serves HTML/JS + local API.)
echo.
echo   Open in browser: http://localhost:8080
echo   Login: any email / any password (e.g. test@test.com / password)
echo   Press Ctrl+C here to stop the server.
echo ============================================================================
echo.
call %PY% serve_mirror.py
if errorlevel 1 goto SERVER_ERROR
goto END

:LAUNCH
start "MedLibro Exact Copy" /D "%~dp0" cmd /k "%~nx0" run %1
exit /b 0

:NO_SCRIPT
echo [ERROR] Cannot find save_real_pages.py
echo Run this from the medlibro_website_scraper folder.
echo Current folder: %CD%
goto END

:NO_PYTHON
echo [ERROR] Python not found. Install Python and add it to PATH.
goto END

:SAVE_FAILED
echo [ERROR] save_real_pages.py failed
goto END

:BUILD_FAILED
echo [ERROR] build_mirror.py failed
goto END

:SERVER_ERROR
echo [ERROR] Server exited with an error.
goto END

:END
echo.
echo Press any key to close this window...
pause >nul
