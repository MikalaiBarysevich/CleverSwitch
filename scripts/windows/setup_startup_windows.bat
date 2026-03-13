@echo off
setlocal

:: 1. Define Names
set "APP_NAME=cleverswitch"
set "EXE_NAME=cleverswitch.exe"
set "VBS_NAME=run_cleverswitch.vbs"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

:: 2. Find the executable path
:: Check current folder first, then check system PATH
if exist "%~dp0%EXE_NAME%" (
    set "EXE_PATH=%~dp0%EXE_NAME%"
) else (
    for %%i in (%EXE_NAME%) do set "EXE_PATH=%%~$PATH:i"
)

if "%EXE_PATH%"=="" (
    echo Error: %EXE_NAME% not found in this folder or in your System PATH.
    echo Please place this .bat file in the same folder as %EXE_NAME%.
    pause
    exit /b
)

echo Found %APP_NAME% at: %EXE_PATH%

:: 3. Create the VBScript wrapper (to run hidden)
:: We use '0' to hide the console window
echo Set WinScriptHost = CreateObject^("WScript.Shell"^) > "%TEMP%\%VBS_NAME%"
echo WinScriptHost.Run Chr^(34^) ^& "%EXE_PATH%" ^& Chr^(34^), 0 >> "%TEMP%\%VBS_NAME%"
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