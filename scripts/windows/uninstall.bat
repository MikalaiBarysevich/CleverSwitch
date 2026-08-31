@echo off
setlocal EnableDelayedExpansion

set "APP_NAME=cleverswitch"
set "EXE_NAME=cleverswitch.exe"
set "VBS_NAME=run_cleverswitch.vbs"
set "SCRIPT_DIR=%~dp0"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\CleverSwitch"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS_PATH=%STARTUP_FOLDER%\%VBS_NAME%"

:: Paths are expanded as !VAR! inside ( ) blocks — see the note in install.bat.

:: ── Step 1: Remove startup entry ─────────────────────────────────────

if exist "!VBS_PATH!" (
    echo [INFO] Removing startup entry...
    taskkill /f /im "%EXE_NAME%" >nul 2>&1
    del /f "!VBS_PATH!"
    echo [OK] Startup entry removed.
) else (
    echo [INFO] No startup entry found - skipping.
)

:: ── Step 2: Remove from user PATH ────────────────────────────────────

for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "USER_PATH=%%B"

set "NEW_PATH=!USER_PATH:%INSTALL_DIR%;=!"
set "NEW_PATH=!NEW_PATH:;%INSTALL_DIR%=!"
set "NEW_PATH=!NEW_PATH:%INSTALL_DIR%=!"

if "!NEW_PATH!"=="!USER_PATH!" (
    echo [INFO] "!INSTALL_DIR!" was not on your PATH - skipping.
) else (
    echo [INFO] Removing "!INSTALL_DIR!" from user PATH...
    REM See the note in install.bat: setx.exe silently truncates values over
    REM 1024 characters, so it isn't safe for writing PATH back either.
    REM If the install dir was the only PATH entry, NEW_PATH ends up
    REM undefined here (batch has no defined-but-empty variable state), so
    REM it isn't part of the environment set_user_path.ps1 inherits and
    REM $env:NEW_PATH reads as $null there - the script explicitly treats
    REM that as an empty string rather than skipping the write, so PATH
    REM ends up present-but-empty instead of being deleted outright.
    if not exist "!SCRIPT_DIR!set_user_path.ps1" (
        echo [WARN] set_user_path.ps1 not found alongside uninstall.bat - skipping PATH update.
    ) else (
        set "CS_PATH_WRITE=1"
        powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "!SCRIPT_DIR!set_user_path.ps1"
        if errorlevel 1 (
            echo [ERROR] Failed to update PATH - it was not changed.
        ) else (
            echo [OK] PATH updated.
        )
    )
)

:: ── Step 3: Remove install directory ─────────────────────────────────

if exist "!INSTALL_DIR!" (
    echo [INFO] Removing "!INSTALL_DIR!"...
    rmdir /s /q "!INSTALL_DIR!"
    echo [OK] %APP_NAME% removed.
) else (
    echo [INFO] No installation found at "!INSTALL_DIR!" - skipping.
)

:: ── Done ─────────────────────────────────────────────────────────────

echo.
echo [OK] Uninstall complete!
pause
