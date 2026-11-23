param()
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$project = Join-Path $root 'DakamaoPet\DakamaoPet.csproj'
$output = Join-Path $root 'release'

& dotnet publish $project -p:PublishProfile=Portable -c Release -o $output
if ($LASTEXITCODE -ne 0) { throw '发布失败，请查看上面的构建错误。' }

$exe = Join-Path $output '大卡猫.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw '发布没有生成大卡猫.exe。' }

# A project-root copy makes the entry point obvious. Both copies are portable.
Copy-Item -LiteralPath $exe -Destination (Join-Path $root '大卡猫.exe') -Force
Write-Host ('完成：双击 ' + (Join-Path $root '大卡猫.exe'))
