# Windows candidate acceptance

[简体中文](ACCEPTANCE.md) · **English** · [Documentation](README.en.md)

`Test-PortableRelease.ps1` checks a candidate using its bundled Python; no separate Python installation is needed. It writes to a new acceptance directory, does not modify installed games, source saves or existing projects, and does not launch the game automatically. Full conversions can take substantial time and disk space.

## Prepare the environment

Prefer a Windows x64 computer or VM without Python, compilers or development caches. Record the OS version, candidate ZIP SHA-256, game versions and installed runtimes. Extract the complete candidate into a path containing Chinese characters and spaces, preserving its structure. If testing on the development machine, say so: clearing PATH does not prove clean-machine compatibility.

Use `Get-FileHash -Algorithm SHA256` to compare the ZIP with `SHA256SUMS.txt`. The internal manifest detects damaged or modified files; it is not digital-signature identity authentication.

## Startup and integrity

Open PowerShell in the extracted directory and choose an output directory that does not yet exist:

```powershell
./Test-PortableRelease.ps1 -Output 'C:/验收记录/Startup check' -Environment 'Independent Windows 11 test machine; no development tools'
```

Also launch `EU5Converter.exe` manually and check the first-run terms dialog. No should open the terms; Cancel should exit; after reading and accepting, Yes should enter the workbench. Subsequent launches should not ask again. For beta.3, also check language preference restoration and the independent game-language selectors in import/export dialogs. The automated checks do not click through the launcher's terms dialog.

The script checks every release-file hash, unexpected files, Python search paths, NumPy calculations, Pillow reading/writing, Rakaly loading, and creation/closure of the workbench and rule-initialization dialog. In beta.3 it also checks Chinese/English switching. It temporarily restricts the process PATH and Python environment variables, restoring them afterward.

## First use and full conversion

Install supported EU5 and Victoria 3 versions. In V3, disable all mods, start a new 1836 campaign, keep it paused and save immediately. The baseline must be version 1.13.11, dated 1836.1.1. Absence of mod metadata in a save is not a substitute for this preparation.

Choose a supported EU5 sample and replace these example paths:

```powershell
./Test-PortableRelease.ps1 `
  -Output 'C:/验收记录/Full conversion' `
  -Environment 'Independent Windows 11 test machine; no development tools' `
  -EU5 'D:/Games/Europa Universalis V' `
  -Game 'D:/Games/Victoria 3/game' `
  -Baseline 'D:/Test inputs/vanilla1836.v3' `
  -Save 'D:/Test inputs/sample.eu5'
```

This mode performs integrity/startup checks, rule generation, full conversion, project save/reopen, export and readback. Rules use locally installed game resources; version or resource-reference mismatches stop the process. Modded EU5 samples also need the original mods at matching versions. Use a vanilla sample for initial acceptance.

To recheck an existing candidate, use `-Package` and `-Game` without `-Save`:

```powershell
./Test-PortableRelease.ps1 -Output 'C:/验收记录/Project readback' `
  -Game 'D:/Games/Victoria 3/game' -Package 'D:/Conversion results/complete'
```

The full-conversion command uses the pipeline's default output language and has no separate language argument. To test both languages, additionally import with English selected in the workbench, save and reopen the project, then export separately in English and Simplified Chinese, and compare localization reports and game-state readback. Separate export directories intentionally receive separate mod IDs.

## Results and in-game checks

`acceptance.json` records scope, runtime versions, manifest hashes and stage results; failures also produce `failure.log`. `status: passed` means only the selected static checks passed. `clean_machine_verified` and `game_runtime_verified` remain `false`: the script cannot independently establish machine history or game behavior. Record environment and manual results separately; those fields do not by themselves mean the test failed.

In-game acceptance must use the current exported mod in a new campaign. Check ownership, population and identities, homelands, religious icons, economy and opening wars. Advance time, save/reload, and record crashes, errors and untested items. Include candidate ZIP hash, source-save hash, export directory and observation date so evidence identifies a specific build. Historical results do not replace tests of the current candidate.

Acceptance directories contain decoded saves, private paths and conversion data. Extract necessary errors and remove personal information before reporting; do not publish the entire directory. See [problem reports and saves](SUPPORT.en.md).
