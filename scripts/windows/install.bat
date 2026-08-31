@echo off
setlocal EnableDelayedExpansion

set "APP_NAME=cleverswitch"
set "EXE_NAME=cleverswitch.exe"
set "SCRIPT_DIR=%~dp0"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\CleverSwitch"
set "INSTALL_PATH=%INSTALL_DIR%\%EXE_NAME%"
set "SRC_BINARY=%SCRIPT_DIR%%EXE_NAME%"

:: Paths are expanded as !VAR! inside ( ) blocks. %VAR% expands when the block
:: is parsed, so an extraction folder such as "cleverswitch_windows_x64 (1)"
:: injects its parentheses into the block and cmd aborts the whole script with
:: "\cleverswitch.exe was unexpected at this time".

:: ── Preflight ─────────────────────────────────────────────────────────

if not exist "!SRC_BINARY!" (
    echo [ERROR] %EXE_NAME% not found at "!SRC_BINARY!".
    echo Run this script from the extracted archive folder.
    pause
    exit /b 1
)

:: ── Step 1: Install binary ────────────────────────────────────────────

echo [INFO] Installing %APP_NAME% to "!INSTALL_DIR!"...
if not exist "!INSTALL_DIR!" mkdir "!INSTALL_DIR!"
copy /y "!SRC_BINARY!" "!INSTALL_PATH!" >nul
powershell -Command "Unblock-File -LiteralPath '!INSTALL_PATH!'" 2>nul
echo [OK] %APP_NAME% installed at "!INSTALL_PATH!"

:: ── Step 2: Add to user PATH ──────────────────────────────────────────

for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "USER_PATH=%%B"

set "PATH_PROBE=!USER_PATH:%INSTALL_DIR%=!"
if "!PATH_PROBE!"=="!USER_PATH!" (
    echo [INFO] Adding "!INSTALL_DIR!" to your user PATH...
    if defined USER_PATH (
        set "NEW_PATH=!USER_PATH!;!INSTALL_DIR!"
    ) else (
        set "NEW_PATH=!INSTALL_DIR!"
    )
    REM setx.exe silently truncates values over 1024 characters instead of
    REM erroring - easy to hit once Python/Git/VS Code/WinGet/npm etc. have
    REM all added their own PATH entries, and it would drop the very entry
    REM this step is trying to add without any warning. set_user_path.ps1
    REM writes straight to the registry and isn't subject to that limit.
    REM NEW_PATH is read from this process's environment, not passed as a
    REM command-line argument - see the note at the top of that script.
    if not exist "!SCRIPT_DIR!set_user_path.ps1" (
        echo [WARN] set_user_path.ps1 not found alongside install.bat - skipping PATH update.
        echo [WARN] Add "!INSTALL_DIR!" to your PATH manually if needed.
    ) else (
        set "CS_PATH_WRITE=1"
        powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "!SCRIPT_DIR!set_user_path.ps1"
        if errorlevel 1 (
            echo [ERROR] Failed to update PATH - it was not changed.
            echo [ERROR] Add "!INSTALL_DIR!" to your PATH manually if needed.
        ) else (
            echo [OK] PATH updated.
            echo [WARN] Restart your terminal for the PATH change to take effect.
        )
    )
) else (
    echo [OK] "!INSTALL_DIR!" is already on your PATH.
)

:: ── Step 3: Startup (optional) ────────────────────────────────────────

set /p "STARTUP_CHOICE=Start CleverSwitch automatically on login? [y/n]: "
if /i "!STARTUP_CHOICE!"=="y" (
    set "STARTUP_SCRIPT=!SCRIPT_DIR!setup_startup_windows.bat"
    if not exist "!STARTUP_SCRIPT!" (
        echo [WARN] setup_startup_windows.bat not found alongside install.bat - skipping startup setup.
    ) else (
        call "!STARTUP_SCRIPT!"
    )
) else (
    echo [INFO] Skipped. You can run CleverSwitch manually with: %APP_NAME%
)

:: ── Done ─────────────────────────────────────────────────────────────

echo.
echo [OK] Installation complete!
pause
