@echo off
setlocal EnableDelayedExpansion

set "APP_NAME=cleverswitch"
set "EXE_NAME=cleverswitch.exe"
set "VBS_NAME=run_cleverswitch.vbs"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\CleverSwitch"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_PATH=%STARTUP_FOLDER%\%VBS_NAME%"

:: ── Step 1: Remove startup entry ─────────────────────────────────────

if exist "%VBS_PATH%" (
    echo [INFO] Removing startup entry...
    taskkill /f /im "%EXE_NAME%" >nul 2>&1
    del /f "%VBS_PATH%"
    echo [OK] Startup entry removed.
) else (
    echo [INFO] No startup entry found - skipping.
)

:: ── Step 2: Remove from user PATH ────────────────────────────────────

for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "USER_PATH=%%B"

echo !USER_PATH! | findstr /i /c:"%INSTALL_DIR%" >nul
if %errorlevel% == 0 (
    echo [INFO] Removing %INSTALL_DIR% from user PATH...
    set "NEW_PATH=!USER_PATH:%INSTALL_DIR%;=!"
    set "NEW_PATH=!NEW_PATH:;%INSTALL_DIR%=!"
    set "NEW_PATH=!NEW_PATH:%INSTALL_DIR%=!"
    setx PATH "!NEW_PATH!" >nul
    echo [OK] PATH updated.
) else (
    echo [INFO] %INSTALL_DIR% was not on your PATH - skipping.
)

:: ── Step 3: Remove install directory ─────────────────────────────────

if exist "%INSTALL_DIR%" (
    echo [INFO] Removing %INSTALL_DIR%...
    rmdir /s /q "%INSTALL_DIR%"
    echo [OK] %APP_NAME% removed.
) else (
    echo [INFO] No installation found at %INSTALL_DIR% - skipping.
)

:: ── Done ─────────────────────────────────────────────────────────────

echo.
echo [OK] Uninstall complete!
pause
