# 来源与再发布许可

核查日期：2026-10-03。本次核查针对 v0.12.2-beta.2 源码和 Windows x64 便携包。

## 上游代码

本项目源自 [ParadoxGameConverters/EU5ToVic3](https://github.com/ParadoxGameConverters/EU5ToVic3)，本地基线为 `56ee636b6ebd8a110b54d3133794f964af0f0e1e`。本地与上游默认分支的 [LICENSE](https://github.com/ParadoxGameConverters/EU5ToVic3/blob/master/LICENSE) 均为 MIT，原版权声明为 `Copyright (c) 2021 Paradox Game Converters`。

[MIT 许可证](https://opensource.org/license/mit) 允许使用、复制、修改、合并、发布、分发、再许可及销售软件副本，条件是保留版权和许可声明。仓库根目录的 `LICENSE` 保持原文；本 fork 的代码修改沿用 MIT。

上游另有 [贡献政策](https://github.com/ParadoxGameConverters/EU5ToVic3/blob/master/.NO_AI/README.md)，明确不接受生成式 AI 代码、文档、PR 或 issue。本 fork 使用 AI 辅助开发，是独立维护的修改版。本次不会向上游提交 PR 或 issue，也不声称得到上游背书。保留的 `.NO_AI/README.md` 是上游政策记录，不能据此把本 fork 描述成未经 AI 辅助的项目。

## 子模块与依赖

`commonItems`、`Fronter` 按 `.gitmodules` 的地址和 Git 固定提交引用。各组件及其内嵌依赖的版权、许可证仍适用；根目录的 MIT 不替代它们。

便携包包含 Python、NumPy、Pillow、Tcl/Tk、Rakaly 和运行依赖。实际版本、文件摘要和来源列于包内 `licenses/runtime-inventory.json`；原许可和必要署名随包保留。源码仓库不提交这些运行环境的二进制文件。

### Rakaly

本版使用 librakaly 0.12.7，文件摘要与工具链锁文件核对。维护者已确认取得本版所用 Rakaly 的再分发许可；本项目不另行推定该许可适用于其他版本或其他发布者。[许可目录](../licenses/README.md)保留包装层 MIT 和锁定依赖的通知。部分解析依赖来自 AGPL 仓库，外层 MIT 不替代它们；附带通知不是完整对应源码，也不向下游另授超出原许可的权利。

### 微软组件

发行构建使用已按个人开发者条款许可的 Visual Studio Community 2022。C++ 导入器和启动器均由该工具链重建。Visual C++ DLL 从安装目录的 `VC/Redist/MSVC/<version>/x64` 取得，保持原文件，排除 `debug_nonredist`；这些目录列于[微软可分发清单](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution)。UCRT 文件按实际来源匹配 Windows SDK 组件，保留其原许可。

[Community 条款](https://visualstudio.microsoft.com/license-terms/vs2022-ga-community/)和[微软分发说明](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)约束微软组件。许可文本、终端用户条款和必要通知随包提供；首次启动要求使用者阅读并接受第三方组件条款。微软组件不改用本项目的 MIT，也不因本次发行而向接收者授予不受限制的再分发权。

FreeType、JPEG 等补充署名见[运行组件通知](../licenses/THIRD_PARTY_NOTICES.md)。依赖来源核对与运行验收分别记录，不能用运行成功代替许可核查。

## 游戏、模组与图标

Europa Universalis V、Victoria 3 及其商标、游戏脚本、美术和其他资源属于相应权利人。转换器代码的 MIT 许可不授权再分发这些内容。公开材料排除 `.local/`、`outputs/`、存档、完整候选模组及提取素材。`build/` 不提交到源码仓库，仅将核对后的便携 ZIP 上传为 Release 附件。

部分工具会在使用者本机读取游戏和创意工坊内容，再生成转换结果。这些结果的发布需要按其实际包含的材料另行判断。本次没有取得创意工坊整包再分发许可，源码发布不包含这些整包。

`tools/converter_ui/icons/erabridge-beta*` 是本分支的 EraBridge 应用图标，由维护者提供用于此次发布；不将其描述为 Paradox 或上游团队的官方标识。图标的提供不改变游戏素材和商标的权利归属。

## 文档编辑

README 与本次发布文档按 [Humanizer-zh](https://github.com/op7418/Humanizer-zh) 的编辑原则整理：删去重复和空泛表达，保留事实、限定条件与完成状态。其规范作为编辑参考使用，未复制到发行内容中。历史验证记录与本次重新运行的检查分别标明。
