# 第三方组件与形象授权说明

本文件记录《大卡猫》桌面宠物项目使用的第三方组件、角色形象来源与授权范围。
项目自身新增代码及其他原创贡献采用 [CC BY-NC-SA 4.0](LICENSE)；该许可不覆盖下列第三方内容。

## 角色形象与上游授权

- 本项目形象是基于《鸣潮》二创形象「大卡猫」的**再次创作**，与《鸣潮》官方无关。
- 上游「大卡猫」形象作者：B 站空间 <https://space.bilibili.com/350988058>。
- 授权状态：**已获得上游形象作者授权**，同意本项目使用并再创作该形象（由项目维护者确认并记录于 2026-11-24）。
- 该授权来自上游形象作者，不包含《鸣潮》及其角色、商标、素材等由原权利人享有的权利。本项目不宣称获得《鸣潮》权利人的授权或再许可。
- 上游作者的授权不自动等同于 CC 再许可：本项目对角色派生素材的分发以作者授权范围为限，新增源码的 CC BY-NC-SA 4.0 标记不得解释为对整个角色形象的重新授权。

## 第三方软件组件

| 组件 | 版本 | 许可 | 项目地址 |
| --- | --- | --- | --- |
| VPet-Simulator.Core | 1.1.0.66 | Apache-2.0 | <https://github.com/LorisYounger/VPet> |
| LinePutScript | 1.11.9 | Apache-2.0 | <https://github.com/LorisYounger/LinePutScript> |
| LinePutScript.Localization.WPF | 1.0.7 | Apache-2.0 | <https://github.com/LorisYounger/LinePutScript.Localization.WPF> |
| Panuon.WPF | 1.1.3 | Apache-2.0 | <https://github.com/Panuon/Panuon.WPF> |
| Panuon.WPF.UI | 1.2.4.10 | Apache-2.0 | <https://github.com/Panuon/Panuon.WPF.UI> |
| SkiaSharp（含 Win32 原生资产） | 3.116.1 | MIT | <https://github.com/mono/SkiaSharp> |
| .NET 8 / WPF 运行时 | 8.0 | MIT | <https://github.com/dotnet/runtime> |

许可全文：

- Apache-2.0：<https://www.apache.org/licenses/LICENSE-2.0>
- MIT：<https://opensource.org/license/mit>

`VPet-Simulator.Core` 及其依赖保留各自原许可；本项目的 CC BY-NC-SA 4.0 不改变这些组件的许可条款。
发布二进制中的 .NET 运行时受 Microsoft 的可再分发条款约束。

## 生成素材说明

动画帧与关键帧由项目维护者使用内置图像生成流程制作，提示词、参考图与生成记录保存在 `tools/sequence_sources`、`tools/keyframes` 与对应的 `generation*.json` 中。
这些素材的权利与授权范围以上文「角色形象与上游授权」一节为准。
