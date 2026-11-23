# Post-process generated pet frames: resize to target size and turn the white
# background into transparency.
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\process_frames.ps1
#   powershell -ExecutionPolicy Bypass -File tools\process_frames.ps1 -Path <dir> -Size 256 -Tolerance 30
param(
    [string]$Path = "",
    [int]$Size = 256,
    [int]$Tolerance = 30
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

if ($Path -eq "") {
    $Path = Join-Path $PSScriptRoot "..\DakamaoPet\PetMod\pet\dakamao"
}
if (-not (Test-Path $Path)) {
    throw "Path not found: $Path"
}

function Convert-Frame {
    param([string]$File, [int]$Size, [int]$Tolerance)

    # Load via memory stream: FromFile locks the file and blocks saving in place
    $srcBytes = [System.IO.File]::ReadAllBytes($File)
    $ms = New-Object System.IO.MemoryStream
    $ms.Write($srcBytes, 0, $srcBytes.Length)
    $src = [System.Drawing.Bitmap]::FromStream($ms)

    # Resize (aspect-preserving, centered) if not already the target size
    $work = $src
    if ($src.Width -ne $Size -or $src.Height -ne $Size) {
        $scale = [Math]::Min($Size / $src.Width, $Size / $src.Height)
        $nw = [int][Math]::Round($src.Width * $scale)
        $nh = [int][Math]::Round($src.Height * $scale)
        $ox = [int](($Size - $nw) / 2)
        $oy = [int](($Size - $nh) / 2)
        $work = New-Object System.Drawing.Bitmap $Size, $Size
        $g = [System.Drawing.Graphics]::FromImage($work)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.DrawImage($src, $ox, $oy, $nw, $nh)
        $g.Dispose()
    }

    # White -> transparent via LockBits (BGRA)
    $rect = New-Object System.Drawing.Rectangle 0, 0, $work.Width, $work.Height
    $data = $work.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadWrite, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $len = $data.Stride * $work.Height
    $bytes = New-Object byte[] $len
    [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $len)
    $max = 255 - $Tolerance
    $cleared = 0
    for ($i = 0; $i -lt $len; $i += 4) {
        $b = $bytes[$i]; $gg = $bytes[$i + 1]; $r = $bytes[$i + 2]
        if ($r -ge $max -and $gg -ge $max -and $b -ge $max -and
            ([Math]::Abs($r - $gg) -le 8) -and ([Math]::Abs($gg - $b) -le 8)) {
            $bytes[$i + 3] = 0
            $cleared++
        }
    }
    [System.Runtime.InteropServices.Marshal]::Copy($bytes, 0, $data.Scan0, $len)
    $work.UnlockBits($data)

    $work.Save($File, [System.Drawing.Imaging.ImageFormat]::Png)
    $work.Dispose()
    $src.Dispose()
    $ms.Dispose()
    return $cleared
}

$files = Get-ChildItem -LiteralPath $Path -Recurse -Filter *.png | Sort-Object FullName
$done = 0
foreach ($f in $files) {
    $cleared = Convert-Frame -File $f.FullName -Size $Size -Tolerance $Tolerance
    $rel = $f.FullName.Substring((Resolve-Path $Path).Path.Length + 1)
    Write-Host ("{0}  cleared={1}px" -f $rel, $cleared)
    $done++
}
Write-Host "OK: processed $done frame(s) at ${Size}x${Size}"
