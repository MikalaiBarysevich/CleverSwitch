# Edge-switch setup for scripts/windows/install.bat.
#
# Prompts for the modifier and the edges to map, then writes or appends the edge_switch section to
# %USERPROFILE%\.config\cleverswitch\config.yaml. Windows needs nothing else: Raw Input is always available.
# Writes UTF-8 without a BOM (harmless either way, but keeps the file plain).

$ErrorActionPreference = "Stop"
$ConfigPath = Join-Path $env:USERPROFILE ".config\cleverswitch\config.yaml"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# Read-Host needs a console; when stdin is redirected (a script or a test driving the wizard) read the line.
function Read-Answer([string]$Prompt) {
    if ([Console]::IsInputRedirected) {
        Write-Host "$Prompt"
        $line = [Console]::In.ReadLine()
        if ($null -eq $line) { return "" }
        return $line
    }
    return "$(Read-Host "$Prompt")"
}

function Ask-YesNo([string]$Prompt) {
    while ($true) {
        $answer = (Read-Answer "$Prompt [y/n]").ToLower()
        switch ($answer) {
            { $_ -in @("y", "yes") } { return $true }
            { $_ -in @("n", "no", "") } { return $false }
            default { Write-Host "Please answer y or n." }
        }
    }
}

function Ask-Modifier {
    Write-Host "Modifier to hold:"
    Write-Host "  1) ctrl"
    Write-Host "  2) alt"
    Write-Host "  3) shift"
    Write-Host "  4) meta"
    while ($true) {
        $answer = (Read-Answer "Choose 1-4 [1]").Trim()
        switch ($answer) {
            { $_ -in @("", "1") } { return "ctrl" }
            "2" { return "alt" }
            "3" { return "shift" }
            "4" { return "meta" }
            default { Write-Host "Choose 1, 2, 3 or 4." }
        }
    }
}

function Ask-Host([string]$Label) {
    while ($true) {
        $value = (Read-Answer "$Label edge -> host 1-3 (Enter to skip)").Trim()
        if ($value -eq "") { return "" }
        if ($value -in @("1", "2", "3")) { return $value }
        Write-Host "Host must be 1, 2, 3 or empty."
    }
}

if (-not (Ask-YesNo "Configure edge switch (switch hosts by holding a modifier at a screen edge)?")) {
    Write-Host "==> Skipped. See docs/features/edge-switch.md to set it up later."
    exit 0
}

$modifier = Ask-Modifier
$edges = [ordered]@{}
$edges["left"] = Ask-Host "Left"
$edges["right"] = Ask-Host "Right"
$edges["top"] = Ask-Host "Top"
$edges["bottom"] = Ask-Host "Bottom"

$mapped = @($edges.Keys | Where-Object { $edges[$_] -ne "" })
if ($mapped.Count -eq 0) {
    Write-Host "==> No edge was mapped, so there is nothing to write; edge switch stays off."
    exit 0
}

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("edge_switch:")
$lines.Add("  enabled: true")
$lines.Add("  modifier: $modifier")
$lines.Add("  edges:")
foreach ($edge in $edges.Keys) {
    if ($edges[$edge] -ne "") { $lines.Add("    ${edge}: $($edges[$edge])") }
}

$directory = Split-Path -Parent $ConfigPath
if (-not (Test-Path $directory)) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }

$existing = ""
if (Test-Path $ConfigPath) { $existing = Get-Content -LiteralPath $ConfigPath -Raw }

if ($existing -match "(?m)^edge_switch:") {
    if (-not (Ask-YesNo "edge_switch is already configured in $ConfigPath. Replace it?")) {
        Write-Host "==> Kept the existing edge_switch section."
        exit 0
    }
    # Drop every top-level section and put the new one where the first was. A commented-out or indented
    # "edge_switch:" is not matched, so only real sections go.
    $all = New-Object System.Collections.Generic.List[string]
    Get-Content -LiteralPath $ConfigPath | ForEach-Object { $all.Add($_) }

    $sections = @($all | Where-Object { $_ -match '^edge_switch:' }).Count
    if ($sections -gt 1) {
        Write-Host "==> $ConfigPath has $sections edge_switch sections; replacing all of them with one."
    }

    $result = New-Object System.Collections.Generic.List[string]
    $written = $false
    $skipping = $false
    foreach ($line in $all) {
        if ($line -match '^edge_switch:') {
            if (-not $written) {
                foreach ($newLine in $lines) { $result.Add($newLine) }
                $written = $true
            }
            $skipping = $true
            continue
        }
        if ($skipping) {
            if ($line -match '^\s' -or $line -eq "") { continue }
            $skipping = $false
            $result.Add("")
        }
        $result.Add($line)
    }
    [System.IO.File]::WriteAllLines($ConfigPath, $result, $Utf8NoBom)
    Write-Host "==> edge_switch replaced in $ConfigPath"
    exit 0
}

$text = ($lines -join "`r`n") + "`r`n"
if ($existing) {
    [System.IO.File]::AppendAllText($ConfigPath, "`r`n# Edge switch (added by the installer)`r`n$text", $Utf8NoBom)
} else {
    [System.IO.File]::WriteAllText($ConfigPath, "# CleverSwitch configuration (created by the installer)`r`n$text", $Utf8NoBom)
}

Write-Host "==> edge_switch written to $ConfigPath"
exit 0
