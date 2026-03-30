@echo off
REM ============================================================================
REM INSTALL DEPENDENCIES
REM ============================================================================
REM Installs required Python packages for the MedLibro mirror.
REM Run this once before using run_exact_copy.bat
REM ============================================================================
chcp 65001 >nul
title Install Dependencies
echo ============================================================
echo Installing Dependencies for MedLibro Mirror
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

echo [INFO] Installing packages...
echo.

REM Try user installation first (avoids permission issues)
echo Attempting user installation (recommended)...
pip install --user beautifulsoup4 tqdm
if errorlevel 1 (
    echo.
    echo User installation failed. Trying system installation...
    pip install beautifulsoup4 tqdm
    if errorlevel 1 (
        echo.
        echo [ERROR] Installation failed.
        echo.
        echo Possible solutions:
        echo 1. Close all Python processes and try again
        echo 2. Run as Administrator
        echo 3. Install manually: pip install beautifulsoup4 tqdm
        echo.
        pause
        exit /b 1
    )
)

echo.
echo [OK] Dependencies installed successfully!
echo.
echo Checking installation...
python -c "import bs4, tqdm; print('[OK] All packages imported successfully!')"
if errorlevel 1 (
    echo [WARNING] Packages installed but import test failed.
    echo You may need to restart your terminal or IDE.
)

echo.
pause
