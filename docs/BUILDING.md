# 构建 EraBridge

[文档索引](README.md) · [发布准备](RELEASING.md)

当前维护的构建环境为 Windows x64。原仓库保留 Linux 构建文件，但本分支桌面版尚未完成 Linux 验证。

## 获取源码

克隆本 fork 后，在仓库根目录初始化子模块：

```powershell
git submodule update --init --recursive
```

`commonItems` 与 `Fronter` 使用上游固定的子模块提交，不应把本机子模块目录复制为普通源码目录。

## C++ 导入器与测试

准备 Python 3.11 或更新版本。在 PowerShell 中运行：

```powershell
./tools/Setup-PersonalEnvironment.ps1
./tools/Build-Personal.ps1
```

环境脚本在 `.tools/` 内下载并校验工具链，建立 CMake/Ninja 环境；MSVC 和 Windows SDK 来自微软下载渠道。安装前应阅读脚本及相应组件条款，脚本包含向工具链提取器传递 `--accept-license` 的步骤。已有环境时只需执行构建脚本。

构建输出位于 `build/Release-Windows/EU5ToVic3/`，测试日志位于 `.local/m0/`。`Build-Personal.ps1` 默认运行 CTest；`-ConfigureOnly` 仅配置，`-Jobs 4` 可降低并行任务数。

## Python 工具与测试

Python 代码使用 NumPy、Pillow 和 Tk。当前本机验证使用 Python 3.13.9；代码使用 `hashlib.file_digest`，最低需要 Python 3.11。在自己的虚拟环境中安装依赖，确认 Python 自带 Tk 可用：

```powershell
python -m pip install -r requirements.txt
python -X utf8 -m unittest discover -s tools -p 'test_*.py'
```

部分历史测试和审计脚本读取本机游戏目录或 `.local/` 中的中间资料。缺少这些输入时不能复现相应集成验证；测试结果应说明环境和跳过项。

## 桌面打包的额外输入

`tools/Build-ConverterApp.ps1` 调用 `package_converter_app.py`，需要：

- 已构建的 C++ 导入器和 Rakaly DLL。
- 包含 NumPy、Pillow、Tk 和依赖 DLL 的 Python 环境。
- `.local/converter/rules/` 内带哈希清单的规则包。
- 由使用者自己提供的 Victoria 3 基准开局文本，以及匹配的本地游戏数据。

规则构建入口是 `tools/build_converter_rules.py`，参数可通过 `--help` 查看。它还依赖已验证的资产包、文化映射上下文和本地地理审核数据；这些输入不包含在公开源码中。因此，目前还没有从干净克隆一键生成完整桌面发行包的流程。

输入齐全时运行：

```powershell
./tools/Build-ConverterApp.ps1 -Output build/EraBridge-local
```

输出目录必须位于仓库内且尚不存在。打包器目前按本机 Python 发行版的目录布局收集依赖，其他 Python 安装可能需要调整。`-SkipRuntime` 用于刷新已有本地构建，不用于制作干净发行包。

现有 ZIP 可能包含本地默认路径和从游戏生成的资源，不应直接作为公开下载。公开二进制前需另行核查依赖许可证、资产来源、路径清理和干净机器运行结果。
