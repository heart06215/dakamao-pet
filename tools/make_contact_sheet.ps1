# Assemble all frames of one action folder into a single contact-sheet PNG,
# so visual QA costs one image read instead of one per frame.
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\make_contact_sheet.ps1 -Folder touch_head\touch_a
#   powershell -ExecutionPolicy Bypass -File tools\make_contact_sheet.ps1 -Folder <absolute path> -Out <file>
param(
    [Parameter(Mandatory = $true)][string]$Folder,
    [string]$Out = ""
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$petRoot = Join-Path $PSScriptRoot "..\DakamaoPet\PetMod\pet\dakamao"
$dir = $Folder
if (-not (Test-Path $dir)) { $dir = Join-Path $petRoot $Folder }
if (-not (Test-Path $dir)) { throw "Folder not found: $Folder" }

$frames = Get-ChildItem -LiteralPath $dir -Filter frame_*.png | Sort-Object Name
if (-not $frames) { throw "No frame_*.png found in $dir" }

$cell = 256
$labelH = 28
$sheetW = $cell * $frames.Count
$sheetH = $cell + $labelH
$bmp = New-Object System.Drawing.Bitmap $sheetW, $sheetH
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 45, 45, 55))  # dark bg: transparent frames stay visible

$font = New-Object System.Drawing.Font 'Consolas', 12
$white = [System.Drawing.Brushes]::White
for ($i = 0; $i -lt $frames.Count; $i++) {
    $img = [System.Drawing.Image]::FromFile($frames[$i].FullName)
    $g.DrawImage($img, $i * $cell, 0, $cell, $cell)
    $g.DrawString($frames[$i].Name, $font, $white, ($i * $cell + 4), ($cell + 4))
    $img.Dispose()
}
$g.Dispose()

if ($Out -eq "") {
    $qaDir = Join-Path $PSScriptRoot "qa"
    New-Item -ItemType Directory -Force -Path $qaDir | Out-Null
    $rel = $Folder -replace '[\\/]+', '_'
    $Out = Join-Path $qaDir ("qa_" + $rel + ".png")
}
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Host "OK: $Out  ($($frames.Count) frames, ${sheetW}x${sheetH})"
