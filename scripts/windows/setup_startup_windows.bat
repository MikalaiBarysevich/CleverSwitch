@echo off
setlocal EnableDelayedExpansion

:: 1. Define Names
set "APP_NAME=cleverswitch"
set "EXE_NAME=cleverswitch.exe"
set "VBS_NAME=run_cleverswitch.vbs"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\CleverSwitch"
set "INSTALL_PATH=%INSTALL_DIR%\%EXE_NAME%"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

:: 2. Resolve the executable path for the VBS shim.
:: Prefer the canonical install location so the VBS survives deletion of the
:: source archive folder. Fall back to PATH for manual installs.
set "VBS_EXE_PATH="
if exist "%INSTALL_PATH%" (
    REM Use a literal env var in the VBS so it stays user-portable.
    REM WScript.Shell.Run expands environment variables in the command string.
    set "VBS_EXE_PATH=%%localappdata%%\Programs\CleverSwitch\%EXE_NAME%"
    set "FOUND_AT=%INSTALL_PATH%"
) else (
    for %%i in (%EXE_NAME%) do set "PATH_EXE=%%~$PATH:i"
    if defined PATH_EXE (
        set "VBS_EXE_PATH=!PATH_EXE!"
        set "FOUND_AT=!PATH_EXE!"
    )
)

if "!VBS_EXE_PATH!"=="" (
    echo Error: %EXE_NAME% not found at %INSTALL_PATH% or on your PATH.
    echo Please run install.bat first.
    pause
    exit /b
)

echo Found %APP_NAME% at: !FOUND_AT!

:: 3. Create the VBScript wrapper (to run hidden)
:: We use '0' to hide the console window
echo Set WinScriptHost = CreateObject^("WScript.Shell"^) > "%TEMP%\%VBS_NAME%"
echo WinScriptHost.CurrentDirectory = WinScriptHost.ExpandEnvironmentStrings^("%%USERPROFILE%%"^) >> "%TEMP%\%VBS_NAME%"
echo WinScriptHost.Run Chr^(34^) ^& "!VBS_EXE_PATH!" ^& Chr^(34^), 0 >> "%TEMP%\%VBS_NAME%"
echo Set WinScriptHost = Nothing >> "%TEMP%\%VBS_NAME%"

:: 4. Move to Startup folder
move /y "%TEMP%\%VBS_NAME%" "%STARTUP_FOLDER%\"

echo.
echo Success! Startup script created in: %STARTUP_FOLDER%
echo %APP_NAME% will now start hidden on every login.
echo.

:: 5. Launch it now so user doesn't have to restart
start wscript.exe "%STARTUP_FOLDER%\%VBS_NAME%"
echo Application launched in background.

pause