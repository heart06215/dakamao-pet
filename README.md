# 大卡猫 · 桌面宠物

一只住在 Windows 桌面底部的猫。透明置顶窗口、可拖拽、摸头与摸身体互动、桌面散步、睡觉与翻身，全部由逐帧动画驱动。

宿主为 .NET 8 WPF，动画引擎使用 [VPet-Simulator.Core](https://github.com/LorisYounger/VPet) 1.1.0.66（Apache-2.0）。

![预览](picture/Screenshot%202026-09-29%20103116.jpg)

## 功能

- **拖拽与落地**：抓头顶图标拖动，松手后落到当前显示器工作区底部；提起时随鼠标反向晃动，越快幅度越大，停止后平滑回正。
- **触摸互动**：上半部分触发摸头，下半部分触发摸身体；点击位置出现白色手影。摸头带耳朵弹动与闭眼，摸身体为放松表情。
- **圆环菜单**：右键打开紧凑环形菜单，包含散步、摸头、摸身体、哈欠、睡觉、眨眼、大小、设定、声明与退出。
- **散步**：带着窗口沿桌面底部移动，同方向继续行走，接近边界才转身；菜单打开时停止位移。
- **睡觉**：可在蜷卧与四脚朝天之间切换，切换过程有完整翻身动画；睡觉时摸头会抬头回应后回到睡姿。
- **大小与置顶**：滑块连续缩放，另有 60% / 100% / 160% / 200% / 300% 预设；基准窗口 320×320。可开启强制置顶，置顶时可让桌宠对鼠标完全透明，图标下方出现独立解锁按钮。
- **独立序列播放器**：基于 `CompositionTarget.Rendering`，后台解码为冻结的 Pbgra32 像素，带异步预读与有界帧缓存。

## 目录结构

| 路径 | 用途 |
| --- | --- |
| `DakamaoPet/PetWindow.xaml.cs` | 加载、播放、抚摸、拖拽、下落、睡觉及动作队列 |
| `DakamaoPet/PetWindow.Size.cs` | 缩放、档位、持久化及面板定位 |
| `DakamaoPet/PetWindow.Walking.cs` | 散步位移、方向选择、转身及散步眨眼 |
| `DakamaoPet/PetWindow.FluidPlayback.cs` | 独立序列播放、异步解码及有界帧缓存 |
| `DakamaoPet/PetWindow.Settings.cs` | 置顶、原生点击穿透、解锁按钮、设定与声明页面 |
| `DakamaoPet/PetWindow.xaml` | 透明窗口、拖拽图标、圆环菜单、大小面板、手影 |
| `DakamaoPet/PetMod/pet/dakamao/info.lps` | 动画注册及阶段映射 |
| `DakamaoPet/PetMod/fluid/manifest.json` | 55 段统一渲染序列的路径、帧间隔与时长 |
| `tools/animation_timing.json` | 默认及逐帧播放时长，嵌入宿主并用于 MP4 导出 |
| `tools/qa` | 校验报告（JSON）与检查产物 |
| `picture`、`example` | 造型与动画的视觉参考 |

更完整的实现说明、动作衔接约束与逐轮修改记录见 [项目开发文档.md](项目开发文档.md)。

## 下载与运行

从 [Releases](https://github.com/heart06215/dakamao-pet/releases) 下载 `大卡猫.exe`，双击即可运行。这是单文件自包含的便携版，运行时与动画素材都打包在内部，不需要安装 .NET。

## 构建

需要 .NET 8 SDK：

```powershell
dotnet build DakamaoPet/DakamaoPet.csproj -c Release
dotnet run --project DakamaoPet/DakamaoPet.csproj -c Release
```

打包便携版（输出到 `release/`，并复制一份到项目根目录）：

```powershell
powershell -ExecutionPolicy Bypass -File tools/publish.ps1
```

## 动画素材

本仓库包含**完整的动画帧与源素材**（`DakamaoPet/PetMod` 的 5498 个文件、`tools` 下的关键帧与序列源，合计约 1.3 GB），克隆后无需额外下载即可直接构建运行；仓库体积较大，克隆需要一点时间。

如需从关键帧重新生成播放帧，流程如下（Python 依赖见 `tools/animation_requirements.txt`，使用 `.venv-animation` 环境）：

```powershell
.\.venv-animation\Scripts\python.exe tools/head_palette.py
.\.venv-animation\Scripts\python.exe tools/build_fluid_frames.py
.\.venv-animation\Scripts\python.exe tools/build_smooth_playback.py
.\.venv-animation\Scripts\python.exe tools/validate_picture_style.py
.\.venv-animation\Scripts\python.exe tools/validate_smooth_playback.py
.\.venv-animation\Scripts\python.exe tools/export_animation_previews.py
```

先完成帧构建再编译发布，避免复制到一半的素材。逐帧 `frame_ms` 数组长度必须匹配动画帧数，宿主与 MP4 使用同一份时长配置。

## 许可与声明

- 本项目为**公益项目**，不应以任何形式付款购买。
- 项目形象是基于《鸣潮》二创形象「大卡猫」的**再次创作**。
- 本项目有权许可的新增代码及其他原创贡献采用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)：保留署名、注明修改、非商业性使用、改编贡献以相同许可分享。源码中的 SPDX 标记按此范围解释，不得视为对整个角色形象或依赖库的重新授权。
- **尚未确认**上游大卡猫形象作者采用 CC 协议，也未确认上游角色素材可按 CC 再许可。因此本项目不宣称获得《鸣潮》、上游大卡猫形象及其他第三方内容的 CC 权利；参考图片与基于参考的角色派生素材不因新增源码标记而获得独立授权。
- `VPet-Simulator.Core` 等第三方组件保留各自原许可。

## 致谢

- 动画引擎：[VPet-Simulator](https://github.com/LorisYounger/VPet)
- 形象原作：《鸣潮》二创形象「大卡猫」及其作者
