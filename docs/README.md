# EraBridge 文档

**简体中文** · [English](README.en.md)

EraBridge 0.12.2 的使用、实现与发布说明。首次使用先读[桌面工作台](CONVERTER_WORKBENCH.md)，参与开发先读[构建说明](BUILDING.md)和[架构说明](ARCHITECTURE.md)。中文与英文分篇维护，下表可直接切换。

| 中文 | English | 内容 |
|---|---|---|
| [桌面工作台](CONVERTER_WORKBENCH.md) | [Desktop workbench](CONVERTER_WORKBENCH.en.md) | 导入、地图编辑、风险估算、撤销、导出与默认路径 |
| [多语言支持](LOCALIZATION.md) | [Language support](LOCALIZATION.en.md) | 界面与游戏输出语言、翻译资源和覆盖范围 |
| [问题与存档提交](SUPPORT.md) | [Issues and save submission](SUPPORT.en.md) | 反馈材料、日志位置、大存档分享与隐私 |
| [构建说明](BUILDING.md) | [Building](BUILDING.en.md) | 工具链、依赖、测试命令和打包输入 |
| [开发架构](ARCHITECTURE.md) | [Architecture](ARCHITECTURE.en.md) | 模块职责、转换流程与数据边界 |
| [转换规则总览](CONVERSION_RULES.md) | [Conversion rules](CONVERSION_RULES.en.md) | 人口、地理、政治、经济与战争规则 |
| [文化与宗教](CONVERTER_IDENTITY_SETTINGS.md) | [Culture and religion](CONVERTER_IDENTITY_SETTINGS.en.md) | 身份映射、本土、显示资源与更新 |
| [源核心与释放](CONVERTER_SOURCE_CORES.md) | [Source cores and releases](CONVERTER_SOURCE_CORES.en.md) | 地块支持率、整州宣称及释放边界 |
| [旗帜规则](FLAG_GENERATION_RULES.md) | [Flag rules](FLAG_GENERATION_RULES.en.md) | 源旗恢复、备用旗生成与渲染限制 |
| [验证记录](PUBLICATION.md) | [Validation record](PUBLICATION.en.md) | 各版已运行检查和未覆盖范围 |
| [许可说明](LICENSING.md) | [Licensing](LICENSING.en.md) | 上游、第三方组件与素材分发条件 |
| [独立验收](ACCEPTANCE.md) | [Independent acceptance](ACCEPTANCE.en.md) | 完整性、启动、双语导出和游戏内检查 |
| [Release 准备](RELEASING.md) | [Release preparation](RELEASING.en.md) | 候选包生成、验收、文档维护和上传 |
| [beta.3 发行说明](releases/v0.12.2-beta.3.md) | [beta.3 release notes](releases/v0.12.2-beta.3.en.md) | 中英文工作台与发布后复核 |
| [beta.2 发行说明](releases/v0.12.2-beta.2.md) | [beta.2 release notes](releases/v0.12.2-beta.2.en.md) | 首个 Windows 便携社区测试版 |
| [beta.1 发行说明](releases/v0.12.2-beta.1.md) | [beta.1 release notes](releases/v0.12.2-beta.1.en.md) | 历史源码预览版 |
| [C++ 命名约定](../EU5ToVic3/NamingConvention.zh-CN.txt) | [C++ naming conventions](../EU5ToVic3/NamingConvention.txt) | 五类组件职责与调用关系 |
| [工坊发布指南](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/blob/master/EU5ToVic3/Resources/workshop/PUBLISHING.zh-CN.txt) | [Workshop publishing](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/blob/master/EU5ToVic3/Resources/workshop/PUBLISHING.txt) | 发布目录、元数据和分语言介绍 |
| [工坊介绍](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/blob/master/EU5ToVic3/Resources/workshop/erabridge_workshop_description.zh-CN.txt) | [Workshop description](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/blob/master/EU5ToVic3/Resources/workshop/erabridge_workshop_description.en.txt) | 可用于对应语言工坊页面的完整介绍 |
| [第三方许可目录说明](../licenses/README.md) | [Third-party license directory](../licenses/README.en.md) | 原许可位置、来源与适用范围 |
| [运行组件通知](../licenses/THIRD_PARTY_NOTICES.md) | [Runtime notices](../licenses/THIRD_PARTY_NOTICES.en.md) | 组件署名和许可解释 |

首次启动的[第三方组件条款](../licenses/END_USER_TERMS.txt)在同一文件中先列完整中文、后列完整英文。原始第三方许可证、上游贡献政策与历史参考材料保留原文；项目的双语解释不替代它们。

`master` 文档会继续更新，固定发布标签和既有 ZIP 保留当时的快照。历史发行说明中的测试与限制对应其版本，后续复核另列日期。开发对话、个人安装记录、阶段待办及原始测试数据保留在本地，不作为发布文档。

文档按 [Humanizer-zh](https://github.com/op7418/Humanizer-zh) 的原则维护：直接说明技术事实，删去重复和空泛评价，保留命令、数值、限定条件和出处。静态检查、游戏内验证和长期运行不能互相替代。
