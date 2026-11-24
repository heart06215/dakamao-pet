# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# 环境安装/检查：.NET 8、NuGet、Python 素材环境、GDI+、动画包与参考图。
# 可重复运行。缺少的组件会尝试安装，除非传入 -CheckOnly。
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools\setup_env.ps1
#   powershell -ExecutionPolicy Bypass -File tools\setup_env.ps1 -CheckOnly
param([switch]$CheckOnly)
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$ready = New-Object System.Collections.Generic.List[string]
$todo = New-Object System.Collections.Generic.List[string]
$dotnet = Join-Path $env:ProgramFiles "dotnet\dotnet.exe"
$proj = Join-Path $root "DakamaoPet\DakamaoPet.csproj"
$venv = Join-Path $root ".venv-animation"
$venvPython = Join-Path $venv "Scripts\python.exe"
$requirements = Join-Path $root "tools\animation_requirements.txt"

function Test-Sdk8 {
    if (-not (Test-Path $dotnet)) { return $false }
    $sdks = & $dotnet --list-sdks 2>$null
    return [bool]($sdks | Where-Object { $_ -match "^8\." })
}

Write-Host "=== 1/6 .NET SDK 8（构建与运行桌宠） ==="
$sdkOk = Test-Sdk8
if (-not $sdkOk -and -not $CheckOnly) {
    Write-Host "MISSING -> 通过 winget 安装（可能弹出 UAC）..."
    winget install Microsoft.DotNet.SDK.8 --accept-source-agreements --accept-package-agreements --silent | Out-Null
    $sdkOk = Test-Sdk8
}
if ($sdkOk) { $ready.Add(".NET SDK 8"); Write-Host "READY" }
else { $todo.Add(".NET SDK 8  ->  winget install Microsoft.DotNet.SDK.8"); Write-Host "MISSING" }

Write-Host "=== 2/6 NuGet 源可访问（包还原） ==="
$nugetOk = $false
try {
    $r = Invoke-WebRequest -Uri "https://api.nuget.org/v3/index.json" -UseBasicParsing -TimeoutSec 15
    $nugetOk = ($r.StatusCode -eq 200)
} catch { $nugetOk = $false }
if ($nugetOk) { $ready.Add("NuGet feed"); Write-Host "READY" }
else { $todo.Add("NuGet feed unreachable -> check network/proxy"); Write-Host "MISSING" }

Write-Host "=== 3/6 Python 素材环境（生成/校验/去重） ==="
$pythonOk = $false
if (-not (Test-Path $venvPython)) {
    if ($CheckOnly) { Write-Host "MISSING .venv-animation" }
    else {
        Write-Host "创建 .venv-animation ..."
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($launcher) { & py -3.12 -m venv $venv } else { & python -m venv $venv }
    }
}
if (Test-Path $venvPython) {
    $deps = & $venvPython -c "import PIL, numpy, cv2; print('ok')" 2>$null
    if ($deps -ne "ok" -and -not $CheckOnly) {
        Write-Host "安装 Python 依赖 ..."
        & $venvPython -m pip install --disable-pip-version-check -r $requirements
        $deps = & $venvPython -c "import PIL, numpy, cv2; print('ok')" 2>$null
    }
    $pythonOk = ($deps -eq "ok")
}
if ($pythonOk) { $ready.Add("Python 素材环境"); Write-Host "READY" }
else { $todo.Add("Python 环境缺失 -> 安装 Python 3.12 后重跑本脚本"); Write-Host "MISSING" }

Write-Host "=== 4/6 GDI+ / System.Drawing（帧后处理） ==="
$gdiOk = $true
try { Add-Type -AssemblyName System.Drawing } catch { $gdiOk = $false }
if ($gdiOk) { $ready.Add("System.Drawing"); Write-Host "READY" }
else { $todo.Add("System.Drawing unavailable (should never happen on Windows)"); Write-Host "MISSING" }

Write-Host "=== 5/6 动画帧素材 ==="
$frames = Get-ChildItem -LiteralPath (Join-Path $root "DakamaoPet\PetMod\pet\dakamao") -Recurse -Filter *.png -ErrorAction SilentlyContinue
if ($frames -and $frames.Count -ge 80) { $ready.Add("Animation frames ($($frames.Count))"); Write-Host "READY ($($frames.Count) frames)" }
else { $todo.Add("动画帧缺失 -> 重新克隆仓库或运行 tools\make_placeholder_frames.ps1"); Write-Host "MISSING" }

Write-Host "=== 6/6 三视图参考（由用户提供） ==="
$ex = Join-Path $root "example"
if (Test-Path $ex) {
    $imgs = Get-ChildItem -LiteralPath $ex -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -match "\.(png|jpg|jpeg|webp)$" }
    if ($imgs) { $ready.Add("Three-view reference in example/ ($($imgs.Count) file(s))"); Write-Host "READY ($($imgs.Count) image file(s))" }
    else { $todo.Add("example/ exists but has no image -> user puts the three-view sheet there"); Write-Host "MISSING" }
} else {
    $todo.Add("example/ directory not found -> user creates it and puts the three-view sheet inside"); Write-Host "MISSING"
}

Write-Host ""
Write-Host "=== 构建检查（-CheckOnly 时跳过） ==="
if ($sdkOk -and -not $CheckOnly) {
    & $dotnet build $proj --nologo -v q > (Join-Path $root "tools\build.log") 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "BUILD OK (log: tools\build.log)"
        if ($pythonOk) {
            & $venvPython (Join-Path $root "tools\build_dedup_assets.py") --check
        }
    }
    else { Write-Host "BUILD FAILED - see tools\build.log"; Get-Content (Join-Path $root "tools\build.log") -Tail 15 }
} else {
    Write-Host "skipped"
}

Write-Host ""
Write-Host "=== 汇总 ==="
foreach ($r in $ready) { Write-Host ("  [READY]   " + $r) }
foreach ($t in $todo) { Write-Host ("  [MISSING] " + $t) }
if ($todo.Count -eq 0) {
    Write-Host "环境已就绪。发布：powershell -ExecutionPolicy Bypass -File tools\publish.ps1"
    Write-Host "提醒：图像生成需要外部图像模型，本脚本无法检查。"
}
