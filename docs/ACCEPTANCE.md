# Windows 候选包验收

`Test-PortableRelease.ps1` 使用包内 Python 检查候选，不需要另装 Python。脚本写入新建的验收目录，不修改游戏安装、源存档或已有项目，也不自动启动游戏。完整转换可能耗时较长，预留足够磁盘空间。

## 准备测试环境

优先使用未装 Python、编译器和开发缓存的 Windows x64 电脑或虚拟机。记录系统版本、候选 ZIP 的 SHA-256、游戏版本及已安装运行库。把完整候选解压到含中文和空格的路径，保留目录结构。若只能在开发机运行，应将环境说明写为开发机；清空 PATH 不能证明独立环境可用。

先用 `Get-FileHash -Algorithm SHA256` 核对 ZIP 与随附 `SHA256SUMS.txt`。包内文件清单用于发现损坏或改动，不提供数字签名身份认证。

## 启动与完整性检查

在解压目录打开 PowerShell，使用尚不存在的输出目录：

```powershell
./Test-PortableRelease.ps1 -Output 'C:/验收记录/启动检查' -Environment 'Windows 11 独立测试机；未安装开发工具'
```

另外双击 `EU5Converter.exe`，人工检查首次运行的条款窗口：选择“否”应能打开条款，选择“取消”应退出，阅读并同意后选择“是”应进入工作台。再次启动不应重复询问。下列自动检查不包含启动器条款窗口的点击流程。

脚本检查每个发行文件的摘要、额外文件、Python 搜索路径、NumPy 运算、Pillow 读写、Rakaly 加载，以及桌面窗口和规则初始化对话框的创建与关闭。脚本临时限制当前进程的 PATH 和 Python 环境变量，退出时恢复。

## 首次使用与完整转换

安装受支持版本的 EU5 和 Victoria 3。在 V3 中禁用所有模组，新开 1836 年战役，保持暂停并立即保存。基准存档须为 1.13.11、1836.1.1。检查存档中没有模组字段不能替代这一操作。

准备一个受支持的 EU5 样本，替换下列示例路径：

```powershell
./Test-PortableRelease.ps1 `
  -Output 'C:/验收记录/完整转换' `
  -Environment 'Windows 11 独立测试机；未安装开发工具' `
  -EU5 'D:/Games/Europa Universalis V' `
  -Game 'D:/Games/Victoria 3/game' `
  -Baseline 'D:/测试输入/原版1836.v3' `
  -Save 'D:/测试输入/样本.eu5'
```

该模式依次执行完整性与启动检查、规则生成、完整转换、项目保存重开、导出及数据回读。规则资源只能从本机游戏生成；版本或引用资源不匹配时会停止。带模组的 EU5 样本还需要原有模组及相同版本，首次验收宜先用原版样本。

如果只需复核已有候选，可使用 `-Package` 和 `-Game`，不要同时传入 `-Save`：

```powershell
./Test-PortableRelease.ps1 -Output 'C:/验收记录/项目回读' `
  -Game 'D:/Games/Victoria 3/game' -Package 'D:/转换结果/complete'
```

## 读取结果与游戏内检查

`acceptance.json` 记录检查范围、运行库版本、清单摘要和各阶段结果；失败时另有 `failure.log`。`status: passed` 只表示所选静态检查通过。`clean_machine_verified` 和 `game_runtime_verified` 始终为 `false`，因为脚本不能独立证明机器背景或游戏行为。测试人员应另行记录实际环境与人工检查结果，不要据此字段推断测试失败。

游戏内验收需使用本次导出的模组，新开战役并核对国家归属、人口与身份、本土、宗教图标、经济和开局战争。推进时间，保存后重开，记录崩溃、错误日志和未覆盖项。附候选 ZIP 摘要、源存档摘要、导出目录和观察日期，使记录能对应到具体构建。不得用历史版本的测试结果替代当前候选。

验收目录含解码存档、私人输入路径及转换数据。提交问题前应摘取必要错误信息并清理个人信息，不要直接公开整个目录。
