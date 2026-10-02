# 来源与再发布许可

核查日期：2026-10-03。本次核查针对源码发布；现有本地 ZIP 和转换结果不在发布范围内。

## 上游代码

本项目源自 [ParadoxGameConverters/EU5ToVic3](https://github.com/ParadoxGameConverters/EU5ToVic3)，本地基线为 `56ee636b6ebd8a110b54d3133794f964af0f0e1e`。本地与上游默认分支的 [LICENSE](https://github.com/ParadoxGameConverters/EU5ToVic3/blob/master/LICENSE) 均为 MIT，原版权声明为 `Copyright (c) 2021 Paradox Game Converters`。

[MIT 许可证](https://opensource.org/license/mit) 允许使用、复制、修改、合并、发布、分发、再许可及销售软件副本，条件是保留版权和许可声明。仓库根目录的 `LICENSE` 保持原文；本 fork 的代码修改沿用 MIT。

上游另有 [贡献政策](https://github.com/ParadoxGameConverters/EU5ToVic3/blob/master/.NO_AI/README.md)，明确不接受生成式 AI 代码、文档、PR 或 issue。本 fork 使用 AI 辅助开发，是独立维护的修改版。本次不会向上游提交 PR 或 issue，也不声称得到上游背书。保留的 `.NO_AI/README.md` 是上游政策记录，不能据此把本 fork 描述成未经 AI 辅助的项目。

## 子模块与依赖

`commonItems`、`Fronter` 按 `.gitmodules` 的地址和 Git 固定提交引用。各组件及其内嵌依赖的版权、许可证仍适用；根目录的 MIT 不替代它们。

公开源码不新增分发 Python、NumPy、Pillow、Tk、MSVC、Windows SDK 或下载的 Rakaly 二进制。上游历史中已有的第三方文件保持其原来源。后续若发布可执行包，需按实际打包清单收集许可证和通知文件，并核查各 DLL 的分发条件；不能仅凭构建成功判断可公开分发。

## 游戏、模组与图标

Europa Universalis V、Victoria 3 及其商标、游戏脚本、美术和其他资源属于相应权利人。转换器代码的 MIT 许可不授权再分发这些内容。本次排除 `.local/`、`build/`、`outputs/`、存档、完整候选模组及提取素材。

部分工具会在使用者本机读取游戏和创意工坊内容，再生成转换结果。这些结果的发布需要按其实际包含的材料另行判断。本次没有取得创意工坊整包再分发许可，源码发布不包含这些整包。

`tools/converter_ui/icons/erabridge-beta*` 是本分支的 EraBridge 应用图标，由维护者提供用于此次发布；不将其描述为 Paradox 或上游团队的官方标识。图标的提供不改变游戏素材和商标的权利归属。

## 文档编辑

README 与本次发布文档按 [Humanizer-zh](https://github.com/op7418/Humanizer-zh) 的编辑原则整理：删去重复和空泛表达，保留事实、限定条件与完成状态。其规范作为编辑参考使用，未复制到发行内容中。历史验证记录与本次重新运行的检查分别标明。
