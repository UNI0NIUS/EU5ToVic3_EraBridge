# Provenance and redistribution licensing

[简体中文](LICENSING.md) · **English** · [Documentation](README.en.md)

Review date: 2026-10-03, covering v0.12.2-beta.2 source and the Windows x64 package. Beta.3 retains the same runtime components and native importer, rebuilding the desktop launcher and updating bilingual source, translated component terms and documentation. The bundled inventory remains the record of actual component provenance.

## Upstream code

This project derives from [ParadoxGameConverters/EU5ToVic3](https://github.com/ParadoxGameConverters/EU5ToVic3), with baseline `56ee636b6ebd8a110b54d3133794f964af0f0e1e`. The local and upstream default-branch [LICENSE](https://github.com/ParadoxGameConverters/EU5ToVic3/blob/master/LICENSE) are MIT, retaining `Copyright (c) 2021 Paradox Game Converters`.

The [MIT license](https://opensource.org/license/mit) permits use, copying, modification, merging, publication, distribution, sublicensing and sale, subject to retaining its copyright and permission notices. The root `LICENSE` remains unchanged; this fork's code modifications also use MIT.

Upstream's [contribution policy](https://github.com/ParadoxGameConverters/EU5ToVic3/blob/master/.NO_AI/README.md) rejects generative-AI code, documentation, pull requests and issues. This fork uses AI-assisted development and is independently maintained. Its work is not submitted upstream or presented as endorsed by upstream. The retained `.NO_AI/README.md` records upstream policy; it must not be used to describe this fork as developed without AI assistance.

## Submodules and dependencies

`commonItems` and `Fronter` are pinned Git references using the addresses in `.gitmodules`. Their own copyright and license terms, including embedded dependencies, continue to apply; the root MIT license does not replace them.

The portable package includes Python, NumPy, Pillow, Tcl/Tk, Rakaly and runtime dependencies. Actual versions, hashes and provenance appear in `licenses/runtime-inventory.json`. Original licenses and required notices accompany the package. Runtime binaries are not committed to the source repository.

### Rakaly

This release uses librakaly 0.12.7, checked against the toolchain lock file. The maintainer has confirmed redistribution authorization for the Rakaly version used in this release; this project does not infer that it covers other versions or publishers. The [license directory](../licenses/README.en.md) retains the wrapper's MIT license and locked dependency notices. Some parsing dependencies originate from AGPL repositories; the outer MIT license does not replace those terms. Bundled notices are not complete corresponding source and grant downstream users no additional rights beyond the applicable licenses.

### Microsoft components

The release build uses Visual Studio Community 2022 licensed under its individual-developer terms. The C++ importer and launcher were rebuilt with that toolchain for beta.2; beta.3 retains the unchanged importer and rebuilds the launcher. Visual C++ DLLs come unchanged from `VC/Redist/MSVC/<version>/x64`, excluding `debug_nonredist`; these paths appear in [Microsoft's redistributable list](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution). UCRT files are matched to their actual Windows SDK provenance and retain their licenses.

The [Community terms](https://visualstudio.microsoft.com/license-terms/vs2022-ga-community/) and [Microsoft redistribution guidance](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170) govern Microsoft components. License texts, end-user terms and required notices are bundled; first launch asks users to read and accept the third-party terms. Microsoft components are not relicensed under MIT, and this release does not grant unrestricted redistribution rights for them.

See [runtime notices](../licenses/THIRD_PARTY_NOTICES.en.md) for FreeType, JPEG and other supplementary attribution. Provenance checks and runtime acceptance are separate: successful execution does not establish redistribution permission.

## Games, mods and icons

Europa Universalis V, Victoria 3, their trademarks, scripts, artwork and other resources belong to their respective rights holders. The converter's MIT license does not authorize redistribution of those materials. Public materials exclude `.local/`, `outputs/`, saves, complete candidate mods and extracted assets. `build/` is not committed; only the reviewed portable ZIP is uploaded as a Release asset.

Some tools read installed games and Workshop content locally to generate conversion results. Publishing those results requires assessing their actual contents. No authorization to redistribute complete Workshop packages was obtained for this release, and source publication excludes them.

`tools/converter_ui/icons/erabridge-beta*` contains this fork's EraBridge application icons, supplied by the maintainer for release. They are not official Paradox or upstream-team branding. Providing these icons does not alter rights in game assets or trademarks.

## Documentation

README and release documentation follow [Humanizer-zh](https://github.com/op7418/Humanizer-zh) as an editorial reference: remove repetition and empty claims while retaining facts, qualifications and completion status. That reference was not copied into the distribution. Historical validation is distinguished from checks repeated for the current release.

Chinese and English project explanations are provided separately. Original third-party license texts remain authoritative and are not replaced by these explanatory translations.
