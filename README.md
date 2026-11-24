# 大卡猫 · 桌面宠物

一只住在 Windows 桌面底部的猫。透明置顶窗口、可拖拽、摸头与摸身体互动、桌面散步、睡觉与翻身，全部由逐帧动画驱动。

宿主为 .NET 8 WPF，动画引擎使用 [VPet-Simulator.Core](https://github.com/LorisYounger/VPet) 1.1.0.66（Apache-2.0）。

![预览](picture/Screenshot%202026-09-29%20103116.jpg)

## 功能

- **拖拽与落地**：抓头顶图标拖动，松手后落到当前显示器工作区底部；提起时随鼠标反向晃动，越快幅度越大，停止后平滑回正。
- **触摸互动**：上半部分触发摸头，下半部分触发摸身体；点击位置出现白色手影。摸头带耳朵弹动与闭眼，摸身体为放松表情。
- **圆环菜单**：右键打开紧凑环形菜单，包含散步、摸头、摸身体、哈欠、睡觉、眨眼、大小、设定、声明、回到主屏与退出。
- **散步**：带着窗口沿桌面底部移动，同方向继续行走，接近边界才转身；菜单打开时停止位移。
- **睡觉**：可在蜷卧与四脚朝天之间切换，切换过程有完整翻身动画；睡觉时摸头会抬头回应后回到睡姿。
- **大小与置顶**：滑块连续缩放，另有 60% / 100% / 160% / 200% / 300% 预设；基准窗口 320×320。可开启强制置顶，置顶时可让桌宠对鼠标完全透明，图标下方出现独立解锁按钮。
- **位置记忆与托盘**：记住上次位置，显示器拔插后会夹紧到最近的可用工作区；`%LOCALAPPDATA%\DakamaoPet\position.json`。托盘图标提供“显示 / 回到主屏”、置顶开关、设定、声明与退出。
- **独立序列播放器**：基于 `CompositionTarget.Rendering`，后台解码为冻结的 Pbgra32 像素，带异步预读、有界帧缓存，以及跨循环复用的已解码帧缓存。

## 目录结构

| 路径 | 用途 |
| --- | --- |
| `DakamaoPet/PetWindow.xaml.cs` | 加载、播放、抚摸、拖拽、下落、睡觉及动作队列 |
| `DakamaoPet/PetWindow.Size.cs` | 缩放、档位、防抖持久化及面板定位 |
| `DakamaoPet/PetWindow.Walking.cs` | 散步位移、方向选择、转身及散步眨眼 |
| `DakamaoPet/PetWindow.FluidPlayback.cs` | 独立序列播放、异步解码、有界缓存及跨循环复用 |
| `DakamaoPet/PetWindow.Settings.cs` | 置顶、原生点击穿透、解锁按钮、设定与声明页面 |
| `DakamaoPet/PetWindow.Position.cs` | 位置持久化、多显示器夹紧与回到主屏 |
| `DakamaoPet/PetWindow.Tray.cs` | 托盘图标与快捷菜单 |
| `DakamaoPet/AssetStore.cs` | 发布素材还原（硬链接优先）及素材哈希缓存 |
| `DakamaoPet/PetWindow.xaml` | 透明窗口、拖拽图标、圆环菜单、大小面板、手影 |
| `DakamaoPet/PetMod/pet/dakamao/info.lps` | 动画注册及阶段映射 |
| `DakamaoPet/PetMod/fluid/manifest.json` | 55 段统一渲染序列的路径、帧间隔与时长 |
| `tools/animation_timing.json` | 默认及逐帧播放时长，嵌入宿主并用于 MP4 导出 |
| `tools/build_dedup_assets.py` | 发布前去重：唯一内容 + `layout.json` |
| `tools/publish.ps1` | 一键校验、去重、单文件发布、SHA256 报告与标签 |
| `tools/qa` | 校验报告（JSON）与检查产物 |
| `LICENSE`、`THIRD-PARTY-NOTICES.md` | 项目许可与第三方/形象授权声明 |

更完整的实现说明、动作衔接约束与逐轮修改记录见 [项目开发文档.md](项目开发文档.md)。

## 下载与运行

从 [Releases v0.3.0](https://github.com/heart06215/dakamao-pet/releases/tag/v0.3.0) 下载 [`DakamaoPet-0.3.0-win-x64.exe`](https://github.com/heart06215/dakamao-pet/releases/download/v0.3.0/DakamaoPet-0.3.0-win-x64.exe)（即 `大卡猫.exe`，549 MB），双击即可运行。单文件自包含：.NET 8 运行时与全部动画素材都打包在 exe 内部，不需要安装任何环境。

SHA256：`B818CC085BD8ED43BA370E26B75D0032284185F5082FDDAF02ADE33728806A00`

首次启动会把去重素材还原到 `%LOCALAPPDATA%\DakamaoPet\assets\<版本>`（唯一内容约 504 MB，同一磁盘上使用硬链接，不额外占用等量空间）；之后启动直接复用。

## 构建

需要 .NET 8 SDK：

```powershell
dotnet build DakamaoPet/DakamaoPet.csproj -c Release
dotnet run --project DakamaoPet/DakamaoPet.csproj -c Release
```

一键发布（校验可选，自动生成去重素材、单文件 exe、SHA256 报告与发布说明）：

```powershell
powershell -ExecutionPolicy Bypass -File tools/publish.ps1 -Validate -Tag
```

发布脚本会：

1. 检查程序未在运行，读取 `csproj` 版本号；
2. 可选执行 `validate_picture_style.py` 与 `validate_smooth_playback.py`；
3. 运行 `build_dedup_assets.py`，按内容去重（5498 个文件 → 3026 个唯一 blob，约节省 45%）；
4. 以 `DedupAssetsPath` 单文件发布，写入 `release/DakamaoPet-<版本>-win-x64.exe` 与根目录 `大卡猫.exe`；
5. 计算 SHA256，写入 `tools/qa/publish-<版本>.json` 和 `release/RELEASE-<版本>.md`，并打印 README 片段。

## 动画素材

本仓库包含**完整的动画帧与源素材**（`DakamaoPet/PetMod` 的 5498 个文件、`tools` 下的关键帧与序列源，合计约 1.3 GB），克隆后无需额外下载即可直接构建运行。

发布包不会重复打包相同帧：`tools/build_dedup_assets.py` 把 923 MB 的 PetMod 压成 504 MB 唯一内容，exe 由约 954 MB 降到 549 MB；帧像素与 QA 校验结果保持不变。

如需从关键帧重新生成播放帧（Python 依赖见 `tools/animation_requirements.txt`，`tools/setup_env.ps1` 会创建 `.venv-animation` 并安装依赖）：

```powershell
.\.venv-animation\Scripts\python.exe tools/head_palette.py
.\.venv-animation\Scripts\python.exe tools/build_fluid_frames.py
.\.venv-animation\Scripts\python.exe tools/build_smooth_playback.py
.\.venv-animation\Scripts\python.exe tools/validate_picture_style.py
.\.venv-animation\Scripts\python.exe tools/validate_smooth_playback.py
.\.venv-animation\Scripts\python.exe tools/export_animation_previews.py
```

先完成帧构建再编译发布，避免复制到一半的素材。逐帧 `frame_ms` 数组长度必须匹配动画帧数，宿主与 MP4 使用同一份时长配置。

GitHub Actions 会在 Windows 上编译宿主与检查程序、校验素材，并验证去重布局可用。

## 许可与声明

- 本项目为**公益项目**，不应以任何形式付款购买。
- 项目形象是基于《鸣潮》二创形象「大卡猫」的**再次创作**。
- 上游「大卡猫」形象作者：B 站空间 <https://space.bilibili.com/350988058>。**已获得作者授权**使用并可再创作该形象（由项目维护者确认）。
- 本项目有权许可的新增代码及其他原创贡献采用 [CC BY-NC-SA 4.0](LICENSE)：保留署名、注明修改、非商业性使用、改编贡献以相同许可分享。源码中的 SPDX 标记按此范围解释，不得视为对整个角色形象或依赖库的重新授权。
- 上游作者的授权不包含《鸣潮》及其角色、商标、素材等权利；本项目不宣称获得《鸣潮》权利人的授权，参考图片与基于参考的角色派生素材不因新增源码标记而获得独立授权。
- `VPet-Simulator.Core`、`LinePutScript`、`Panuon.WPF`、`SkiaSharp` 等第三方组件保留各自原许可，详见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

## 致谢

- 动画引擎：[VPet-Simulator](https://github.com/LorisYounger/VPet)
- 形象原作：《鸣潮》二创形象「大卡猫」及其作者
