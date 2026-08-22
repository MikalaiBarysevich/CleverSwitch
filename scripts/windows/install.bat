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
        setx PATH "!USER_PATH!;!INSTALL_DIR!" >nul
    ) else (
        setx PATH "!INSTALL_DIR!" >nul
    )
    echo [OK] PATH updated.
    echo [WARN] Restart your terminal for the PATH change to take effect.
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
