# Writes $env:NEW_PATH to HKCU\Environment\PATH as REG_EXPAND_SZ - the type
# Windows normally stores PATH as, which lets entries like %JAVA_HOME%\bin
# expand on read. [Environment]::SetEnvironmentVariable writes plain REG_SZ
# instead, silently downgrading the type and breaking any %VARIABLE%-style
# entries elsewhere in PATH for every user who runs the installer/uninstaller
# - not just people with long PATHs.
#
# Kept as its own file (invoked via `-File`, not inlined as a `-Command`
# one-liner) so the registry/.NET calls below - which need their own
# parentheses and braces - never have to coexist with cmd.exe's parenthesized
# if/else blocks on the same line.
#
# The new value is read from $env:NEW_PATH (set by the calling batch script,
# inherited into this process's environment) rather than a -Value command-
# line parameter. That sidesteps two argv-passing pitfalls: Windows argv
# quoting mangles a trailing backslash right before a closing quote (e.g.
# "...\Git\bin\" arrives with the escaped quote folded into the value), and
# an empty-string argument isn't guaranteed to bind cleanly to a Mandatory
# parameter on every PowerShell version - which could otherwise prompt
# interactively for the value and hang the caller instead of erroring.
#
# install.bat/uninstall.bat check the exit code after calling this and only
# report success if it's 0, so a failure here (e.g. a restrictive execution
# policy or PowerShell Constrained Language Mode blocking the registry call)
# surfaces as an error instead of a false "PATH updated".
#
# CS_PATH_WRITE=1 must be set by the caller. This script ships in the release
# zip right next to install.bat/uninstall.bat, and Windows registers a "Run
# with PowerShell" verb for .ps1 files, so it can be launched directly by
# accident. Without this guard, a bare run would fall through to $env:NEW_PATH
# being unset and silently write an empty PATH - the marker turns that into
# an explicit error instead. NEW_PATH-absent-with-the-marker-present is still
# a legitimate write (uninstalling the sole PATH entry leaves NEW_PATH
# undefined - see the note in uninstall.bat), so the guard only checks for
# the marker, not for NEW_PATH itself.

if ($env:CS_PATH_WRITE -ne '1') {
    Write-Error 'set_user_path.ps1 must be run via install.bat or uninstall.bat, not directly.'
    exit 1
}

$value = $env:NEW_PATH
if ($null -eq $value) { $value = '' }

try {
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
    # Best-effort backup of the pre-write value, as insurance against the
    # empty-PATH case above being hit some other way. Not load-bearing for
    # correctness, so a failure here doesn't block the real write.
    try {
        $previous = $key.GetValue('PATH', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        $key.SetValue('PATH_CleverSwitchBackup', $previous, [Microsoft.Win32.RegistryValueKind]::ExpandString)
    } catch {
        # Non-fatal - proceed to the real write either way.
    }
    $key.SetValue('PATH', $value, [Microsoft.Win32.RegistryValueKind]::ExpandString)
    $key.Close()
} catch {
    Write-Error $_
    exit 1
}
