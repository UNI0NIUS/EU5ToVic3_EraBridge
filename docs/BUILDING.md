# 构建 EraBridge

**简体中文** · [English](BUILDING.en.md)

[文档索引](README.md) · [发布准备](RELEASING.md)

当前维护的构建环境为 Windows x64。原仓库保留 Linux 构建文件，但本分支桌面版尚未完成 Linux 验证。

## 获取源码

克隆本 fork 后，在仓库根目录初始化子模块：

```powershell
git submodule update --init --recursive
```

`commonItems` 与 `Fronter` 使用上游固定的子模块提交，不应把本机子模块目录复制为普通源码目录。

## C++ 导入器与测试

准备 Python 3.11 或更新版本、CMake、Ninja 和 librakaly 0.12.7。Windows 发行构建使用 Visual Studio Community 2022 的 C++ 桌面开发工具与 Windows SDK；使用者应先确认适用资格并接受产品条款。`Setup-PersonalEnvironment.ps1` 可下载其他本地工具，但不能替代适用的 Visual Studio 产品许可。

`Enter-DevEnvironment.ps1` 优先使用 `.tools/VisualStudio2022` 的正式安装；也可传入 `-VisualStudioPath` 初始化其他安装位置。更换编译器时使用新的 CMake 构建目录，避免旧缓存仍指向其他工具链：

```powershell
. ./tools/Enter-DevEnvironment.ps1
cmake --preset x64-release-windows -B build/community-release -DBUILD_FRONTEND=OFF -DCMAKE_MAKE_PROGRAM="$PWD/.tools/python/Scripts/ninja.exe" -DRAKALY_DIR="$PWD/.tools/rakaly-0.12.7/librakaly-0.12.7-win-msvc"
cmake --build build/community-release --target EU5ToVic3Converter EU5ToVic3Tests --parallel 8
ctest --test-dir build/community-release --output-on-failure
```

沿用同一工具链的日常构建也可运行 `tools/Build-Personal.ps1`。
构建输出位于 `build/Release-Windows/EU5ToVic3/`，测试日志位于 `.local/m0/`。`Build-Personal.ps1` 默认运行 CTest；`-ConfigureOnly` 仅配置，`-Jobs 4` 可降低并行任务数。

## Python 工具与测试

桌面运行使用 NumPy、Pillow 和 Tk；开发测试另需 SciPy。当前本机验证使用 Python 3.13.9；代码使用 `hashlib.file_digest`，最低需要 Python 3.11。在自己的虚拟环境中安装依赖，确认 Python 自带 Tk 可用：

```powershell
python -m pip install -r requirements-dev.txt
python -X utf8 -m unittest discover -s tools -p 'test_*.py'
```

部分历史测试和审计脚本读取本机游戏目录或 `.local/` 中的中间资料。缺少这些输入时不能复现相应集成验证；测试结果应说明环境和跳过项。

## 桌面打包的额外输入

`tools/Build-ConverterApp.ps1` 调用 `package_converter_app.py`，需要：

- 已构建的 C++ 导入器和 Rakaly DLL。
- 包含 NumPy、Pillow、Tk 和依赖 DLL 的 Python 环境。
- 仓库中的 `config/release_rules/` 配方及其引用的配置文件。

默认打包不读取开发机的 `.local/converter/rules/`。玩家首次运行时，通过“准备转换规则”从自己的游戏和 V3 原版 1836.1.1 基准存档生成私有资源。`initialize_converter.py` 校验配方、地图及引用字段摘要；游戏资源变化时需维护者更新配方。`freeze_release_rules.py` 用于维护配方，不是玩家首次使用的步骤。

`-IncludeLocalRules` 仅供本地调试，会带入已有完整规则，不应用于公开候选。

输入齐全时运行：

```powershell
./tools/Build-ConverterApp.ps1 -Output build/EraBridge-local
```

输出目录必须位于仓库内且尚不存在。打包器目前按本机 Python 发行版的目录布局收集依赖，其他 Python 安装可能需要调整。`-SkipRuntime` 用于刷新已有本地构建，不用于制作干净发行包。

旧构建或使用 `-IncludeLocalRules` 的 ZIP 可能包含本地默认路径和游戏资源，不应直接作为公开下载。公开二进制前需核查依赖许可证、资产来源和路径清理；开发机检查与独立机器验收分别记录。
