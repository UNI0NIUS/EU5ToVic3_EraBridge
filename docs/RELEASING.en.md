# Release preparation and acceptance

[简体中文](RELEASING.md) · **English** · [Documentation](README.en.md)

The current portable release is `v0.12.2-beta.3`, a community test release retaining GitHub's **Pre-release** marker. `beta.1` was a source-only preview. Existing tags and downloaded assets are not overwritten.

The repository contains source, configuration, tests and documentation; ZIPs are Release assets. Games, saves, complete generated mods, development conversations and machine-local records are excluded from public materials.

## Prepare a portable package

Rebuild the C++ importer and desktop launcher using the [build guide](BUILDING.en.md). The release environment needs a licensed Visual Studio Community 2022 installation. The script obtains official x64 runtimes from `.tools/VisualStudio2022/VC/Redist/MSVC/` and places them beside Python and the standalone importer. Other dependencies are matched by file hashes against package caches or wheel RECORD files.

The following reproduces the beta.3 packaging layout in a new workspace; a subsequent public revision must use a new version:

```powershell
./tools/Build-ConverterApp.ps1 -Output build/EraBridge-beta3
python -X utf8 tools/prepare_release.py --app build/EraBridge-beta3 --out build/release-preparation/v0.12.2-beta.3 --public-preview
```

Output must be a new directory below `build/`, separate from the input application. `--python-base` selects the packaging Python installation; `--no-archive` creates only the directory and report. Without `--public-preview`, the candidate is marked `INTERNAL`; renaming it does not replace release checks.

| Output | Purpose |
|---|---|
| `EraBridge-0.12.2-beta.3-windows-x64/` | Portable application, runtime, recipes, documentation and licenses |
| Matching `.zip` and `SHA256SUMS.txt` | Download assets and archive hash |
| `release-readiness.json` | Local provenance commit, worktree state and unfinished validation |
| `build_manifest.json` inside the package | SHA-256 for every payload file, excluding the manifest itself |
| `licenses/runtime-inventory.json` | Component provenance and license locations |

The script only prepares materials; it does not upload, tag or approve publication, and `ready_for_publication` remains `false`. Integrity and runtime acceptance have separate reports. Provenance matching alone is not a completed licensing review; see [licensing](LICENSING.en.md).

## Publication checks

1. Build from the intended source commit. Match binaries, rules and reports to the same candidate and exclude unrelated local files.
2. Inspect the manifest and ZIP for personal paths, secrets, saves, complete private rules, logs and development caches. Default game and candidate paths must be empty.
3. Extract into a new path containing Chinese characters and spaces and run the [acceptance tools](ACCEPTANCE.en.md). Relocation on a development machine is not clean-machine acceptance.
4. State the verified scope, resource-capacity and script errors, and remaining independent-machine and long-campaign gaps in the [release notes](releases/v0.12.2-beta.3.en.md).
5. Create a new tag and draft Release for that commit. Upload the ZIP and checksum file, check server asset hashes and sizes, then publish as a pre-release. Future revisions use new versions rather than replacing downloaded assets.

## Community testing and documentation

Feedback on first-use initialization, full conversion, map editing, save/reopen, export and in-game loading is welcome. Resource-building capacity and some vanilla script errors are disclosed issues; independent Windows environments and long campaigns remain unverified. These gaps are not described as passed checks and do not prevent an explicitly labeled community preview.

Maintain Chinese documents and their `.en.md` counterparts together, with reciprocal language links. `PUBLIC_DOCUMENTS` in `tools/prepare_release.py` explicitly lists package documentation; add both editions when adding a guide. Workshop descriptions have separate Chinese and English files; see [Workshop publishing](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/blob/master/EU5ToVic3/Resources/workshop/PUBLISHING.txt).

Documentation updates on `master` do not change previously published ZIPs or tag snapshots. New download packages must use a new version. GitHub's automatic Source code ZIP/TAR files are source snapshots without the portable runtime or complete submodules, not installation packages.
