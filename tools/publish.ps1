# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# 一键发布：校验配置、生成去重素材、单文件发布、写 SHA256 报告并复制到根目录。
param(
    [string]$Version,
    [switch]$Validate,
    [switch]$Tag,
    [switch]$SkipDedup
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = Join-Path $root 'DakamaoPet\DakamaoPet.csproj'
$output = Join-Path $root 'release'
$python = Join-Path $root '.venv-animation\Scripts\python.exe'
$dotnet = Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'
if (-not (Test-Path $dotnet)) { $dotnet = 'dotnet' }

function Read-ProjectVersion {
    [xml]$xml = Get-Content -LiteralPath $project -Raw -Encoding UTF8
    $value = $xml.Project.PropertyGroup | ForEach-Object { $_.Version } |
        Where-Object { $_ } | Select-Object -First 1
    if (-not $value) { throw 'csproj 中没有找到 Version。' }
    return [string]$value
}

if (-not $Version) { $Version = Read-ProjectVersion }
if ($Version -notmatch '^\d+\.\d+\.\d+([-.][0-9A-Za-z.-]+)?$') {
    throw "版本号格式无效：$Version"
}

$running = Get-Process -Name '大卡猫' -ErrorAction SilentlyContinue
if ($running) {
    throw '大卡猫正在运行，请先从托盘或菜单退出后再发布。'
}
if (-not (Test-Path $python) -and -not $SkipDedup) {
    throw '缺少 .venv-animation，请先运行 tools\setup_env.ps1。'
}

$commit = (& git -C $root rev-parse --short HEAD 2>$null | Out-String).Trim()
$dirty = (& git -C $root status --porcelain 2>$null | Out-String).Trim()
if ($dirty) { Write-Warning '工作区存在未提交改动，发布包将包含当前文件内容。' }

if ($Validate) {
    if (-not (Test-Path $python)) { throw '校验需要 .venv-animation，请先运行 tools\setup_env.ps1。' }
    Write-Host '=== 素材校验 ==='
    & $python (Join-Path $root 'tools\validate_picture_style.py')
    if ($LASTEXITCODE -ne 0) { throw '画面风格校验失败。' }
    & $python (Join-Path $root 'tools\validate_smooth_playback.py')
    if ($LASTEXITCODE -ne 0) { throw '序列播放校验失败。' }
}

$publishArgs = @(
    'publish', $project,
    '-p:PublishProfile=Portable',
    ('-p:Version=' + $Version),
    '-c', 'Release',
    '-o', $output,
    '--nologo'
)
$dedupReport = $null
if (-not $SkipDedup) {
    Write-Host '=== 生成去重素材 ==='
    $dedup = Join-Path $root 'DakamaoPet\obj\petmod-dedup'
    $json = (& $python (Join-Path $root 'tools\build_dedup_assets.py') --out $dedup --verify | Out-String)
    if ($LASTEXITCODE -ne 0) { throw '去重素材生成失败。' }
    if (-not (Test-Path -LiteralPath (Join-Path $dedup 'layout.json'))) {
        throw '去重素材缺少 layout.json。'
    }
    $dedupReport = $json | ConvertFrom-Json
    Write-Host ("唯一内容 {0} / {1} 个文件，节省 {2:N1} MB" -f `
        $dedupReport.unique_files, $dedupReport.files, ($dedupReport.saved_bytes / 1MB))
    $publishArgs += ('-p:DedupAssetsPath=' + $dedup)
}

Write-Host '=== 单文件发布 ==='
if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Recurse -Force }
& $dotnet @publishArgs
if ($LASTEXITCODE -ne 0) { throw '发布失败，请查看上面的构建错误。' }

$exe = Join-Path $output '大卡猫.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw '发布没有生成大卡猫.exe。' }
if (-not $SkipDedup -and (Get-Item -LiteralPath $exe).Length -gt 750MB) {
    throw '发布体积异常（仍接近未去重大小），请检查 DedupAssetsPath 是否生效。'
}

$assetMode = if ($SkipDedup) { 'full' } else { 'dedup' }
$named = Join-Path $output ("DakamaoPet-{0}-win-x64.exe" -f $Version)
Move-Item -LiteralPath $exe -Destination $named -Force
Copy-Item -LiteralPath $named -Destination (Join-Path $root '大卡猫.exe') -Force

foreach ($doc in 'README.md', 'LICENSE', 'THIRD-PARTY-NOTICES.md') {
    $source = Join-Path $root $doc
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $output $doc) -Force
    }
}

Write-Host '=== 计算校验值 ==='
$sha = (Get-FileHash -LiteralPath $named -Algorithm SHA256).Hash
$size = (Get-Item -LiteralPath $named).Length
$sizeMb = [math]::Round($size / 1MB, 1)
$poseRevision = 'v26_whole_body'
$sourceJson = Join-Path $root 'DakamaoPet\PetMod\fluid\sleep-roll-source.json'
if (Test-Path -LiteralPath $sourceJson) {
    $poseRevision = (Get-Content -LiteralPath $sourceJson -Raw | ConvertFrom-Json).revision
}

$assetFiles = $null
$uniqueAssetFiles = $null
$savedBytes = $null
if ($dedupReport) {
    $assetFiles = $dedupReport.files
    $uniqueAssetFiles = $dedupReport.unique_files
    $savedBytes = $dedupReport.saved_bytes
}
$report = [ordered]@{
    Version = $Version
    Root = $named
    SHA256 = $sha
    ReleaseMatches = $true
    Length = $size
    AssetMode = $assetMode
    AssetFiles = $assetFiles
    UniqueAssetFiles = $uniqueAssetFiles
    SavedBytes = $savedBytes
    PoseRevision = $poseRevision
    Commit = $commit
    PublishedAt = (Get-Date).ToString('o')
}
$reportPath = Join-Path $root ("tools\qa\publish-{0}.json" -f $Version)
$reportJson = $report | ConvertTo-Json
[System.IO.File]::WriteAllText($reportPath, $reportJson + "`n", (New-Object System.Text.UTF8Encoding($false)))

if ($Tag) {
    $tagName = "v$Version"
    & git -C $root rev-parse -q --verify "refs/tags/$tagName" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { throw "标签 $tagName 已存在。" }
    & git -C $root tag -a $tagName -m "Release $tagName"
    if ($LASTEXITCODE -ne 0) { throw '创建 Git 标签失败。' }
    Write-Host "已创建本地标签 $tagName（尚未推送）。"
}

$url = "https://github.com/heart06215/dakamao-pet/releases/download/v$Version/DakamaoPet-$Version-win-x64.exe"
$notesPath = Join-Path $output ("RELEASE-{0}.md" -f $Version)
$notes = @"
# 大卡猫 v$Version

Windows x64 单文件便携版，双击即运行，无需安装 .NET。

- 文件：DakamaoPet-$Version-win-x64.exe（$sizeMb MB）
- SHA256：$sha
- 素材：$assetMode$(if ($dedupReport) { "（$($dedupReport.unique_files) 个唯一文件，去重节省 $([math]::Round($dedupReport.saved_bytes / 1MB, 1)) MB）" })
- 提交：$commit

完整说明、许可与第三方声明见仓库 README、LICENSE 与 THIRD-PARTY-NOTICES.md。
"@
[System.IO.File]::WriteAllText($notesPath, $notes, (New-Object System.Text.UTF8Encoding($false)))

Write-Host ''
Write-Host '=== 完成 ==='
Write-Host ("输出：{0}（{1} MB）" -f $named, $sizeMb)
Write-Host ("根目录副本：{0}" -f (Join-Path $root '大卡猫.exe'))
Write-Host ("报告：{0}" -f $reportPath)
Write-Host ''
Write-Host 'README 可粘贴：'
Write-Host ("从 [Releases v{0}](https://github.com/heart06215/dakamao-pet/releases/tag/v{0}) 下载 [DakamaoPet-{0}-win-x64.exe]({1})（即 大卡猫.exe，{2} MB）" -f $Version, $url, $sizeMb)
Write-Host ("SHA256：{0}" -f $sha)
Write-Host ''
Write-Host '上传示例：'
Write-Host ("gh release create v{0} `"{1}`" --title `"大卡猫 v{0}`" --notes-file release\RELEASE-{0}.md" -f $Version, $named)
