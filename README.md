# EraBridge — EU5 → Victoria 3

![EraBridge 图标](tools/converter_ui/icons/erabridge-beta-128.png)

EraBridge 将 Europa Universalis V 存档转换为 Victoria 3 候选模组，并提供 Windows 桌面工作台，用于查看地图、调整人口与耕地、编辑地区和导出结果。当前源码版本为 **0.12.2，开发中**，主要验证环境是 EU5 1.3.11 与 Victoria 3 1.13.11。

项目基于 [ParadoxGameConverters/EU5ToVic3](https://github.com/ParadoxGameConverters/EU5ToVic3) 独立修改，与上游团队没有官方隶属关系。上游基线为 `56ee636b6ebd8a110b54d3133794f964af0f0e1e`。本分支开发使用了 AI 辅助；上游不接受此类贡献，相关反馈请留在本 fork。

## 当前功能

- 读取 EU5 文本、压缩及二进制存档，转换人口、文化、宗教、国家、政治关系、经济、军队和开局战争。
- 在桌面地图中查看国家、州、地块、市场、食物和就业估算，预览编辑结果并撤销操作。
- 调整人口和耕地、合并相邻地区或国家、修改地块归属与州界，导出独立候选模组。
- 按源存档核心生成地块级可释放国家，整州宣称另按覆盖率判断；恢复可解析的源旗帜。

完整转换和静态检查已经覆盖部分 1337、1780、1787 存档。游戏内显示、经济平衡及长期稳定性仍需验证。食物与就业指标是静态估算，不代表游戏运行后的价格、招聘或实际失业率；任意版本和第三方模组的兼容性尚未验证。

## 使用与构建

本次公开的是源码、配置、测试、应用图标和文档。仓库不包含游戏本体、玩家存档、基准存档、游戏提取的贴图或本机生成的完整规则包，也不提供可直接运行的 Windows 发行包。

开发环境及构建步骤见 [构建说明](docs/BUILDING.md)。完整桌面打包还需要本地规则包及合法安装的游戏数据；仅克隆仓库不足以完成端到端转换。

已有本地构建时，双击 `Open-ConverterWorkbench.cmd`，或运行 `build/ConverterWorkbench/EU5Converter.exe`。导入存档时指定游戏目录和规则包，完成转换后在地图上检查，再导出模组。新模组应在 Victoria 3 中新开战役验证。

## 文档

- [桌面工作台：操作流程、编辑和导出](docs/CONVERTER_WORKBENCH.md)
- [文化、宗教与身份规则](docs/CONVERTER_IDENTITY_SETTINGS.md)
- [源核心、宣称与释放边界](docs/CONVERTER_SOURCE_CORES.md)
- [旗帜转换规则](docs/FLAG_GENERATION_RULES.md)
- [公开材料与验证记录](docs/PUBLICATION.md)
- [来源、许可与再发布范围](docs/LICENSING.md)

`config/personal/` 保留早期开发沿用的目录名称，包含转换规则、研究依据和部分旧战役配置。各文件的适用范围不同，不能把所有配置直接当作任意新存档的默认值。

## 许可

代码沿用 [MIT 许可证](LICENSE)。修改和再发布时须保留原版权与许可声明。子模块和第三方组件按各自许可证处理；MIT 不授予游戏内容、商标或创意工坊素材的再分发权。具体边界见 [许可说明](docs/LICENSING.md)。
