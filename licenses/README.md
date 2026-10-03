# 第三方许可原文

`rakaly-0.12.7/LICENSE.txt` 保存 [librakaly v0.12.7 的许可原文](https://github.com/rakaly/librakaly/blob/v0.12.7/LICENSE.txt)，按下载内容原样保留。文件 SHA-256 为 `91276db973f25602d1aa43491f59cbc84cb88e6f151e1d0cc82a755563ce0195`。

候选包中的 Rakaly DLL 只有与 `tools/toolchain-lock.json` 所记录的 0.12.7 文件摘要一致时，才附上这份版本许可。`dependencies/inventory.json` 收录其 Cargo.lock 中 101 个依赖包的来源、归档摘要与通知文本摘要，包含构建和可选依赖，不代表全部静态链接。`review_required` 标记缺少单独许可声明或通知的项目。

其中 pdx-tools 的 `eu5save`、`vic3save`、`bumpalo-serde` 与派生宏来自 AGPL 仓库，保留对应根许可。维护者已确认取得本版 Rakaly 再分发许可；外层 MIT 不替代依赖许可，适用范围见[许可说明](../docs/LICENSING.md)。此目录不是完整对应源码，不向下游另授许可。

Python 运行库的许可由准备脚本从匹配的包缓存和运行环境中收集，不将本机缓存目录提交到仓库。详细流程见[Release 准备](../docs/RELEASING.md)。

运行组件的补充署名及所选许可分支见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

`microsoft-community-2022/LICENSE.docx` 是微软提供的 Community 2022 许可原文，`LICENSE.txt` 为便于阅读的文本提取版，原文优先。Windows 包另保留 UCRT 的 SDK 许可。首次启动的第三方组件条款见 [END_USER_TERMS.txt](END_USER_TERMS.txt)。
