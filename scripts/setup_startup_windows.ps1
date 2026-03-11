# 1. Define paths
$AppName = "cleverswitch"
$ExeName = "cleverswitch.exe"
$VbsName = "run_cleverswitch.vbs"
$StartupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"

# 2. Find the executable path
# Check if it's in the current folder, otherwise look in the PATH
$ExePath = Get-Command $ExeName -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source

if (-not $ExePath) {
    $ExePath = Join-Path $PSScriptRoot $ExeName
}

if (-not (Test-Path $ExePath)) {
    Write-Host "Error: $ExeName not found. Please ensure it's in your PATH or this folder." -ForegroundColor Red
    exit
}

Write-Host "Found executable at: $ExePath"

# 3. Create the VBScript wrapper
# This script runs the EXE with '0' as the window style (Hidden)
$VbsContent = @'
Set WinScriptHost = CreateObject("WScript.Shell")
WinScriptHost.Run Chr(34) & "REPLACE_ME_PATH" & Chr(34), 0
Set WinScriptHost = Nothing
'@ -replace "REPLACE_ME_PATH", $ExePath

$VbsPath = Join-Path $StartupFolder $VbsName
$VbsContent | Out-File -FilePath $VbsPath -Encoding ascii

# 4. Verify and Launch
Write-Host "Success! VBS script created in: $StartupFolder" -ForegroundColor Green
Write-Host "CleverSwitch will now start hidden on every login."

# Optional: Run it now so they don't have to restart
Start-Process wscript.exe -ArgumentList "`"$VbsPath`""
Write-Host "Application launched in background."
