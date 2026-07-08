@echo off
setlocal EnableDelayedExpansion

:: Build the CleverSwitch Windows release archive: a PyInstaller onefile exe
:: packed with the docs, config example, and install scripts.
:: Output: dist\cleverswitch_windows_x64.zip

set "APP_NAME=cleverswitch"
set "EXE_NAME=cleverswitch.exe"
set "ARCHIVE=cleverswitch_windows_x64"

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\.." || (echo [ERROR] Could not locate project root. & exit /b 1)
set "ROOT_DIR=%CD%"

:: ── Preflight ─────────────────────────────────────────────────────────
:: hidapi.dll must sit at the project root; the ";." packs it beside the exe.

if not exist "%ROOT_DIR%\hidapi.dll" (
    echo [ERROR] hidapi.dll not found at %ROOT_DIR%.
    echo Download it from https://github.com/libusb/hidapi/releases and place it at the project root.
    popd
    exit /b 1
)

:: ── Step 1: Runtime dependencies ──────────────────────────────────────
:: PyInstaller only bundles what is importable at build time — it does NOT
:: read pyproject.toml. A missing runtime dep is silently dropped (build-log
:: warning only) and the exe then crashes at launch with ModuleNotFoundError.
:: This is exactly how the broken v1.2.5 release shipped.

echo [INFO] Installing runtime dependencies...
pip install . || (echo [ERROR] pip install . failed. & popd & exit /b 1)
pip install pyinstaller || (echo [ERROR] pip install pyinstaller failed. & popd & exit /b 1)

echo [INFO] Sanity-checking imports...
python -c "import yaml; print('pyyaml ok')" || (echo [ERROR] pyyaml not importable - aborting before a broken build. & popd & exit /b 1)

:: ── Step 2: PyInstaller ───────────────────────────────────────────────
:: --hidden-import yaml is a safety net against a missed auto-detect.

echo [INFO] Building binary with PyInstaller...
pyinstaller --onefile --name %APP_NAME% --paths src --hidden-import yaml --add-binary "hidapi.dll;." src\cleverswitch\__main__.py || (echo [ERROR] PyInstaller build failed. & popd & exit /b 1)

:: ── Step 3: Smoke-test ────────────────────────────────────────────────
:: Catch a dropped dependency here instead of on a user's machine.

echo [INFO] Smoke-testing the binary...
"dist\%EXE_NAME%" --version || (echo [ERROR] Binary failed to start - a build dependency was likely dropped; see the dependency-install step. & popd & exit /b 1)

:: ── Step 4: Assemble archive ──────────────────────────────────────────

echo [INFO] Assembling %ARCHIVE%.zip...
set "STAGE=dist\%ARCHIVE%"
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"
copy /y "dist\%EXE_NAME%" "%STAGE%\" >nul
copy /y README.md "%STAGE%\" >nul
copy /y LICENSE.txt "%STAGE%\" >nul
copy /y docs\Installation.md "%STAGE%\" >nul
copy /y config.example.yaml "%STAGE%\" >nul
copy /y scripts\windows\install.bat "%STAGE%\" >nul
copy /y scripts\windows\uninstall.bat "%STAGE%\" >nul
copy /y scripts\windows\setup_startup_windows.bat "%STAGE%\" >nul
powershell -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath 'dist\%ARCHIVE%.zip' -Force" || (echo [ERROR] Compress-Archive failed. & popd & exit /b 1)
rmdir /s /q "%STAGE%"

:: ── Done ─────────────────────────────────────────────────────────────

echo [OK] Release archive ready: dist\%ARCHIVE%.zip
popd
