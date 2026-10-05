# Build EraBridge

[简体中文](BUILDING.md) · **English**

[Documentation](README.en.md) · [Release preparation](RELEASING.en.md)

Windows x64 is the maintained build environment. Upstream Linux build files remain, but this fork's desktop version has not completed Linux validation.

## Get the source

After cloning this fork, initialize submodules from the repository root:

```powershell
git submodule update --init --recursive
```

`commonItems` and `Fronter` use pinned upstream submodule commits. Do not replace them with ordinary copies of local directories.

## C++ importer and tests

Prepare Python 3.11 or newer, CMake, Ninja and librakaly 0.12.7. Windows release builds use Visual Studio Community 2022's C++ desktop tools and Windows SDK; confirm your eligibility and accept the applicable product terms. `Setup-PersonalEnvironment.ps1` can download other local tools but does not replace the applicable Visual Studio license.

`Enter-DevEnvironment.ps1` prefers the official installation under `.tools/VisualStudio2022`. Use `-VisualStudioPath` for another installation. When changing compilers, use a fresh CMake build directory so an old cache does not retain another toolchain:

```powershell
. ./tools/Enter-DevEnvironment.ps1
cmake --preset x64-release-windows -B build/community-release -DBUILD_FRONTEND=OFF -DCMAKE_MAKE_PROGRAM="$PWD/.tools/python/Scripts/ninja.exe" -DRAKALY_DIR="$PWD/.tools/rakaly-0.12.7/librakaly-0.12.7-win-msvc"
cmake --build build/community-release --target EU5ToVic3Converter EU5ToVic3Tests --parallel 8
ctest --test-dir build/community-release --output-on-failure
```

For routine builds using the same toolchain, run `tools/Build-Personal.ps1`. Its output is under `build/Release-Windows/EU5ToVic3/`, with test logs in `.local/m0/`. It runs CTest by default; `-ConfigureOnly` only configures, and `-Jobs 4` reduces parallelism.

## Python tools and tests

The desktop runtime uses NumPy, Pillow and Tk; development tests also need SciPy. Local validation used Python 3.13.9. The code uses `hashlib.file_digest`, requiring Python 3.11 or newer. Install dependencies in your own virtual environment and check that its Tk is available:

```powershell
python -m pip install -r requirements-dev.txt
python -X utf8 -m unittest discover -s tools -p 'test_*.py'
```

Some historical tests and audit scripts read local game installations or intermediates under `.local/`. Those integration checks cannot be reproduced without their inputs; state the environment and skipped checks when reporting results.

To start the desktop in English without reopening the last project:

```powershell
python -X utf8 tools/converter_desktop.py --language en --no-autoload
```

Language tests and small export fixtures are in `test_converter_i18n.py`, `test_converter_desktop.py` and `test_converter_workbench.py`.

## Additional desktop-packaging inputs

`tools/Build-ConverterApp.ps1` calls `package_converter_app.py` and needs:

- The built C++ importer and Rakaly DLL.
- A Python environment containing NumPy, Pillow, Tk and dependency DLLs.
- `config/release_rules/` recipes and the configuration files they reference.

Default packaging does not read the development machine's `.local/converter/rules/`. On first use, players prepare private resources from their games and a vanilla V3 1836.1.1 baseline save. `initialize_converter.py` checks recipe, map and referenced-field hashes; changed game resources require a maintainer to update the recipe. `freeze_release_rules.py` maintains recipes and is not a player first-use step.

`-IncludeLocalRules` is only for local debugging. It includes complete existing rules and must not be used for public candidates.

With inputs available, run:

```powershell
./tools/Build-ConverterApp.ps1 -Output build/EraBridge-local
```

Output must be a new directory inside the repository. The packager currently collects dependencies according to the maintained local Python distribution layout; other installations may need adjustments. `-SkipRuntime` refreshes an existing local build and is not a clean release procedure. The `tools/converter_locales/` catalogs must accompany the Python code.

Older builds or ZIPs using `-IncludeLocalRules` may contain local default paths and game resources. Do not use them directly as public downloads. Before publishing binaries, check dependency licenses, asset provenance and path cleanup. Record development-machine checks separately from independent-machine acceptance. See [release preparation](RELEASING.en.md) and [licensing](LICENSING.en.md).
