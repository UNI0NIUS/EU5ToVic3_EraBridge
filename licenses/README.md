# 第三方许可原文

`rakaly-0.12.7/LICENSE.txt` 保存 [librakaly v0.12.7 的许可原文](https://github.com/rakaly/librakaly/blob/v0.12.7/LICENSE.txt)，按下载内容原样保留。文件 SHA-256 为 `91276db973f25602d1aa43491f59cbc84cb88e6f151e1d0cc82a755563ce0195`。

候选包中的 Rakaly DLL 只有与 `tools/toolchain-lock.json` 所记录的 0.12.7 文件摘要一致时，才附上这份版本许可。`dependencies/inventory.json` 收录其 Cargo.lock 中 101 个依赖包的来源、归档摘要与通知文本摘要，包含构建和可选依赖，不代表全部静态链接。`review_required` 标记缺少单独许可声明或通知的项目。

其中 pdx-tools 的 `eu5save`、`vic3save`、`bumpalo-serde` 与派生宏来自 AGPL 仓库，保留对应根许可。外层 MIT 不能单独证明整个 DLL 的分发条件已满足，具体问题见[许可说明](../docs/LICENSING.md)。此目录不是完整对应源码，也不是二进制分发授权结论。

Python 运行库的许可由准备脚本从匹配的包缓存和运行环境中收集，不将本机缓存目录提交到仓库。详细流程见[Release 准备](../docs/RELEASING.md)。
