# 问题反馈与存档提交

**简体中文** · [English](SUPPORT.en.md) · [文档索引](README.md)

先在[本 fork 的 Issues](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/issues/new?template=bug_report.md)提交现象、复现步骤和必要日志。初次报告不要求公开完整存档；需要复现输入时，再补充能够重现问题的最小材料。

## 报告内容

- EraBridge 版本或提交、下载来源、Windows 版本。
- EU5 与 Victoria 3 版本，源存档日期与玩家国家。
- 是否启用模组；列出模组名称、版本和加载顺序。
- 工作台语言、所选输出语言和 V3 游戏语言。
- 问题阶段：准备规则、导入、转换、地图编辑、保存项目、导出或游戏内运行。
- 操作步骤、预期和实际结果、完整错误信息；游戏内问题注明日期、国家、州或建筑。本地化问题附显示文字或脚本键。

先对照[验证范围](PUBLICATION.md)与[发行说明](releases/v0.12.2-beta.3.md)。部分二进制存档会报 `Unknown EU5 binary tokens: import refused`；原生导入失败时请保留原始 `.eu5`，不要手动修改或重新编码后将它当作原件。

## 默认路径与日志

发行版通过 `EU5Converter.exe` 启动时，下列路径均相对于软件解压目录，而非游戏安装目录：

| 材料 | 路径 |
|---|---|
| 初次完整转换结果 | `data/runs/<时间戳-ID>/complete/` |
| 工作台再次导出 | `data/exports/<时间戳-ID>/` |
| 已保存项目 | `data/projects/` |
| 转换进度与错误 | `data/runs/<时间戳-ID>/conversion.log`、`status.json` |
| 原生导入日志 | 对应任务目录中的 `log.txt` |
| 工作台错误 | `data/logs/desktop-*.log` |
| 启动失败 | `data/startup.log` |

界面“打开输出目录”可定位最近输出。导出包中的 `localization_verification.json` 记录语言检查；`package_report.json` 记录输入指纹、输出哈希和校验结果。源码启动默认使用 `.local/converter/`；指定 `--workspace` 时以该目录为准。程序不会默认导出到 Victoria 3 的 `mod` 目录，安装方式见[工作台说明](CONVERTER_WORKBENCH.md)。

仅提供相关阶段的日志或错误片段即可。日志、项目和报告可能包含用户名、私人路径及输入数据；分享副本前清理无关个人信息，保留错误上下文。不要直接上传整个 `data/`、验收目录或游戏安装。

## 提交需要复现的存档

1. 保留原件，将能复现问题的 `.eu5` 放入 ZIP，并附简短说明：软件及游戏版本、存档日期、国家、模组加载顺序和操作步骤。ZIP 中保留原存档字节；压缩不会修复或改变输入内容。
2. ZIP 不超过 25 MB 时，可拖入 Issue 正文或评论。更大时使用网盘分享下载链接，注明文件名、大小、访问方式和有效期。GitHub 支持 ZIP，普通附件上限为 25 MB；公开仓库附件可被未登录者访问。见 [GitHub 附件说明](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files)。
3. 可附原始存档或 ZIP 的 SHA-256，并明确摘要对应哪个文件，便于确认下载完整性：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'D:\Report\sample.eu5'
```

不能公开的存档不要上传至公开 Issue，也不要把带访问口令的链接视为私密渠道。先只提交问题说明，再与维护者约定可接受的私下传输方式和保留期限；目前没有专用的私密存档上传入口。分享前确认自己同意接收者查看存档内容。不要附游戏本体、完整创意工坊包、账号凭据或其他无关文件。

通常先提供 EU5 原始存档。若问题只在 V3 运行后出现，请注明启用的导出模组、发生日期和复现方式，再按需要提供 `.v3` 及相关输出；仅有 `.v3` 未必足以重现转换阶段问题。请保留原件和本地备份，维护者可能继续询问必要信息。
