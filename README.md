# EraBridge — EU5 → Victoria 3

![EraBridge 图标](tools/converter_ui/icons/erabridge-beta-128.png)

EraBridge 将 Europa Universalis V 存档转换为 Victoria 3 候选模组，并提供 Windows 桌面工作台，用于查看地图、调整人口与耕地、编辑地区和导出结果。当前源码版本为 **0.12.2-beta.1，源码预览版**，主要验证环境是 EU5 1.3.11 与 Victoria 3 1.13.11。

项目基于 [ParadoxGameConverters/EU5ToVic3](https://github.com/ParadoxGameConverters/EU5ToVic3) 独立修改，与上游团队没有官方隶属关系。上游基线为 `56ee636b6ebd8a110b54d3133794f964af0f0e1e`。本分支开发使用了 AI 辅助；上游不接受此类贡献，相关反馈请留在本 fork。

## 当前功能

- 读取 EU5 文本、压缩及二进制存档，转换人口、文化、宗教、国家、政治关系、经济、军队和开局战争。
- 在桌面地图中查看国家、州、地块、市场、食物和就业估算，预览编辑结果并撤销操作。
- 调整人口和耕地、合并相邻地区或国家、修改地块归属与州界，导出独立候选模组。
- 按源存档核心生成地块级可释放国家，整州宣称另按覆盖率判断；恢复可解析的源旗帜。

完整转换和静态检查已经覆盖部分 1337、1780、1787 存档。游戏内显示、经济平衡及长期稳定性仍需验证。食物与就业指标是静态估算，不代表游戏运行后的价格、招聘或实际失业率；任意版本和第三方模组的兼容性尚未验证。

## 使用与构建

[v0.12.2-beta.1](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/releases/tag/v0.12.2-beta.1) 提供源码、配置、测试、应用图标和文档，供自行构建及社区测试。当前没有便携安装附件，GitHub 自动生成的 Source code 压缩包不能直接运行；克隆时还需初始化子模块。依赖分发许可确认后再提供 Windows 便携包。

资源建筑容量与部分原版脚本报错是本版已知问题，独立 Windows 和长期运行尚未验证。复现问题请提交到[本项目 Issues](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/issues/new?template=bug_report.md)，附版本和操作步骤；完整验证范围见[验证记录](docs/PUBLICATION.md)。

仓库不包含游戏本体、玩家存档、基准存档、游戏提取的贴图或本机生成的完整规则包。发布条件及剩余问题见[发布准备](docs/RELEASING.md)。

开发环境及构建步骤见 [构建说明](docs/BUILDING.md)。桌面包包含规则配方；首次转换时从使用者合法安装的游戏和自备基准存档生成所需资源。

已有本地构建时，双击 `Open-ConverterWorkbench.cmd`，或运行 `build/ConverterWorkbench/EU5Converter.exe`。先点击“准备转换规则”，选择两款游戏和自备的 V3 原版开局存档，再导入 EU5 存档。转换完成后在地图上检查并导出模组。新模组应在 Victoria 3 中新开战役验证。

## 文档

- [开发文档：使用说明、架构与转换规则](docs/README.md)
- [桌面工作台：操作流程、编辑和导出](docs/CONVERTER_WORKBENCH.md)
- [文化、宗教与身份规则](docs/CONVERTER_IDENTITY_SETTINGS.md)
- [源核心、宣称与释放边界](docs/CONVERTER_SOURCE_CORES.md)
- [旗帜转换规则](docs/FLAG_GENERATION_RULES.md)
- [公开材料与验证记录](docs/PUBLICATION.md)
- [Release 准备与验收流程](docs/RELEASING.md)
- [来源、许可与再发布范围](docs/LICENSING.md)

`config/personal/` 保留早期开发沿用的目录名称，包含转换规则、研究依据和部分旧战役配置。各文件的适用范围不同，不能把所有配置直接当作任意新存档的默认值。

## 许可

代码沿用 [MIT 许可证](LICENSE)。修改和再发布时须保留原版权与许可声明。子模块和第三方组件按各自许可证处理；MIT 不授予游戏内容、商标或创意工坊素材的再分发权。具体边界见 [许可说明](docs/LICENSING.md)。
