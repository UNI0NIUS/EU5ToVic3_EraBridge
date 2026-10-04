# Build EraBridge

[简体中文](BUILDING.md) · **English** · [Documentation](README.en.md)

Windows x64 is the maintained desktop build environment. Upstream Linux build files remain, but this fork's desktop version has not completed Linux validation.

Initialize submodules after cloning:

```powershell
git submodule update --init --recursive
```

For desktop source development, use Python 3.11 or newer with Tk, NumPy and Pillow. Development tests also need SciPy:

```powershell
python -m pip install -r requirements-dev.txt
python -X utf8 tools/converter_desktop.py --language en --no-autoload
python -X utf8 -m unittest discover -s tools -p 'test_converter_*.py'
```

Some integration tests require local game installations and private intermediate data. State which inputs were available when reporting results. Language tests and small synthetic export fixtures are in `test_converter_i18n.py`, `test_converter_desktop.py` and `test_converter_workbench.py`.

The C++ importer needs CMake, Ninja, librakaly 0.12.7 and a suitable Windows C++ toolchain. The maintained release setup uses Visual Studio Community 2022 and Windows SDK; review their applicable terms. Example using the repository's tool layout:

```powershell
. ./tools/Enter-DevEnvironment.ps1
cmake --preset x64-release-windows -B build/community-release -DBUILD_FRONTEND=OFF -DCMAKE_MAKE_PROGRAM="$PWD/.tools/python/Scripts/ninja.exe" -DRAKALY_DIR="$PWD/.tools/rakaly-0.12.7/librakaly-0.12.7-win-msvc"
cmake --build build/community-release --target EU5ToVic3Converter EU5ToVic3Tests --parallel 8
ctest --test-dir build/community-release --output-on-failure
```

Desktop packaging requires the importer and Rakaly DLL under `build/Release-Windows/EU5ToVic3/`, a Python runtime with Tk and dependencies, and the repository's release-rule recipes. With those inputs available:

```powershell
./tools/Build-ConverterApp.ps1 -Output build/EraBridge-local
```

The output must be a new directory inside the repository. The packager currently assumes the maintained local Python distribution layout; other installations may need adjustments. `-SkipRuntime` refreshes an existing local build and is not a clean release procedure. Translation catalogs in `tools/converter_locales/` must accompany the Python code.

Default packaging includes rule recipes rather than private game-derived resources. Users prepare complete rules from their own games and baseline save. `-IncludeLocalRules` is for local debugging and must not be used for public candidates. See the [Chinese release procedure](RELEASING.md) and [licensing notes](LICENSING.md) before distribution.
