# Release 准备与验收

**简体中文** · [English](RELEASING.en.md)

当前便携版为 `v0.12.2-beta.3`，面向社区测试，保留 GitHub **Pre-release** 标记。`beta.1` 是此前的源码预览版，标签和附件不覆盖。

仓库保存源码、配置、测试与文档；ZIP 作为 Release 附件上传。游戏、存档、完整模组、开发对话和本机记录均不进入公开材料。

## 准备便携包

先按[构建说明](BUILDING.md)重建 C++ 导入器和桌面启动器。发行环境需要已许可的 Visual Studio Community 2022；当前脚本从 `.tools/VisualStudio2022/VC/Redist/MSVC/` 取得 x64 正式运行库，放入 Python 目录及独立导入器目录。其他依赖按包缓存或 wheel RECORD 的文件摘要核对来源。

以下示例用于在新工作区复现 beta.3 的打包布局；后续公开修订须使用新版本：

```powershell
./tools/Build-ConverterApp.ps1 -Output build/EraBridge-beta3
python -X utf8 tools/prepare_release.py --app build/EraBridge-beta3 --out build/release-preparation/v0.12.2-beta.3 --public-preview
```

输出必须是 `build/` 下尚不存在的新目录，与输入目录分开。`--python-base` 可指定打包所用 Python 安装根目录；`--no-archive` 只生成目录与报告。省略 `--public-preview` 会生成带 `INTERNAL` 的内部候选，不能通过改名替代发行检查。

| 产物 | 用途 |
|---|---|
| `EraBridge-0.12.2-beta.3-windows-x64/` | 独立便携目录，含运行环境、配方、文档与许可 |
| 同名 `.zip`、`SHA256SUMS.txt` | Release 下载附件及其摘要 |
| `release-readiness.json` | 本地准备报告，记录来源提交、工作区状态和未完成验证 |
| 包内 `build_manifest.json` | 每个打包文件的 SHA-256，不含清单自身 |
| 包内 `licenses/runtime-inventory.json` | 运行组件来源与许可位置 |

准备脚本只生成材料，不上传、创建标签或批准发行，`ready_for_publication` 保持 `false`。完整性与运行验收另存报告；依赖来源匹配本身也不等于许可审查完成。分发依据见[许可说明](LICENSING.md)。

## 发布检查

1. 从准备发布的源码提交重建。核对二进制、规则与测试报告对应同一候选；无关本地文件不纳入提交。
2. 检查文件清单与 ZIP，排除个人路径、密钥、存档、完整规则、日志和开发缓存。默认游戏与候选路径应为空。
3. 将 ZIP 解压至带中文和空格的新目录，运行独立验收工具。开发机移目录检查不能标成干净机器验收；具体命令见[独立验收](ACCEPTANCE.md)。
4. 在[发行说明](releases/v0.12.2-beta.3.md)列出已验证范围、资源容量和脚本报错，以及独立机器和长期运行尚未覆盖的事实。
5. 创建对应提交的新标签和 Release 草稿，上传 ZIP 与校验文件，核对服务器附件摘要和大小，再公开为预发布版。未来修订使用新版本，不覆盖已经下载的附件。

## 社区测试范围

首次初始化、完整转换、地图编辑、保存重开、导出和游戏内加载均欢迎反馈。资源建筑容量和部分原版脚本错误是已披露问题，独立 Windows 与长期战役仍待测试；它们不被描述为已通过，也不阻止本次社区预览发布。

GitHub 自动附带的 Source code ZIP/TAR 是源码快照，不包含便携运行环境和完整子模块，不能当作安装包。


## 文档维护

中文原文件与 `.en.md` 英文版同步维护，并保留互相跳转的语言链接。`tools/prepare_release.py` 的 `PUBLIC_DOCUMENTS` 明确列出随包文档，新增指南时同时加入两种语言。工坊说明也有独立中英文文件，见[工坊发布指南](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/blob/master/EU5ToVic3/Resources/workshop/PUBLISHING.zh-CN.txt)。

`master` 的文档更新不改变已发布 ZIP 或标签快照。新下载包必须采用新版本。
