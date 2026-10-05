# 运行组件署名与许可说明

**简体中文** · [English](THIRD_PARTY_NOTICES.en.md)

EraBridge 的 Windows 便携包使用 Python、NumPy、Pillow、Tcl/Tk 及它们的运行依赖。组件版本和文件来源见包内 `licenses/runtime-inventory.json`，原版权与许可文本保留在相应目录。这里的署名不替代原许可，也不表示替代各组件的适用条款。

本软件部分功能基于 FreeType 团队的工作，使用 FreeType 字体引擎。本包采用其 FTL 许可选项，原文位于 `licenses/runtime/freetype-*/docs/FTL.TXT`。项目主页：[FreeType](https://freetype.org/)。

This software is based in part on the work of the Independent JPEG Group.

XZ 组件清单可能列出多个许可证；本包使用的 liblzma 对应 0BSD，不能把 XZ 的辅助脚本许可直接套到该库。Zstandard 使用其 BSD 许可选项。具体范围以实际二进制及原组件说明为准。

Rakaly 包装层、其解析依赖以及微软运行库分别适用各自条款。`licenses/rakaly-0.12.7/dependencies/` 收集的是锁文件依赖通知，不是完整对应源码。适用范围见[许可说明](../docs/LICENSING.md)和[发布准备](../docs/RELEASING.md)。
