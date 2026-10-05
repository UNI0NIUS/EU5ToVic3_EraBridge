# EraBridge — EU5 → Victoria 3

[简体中文](README.md) · **English**

![EraBridge icon](tools/converter_ui/icons/erabridge-beta-128.png)

EraBridge converts Europa Universalis V saves into candidate Victoria 3 mods. Its Windows desktop workbench lets you inspect the map, adjust population and arable land, edit regions, and export an independent starting world.

The published version is **0.12.2-beta.3**, a Windows x64 community preview, primarily tested with EU5 1.3.11 and Victoria 3 1.13.11. This release includes the bilingual workbench and independent output-language selection.

This is an independent fork of [ParadoxGameConverters/EU5ToVic3](https://github.com/ParadoxGameConverters/EU5ToVic3), based on upstream commit `56ee636b6ebd8a110b54d3133794f964af0f0e1e`. It is not affiliated with the upstream team. This fork uses AI-assisted development; upstream does not accept such contributions. Please direct feedback to this fork.

## Workbench and game languages

The desktop workbench supports Simplified Chinese and English. Use **语言 / Language** to switch while idle; your choice is remembered. Import and export dialogs have a separate **Game display language** setting. Both existing localization sets remain in the mod, while the chosen language is checked before completion and used for installation guidance.

Set Victoria 3 to the matching language, enable the exported mod, and start a new campaign. The converter produces a starting-world mod; **Victoria 3 creates the `.v3` save when you save that campaign**. Changing the workbench language does not translate user-entered names or change game rules.

## Download and run

Download `EraBridge-0.12.2-beta.3-windows-x64.zip` from the [published release](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/releases/tag/v0.12.2-beta.3). Extract the complete archive into a writable folder and run `EU5Converter.exe`. Read and accept the bundled third-party terms on first launch. Python and runtime dependencies are included.

The automatic GitHub “Source code” archives are not runnable distributions. Source builds require initialized submodules. To build from source, follow the [build guide](docs/BUILDING.en.md).

This is a portable archive without an installer. Keep its complete directory together.

For an existing local source build, use `Open-ConverterWorkbench.cmd` or `build/ConverterWorkbench/EU5Converter.exe`.

Prepare conversion rules from your own installed games and a vanilla V3 starting save. Then import an EU5 save, inspect the result, make any edits, and export. The repository does not include game installations, player saves, baseline saves, extracted game textures, or complete locally generated rule bundles.

## Capabilities and limits

- Imports text, compressed and binary EU5 saves, converting population, identities, countries, politics, economies, armies and opening wars.
- Displays map layers, markets, food and job estimates; supports land, building, province and population edits with previews and undo.
- Merges adjacent regions or countries and changes province ownership or state borders; exports an independent candidate mod.
- Preserves province-level source-core release territories, assesses whole-state claims separately by coverage, and reconstructs source flags where supported.

Selected 1337, 1780 and 1787 saves have completed conversion and static checks. In-game appearance, economic balance, long campaigns and independent Windows environments still require validation. Food and job indicators estimate capacity; they are not measured famine or unemployment. Resource-building capacity and some vanilla script errors are known issues. Compatibility with arbitrary versions and third-party mods is unverified.

The beta.3 follow-up still failed on a 1338 KNI binary save with `Unknown EU5 binary tokens: import refused`. A separate 1337 control save passed complete conversion and bilingual export readback on the development machine. See the [validation record](docs/PUBLICATION.en.md) for exact scope.

## Default output locations

Relative to the portable application folder, initial conversion results are under `data/runs/<timestamp-id>/complete/`; subsequent workbench exports go to `data/exports/<timestamp-id>/`. Use **Open output directory** to find the latest output. The converter does not install exports into the V3 mod directory automatically. See [paths, logs and save submission](docs/SUPPORT.en.md).

## Documentation and feedback

- [Workbench guide](docs/CONVERTER_WORKBENCH.en.md)
- [Language behavior and translation maintenance](docs/LOCALIZATION.en.md)
- [Build instructions](docs/BUILDING.en.md)
- [Documentation index](docs/README.en.md), covering English usage, technical references, licensing and validation records
- [Culture, religion and identity rules](docs/CONVERTER_IDENTITY_SETTINGS.en.md)
- [Source cores, claims and release boundaries](docs/CONVERTER_SOURCE_CORES.en.md)
- [Flag conversion](docs/FLAG_GENERATION_RULES.en.md)
- [Public materials and validation record](docs/PUBLICATION.en.md)
- [Release preparation and acceptance](docs/RELEASING.en.md)
- [Provenance and licensing](docs/LICENSING.en.md)
- [Issue reports, logs and save submission](docs/SUPPORT.en.md)
- [Report a problem](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/issues/new?template=bug_report_en.md)

`config/personal/` retains an early development directory name. It contains conversion rules, research material and some older campaign settings. Their scopes differ; do not treat every configuration as a default for arbitrary new saves.

## License

The code retains the [MIT license](LICENSE). Preserve copyright and license notices when modifying or redistributing it. Submodules and third-party components retain their own licenses. The MIT license does not grant redistribution rights to game content, trademarks or Workshop assets; see the [licensing notes](docs/LICENSING.en.md).
