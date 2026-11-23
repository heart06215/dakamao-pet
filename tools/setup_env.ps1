# Environment setup/check for the Dakamao desktop-pet pipeline.
# Safe to run repeatedly. Missing pieces are installed unless -CheckOnly is given
# (winget may show a UAC prompt for the .NET SDK install).
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\setup_env.ps1
#   powershell -ExecutionPolicy Bypass -File tools\setup_env.ps1 -CheckOnly
param([switch]$CheckOnly)
$ErrorActionPreference = "Continue"
$ready = New-Object System.Collections.Generic.List[string]
$todo = New-Object System.Collections.Generic.List[string]
$dotnet = Join-Path $env:ProgramFiles "dotnet\dotnet.exe"
$proj = Join-Path $PSScriptRoot "..\DakamaoPet\DakamaoPet.csproj"

function Test-Sdk8 {
    if (-not (Test-Path $dotnet)) { return $false }
    $sdks = & $dotnet --list-sdks 2>$null
    return [bool]($sdks | Where-Object { $_ -match "^8\." })
}

Write-Host "=== 1/5 .NET SDK 8 (build & run the pet host) ==="
$sdkOk = Test-Sdk8
if (-not $sdkOk -and -not $CheckOnly) {
    Write-Host "MISSING -> installing via winget (a UAC prompt may appear)..."
    winget install Microsoft.DotNet.SDK.8 --accept-source-agreements --accept-package-agreements --silent | Out-Null
    $sdkOk = Test-Sdk8
}
if ($sdkOk) { $ready.Add(".NET SDK 8"); Write-Host "READY" }
else { $todo.Add(".NET SDK 8  ->  winget install Microsoft.DotNet.SDK.8"); Write-Host "MISSING" }

Write-Host "=== 2/5 NuGet feed reachable (package restore) ==="
$nugetOk = $false
try {
    $r = Invoke-WebRequest -Uri "https://api.nuget.org/v3/index.json" -UseBasicParsing -TimeoutSec 15
    $nugetOk = ($r.StatusCode -eq 200)
} catch { $nugetOk = $false }
if ($nugetOk) { $ready.Add("NuGet feed"); Write-Host "READY" }
else { $todo.Add("NuGet feed unreachable -> check network/proxy"); Write-Host "MISSING" }

Write-Host "=== 3/5 GDI+ / System.Drawing (frame post-processing) ==="
$gdiOk = $true
try { Add-Type -AssemblyName System.Drawing } catch { $gdiOk = $false }
if ($gdiOk) { $ready.Add("System.Drawing"); Write-Host "READY" }
else { $todo.Add("System.Drawing unavailable (should never happen on Windows)"); Write-Host "MISSING" }

Write-Host "=== 4/5 placeholder frames / animation pack ==="
$frames = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "..\DakamaoPet\PetMod\pet\dakamao") -Recurse -Filter *.png -ErrorAction SilentlyContinue
if ($frames -and $frames.Count -ge 80) { $ready.Add("Placeholder frames ($($frames.Count))"); Write-Host "READY ($($frames.Count) frames)" }
else { $todo.Add("Placeholder frames missing -> powershell -File tools\make_placeholder_frames.ps1"); Write-Host "MISSING" }

Write-Host "=== 5/5 three-view reference (user provides) ==="
$ex = Join-Path $PSScriptRoot "..\example"
if (Test-Path $ex) {
    $imgs = Get-ChildItem -LiteralPath $ex -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -match "\.(png|jpg|jpeg|webp)$" }
    if ($imgs) { $ready.Add("Three-view reference in example/ ($($imgs.Count) file(s))"); Write-Host "READY ($($imgs.Count) image file(s))" }
    else { $todo.Add("example/ exists but has no image -> user puts the three-view sheet there"); Write-Host "MISSING" }
} else {
    $todo.Add("example/ directory not found -> user creates it and puts the three-view sheet inside"); Write-Host "MISSING"
}

Write-Host ""
Write-Host "=== build check (skipped with -CheckOnly) ==="
if ($sdkOk -and -not $CheckOnly) {
    & $dotnet build $proj --nologo -v q > (Join-Path $PSScriptRoot "build.log") 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host "BUILD OK (log: tools\build.log)" }
    else { Write-Host "BUILD FAILED - see tools\build.log"; Get-Content (Join-Path $PSScriptRoot "build.log") -Tail 15 }
} else {
    Write-Host "skipped"
}

Write-Host ""
Write-Host "=== summary ==="
foreach ($r in $ready) { Write-Host ("  [READY]   " + $r) }
foreach ($t in $todo) { Write-Host ("  [MISSING] " + $t) }
if ($todo.Count -eq 0) { Write-Host "Environment fully ready. Reminder: image generation needs the GPT/Codex image model, which cannot be checked from this script." }
