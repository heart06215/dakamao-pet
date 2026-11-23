# Generate placeholder sprite frames (one numbered PNG per frame) so the app
# can run before the real AI-generated frames are ready.
# Run: powershell -ExecutionPolicy Bypass -File tools\make_placeholder_frames.ps1
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$root = Join-Path $PSScriptRoot "..\DakamaoPet\PetMod\pet\dakamao"

# p = animation folder (relative to pet\dakamao)  n = frame count
# c = body color (R,G,B)  t = label drawn on frame
# Folder name IS the animation definition: <graphtype>/<name>_<a|b|c|single>
# a = A_Start, b = B_Loop, c = C_End
$actions = @(
    @{ p = "default\breathe_b";            n = 6; c = @(40, 130, 120); t = "default/breathe B_Loop" },
    @{ p = "startup\boot_single";          n = 2; c = @(70, 160, 70);  t = "startup/boot Single" },
    @{ p = "shutdown\bye_single";          n = 2; c = @(90, 90, 90);   t = "shutdown/bye Single" },
    @{ p = "say\talk_b";                   n = 2; c = @(200, 180, 60); t = "say/talk B_Loop" },
    @{ p = "sleep\zzz_b";                  n = 4; c = @(80, 80, 150);  t = "sleep/zzz B_Loop" },
    @{ p = "idel\blink_a";                 n = 2; c = @(120, 120, 120); t = "idel/blink A_Start" },
    @{ p = "idel\blink_b";                 n = 2; c = @(130, 130, 130); t = "idel/blink B_Loop" },
    @{ p = "idel\blink_c";                 n = 2; c = @(140, 140, 140); t = "idel/blink C_End" },
    @{ p = "idel\yawn_single";             n = 2; c = @(170, 140, 90);  t = "idel/yawn Single" },
    @{ p = "idel\look_around_single";      n = 3; c = @(110, 140, 170); t = "idel/look_around Single" },
    @{ p = "idel\groom_single";            n = 3; c = @(180, 150, 150); t = "idel/groom Single" },
    @{ p = "idel\tail_swish_single";       n = 2; c = @(150, 170, 110); t = "idel/tail_swish Single" },
    @{ p = "idel\stretch_single";          n = 2; c = @(160, 130, 180); t = "idel/stretch Single" },
    @{ p = "idel\doze_a";                  n = 2; c = @(100, 110, 130); t = "idel/doze A_Start" },
    @{ p = "idel\doze_b";                  n = 2; c = @(110, 120, 140); t = "idel/doze B_Loop" },
    @{ p = "idel\doze_c";                  n = 2; c = @(120, 130, 150); t = "idel/doze C_End" },
    @{ p = "touch_head\touch_a";           n = 4; c = @(220, 120, 160); t = "touch_head A_Start" },
    @{ p = "touch_head\touch_b";           n = 4; c = @(230, 140, 170); t = "touch_head B_Loop" },
    @{ p = "touch_head\touch_c";           n = 2; c = @(210, 110, 150); t = "touch_head C_End" },
    @{ p = "touch_body\touch_a";           n = 4; c = @(230, 160, 90);  t = "touch_body A_Start" },
    @{ p = "touch_body\touch_b";           n = 4; c = @(240, 175, 110); t = "touch_body B_Loop" },
    @{ p = "touch_body\touch_c";           n = 2; c = @(220, 150, 80);  t = "touch_body C_End" },
    @{ p = "raised_static\hold_a";         n = 2; c = @(150, 110, 200); t = "raised_static A_Start" },
    @{ p = "raised_static\hold_b";         n = 2; c = @(160, 120, 210); t = "raised_static B_Loop" },
    @{ p = "raised_static\hold_c";         n = 2; c = @(140, 100, 190); t = "raised_static C_End" },
    @{ p = "raised_dynamic\wiggle_single"; n = 2; c = @(170, 140, 220); t = "raised_dynamic Single" },
    @{ p = "common\fall_single";           n = 6; c = @(200, 80, 80);   t = "common/fall Single" },
    @{ p = "work\work_b";                  n = 2; c = @(150, 120, 80);  t = "work/work B_Loop" },
    @{ p = "switch_up\up_single";          n = 2; c = @(90, 180, 190);  t = "switch_up Single" },
    @{ p = "switch_down\down_single";      n = 2; c = @(70, 150, 160);  t = "switch_down Single" },
    @{ p = "switch_hunger\hungry_single";  n = 2; c = @(190, 140, 60);  t = "switch_hunger Single" },
    @{ p = "switch_thirsty\thirsty_single"; n = 2; c = @(100, 160, 200); t = "switch_thirsty Single" }
)

$total = 0
foreach ($a in $actions) {
    $dir = Join-Path $root $a.p
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    for ($i = 1; $i -le $a.n; $i++) {
        $bmp = New-Object System.Drawing.Bitmap 256, 256
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.Clear([System.Drawing.Color]::Transparent)

        $bob = 6 * ($i % 2)   # alternate frames shift vertically so loops are visible
        $body = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, $a.c[0], $a.c[1], $a.c[2]))
        $dark = [System.Drawing.Brushes]::Black

        # body + head + ears (placeholder cat)
        $g.FillEllipse($body, 78, 128 + $bob, 100, 78)
        $g.FillEllipse($body, 68, 42 + $bob, 120, 100)
        $g.FillPolygon($body, @(
            [System.Drawing.PointF]::new(80, 62 + $bob),
            [System.Drawing.PointF]::new(96, 16 + $bob),
            [System.Drawing.PointF]::new(116, 56 + $bob)))
        $g.FillPolygon($body, @(
            [System.Drawing.PointF]::new(140, 56 + $bob),
            [System.Drawing.PointF]::new(160, 16 + $bob),
            [System.Drawing.PointF]::new(176, 62 + $bob)))
        # eyes
        $g.FillEllipse($dark, 100, 82 + $bob, 12, 12)
        $g.FillEllipse($dark, 144, 82 + $bob, 12, 12)

        $font = New-Object System.Drawing.Font 'Consolas', 11
        $g.DrawString("$($a.t)  $i/$($a.n)", $font, [System.Drawing.Brushes]::DimGray, 6, 6)

        $g.Dispose()
        $bmp.Save((Join-Path $dir ("frame_{0:d2}.png" -f $i)), [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        $total++
    }
}
Write-Host "OK: generated $total placeholder frames under $root"
