# Culture and religion settings

[简体中文](CONVERTER_IDENTITY_SETTINGS.md) · **English** · [Documentation](README.en.md) · [Release preparation](RELEASING.en.md)

Applies to desktop version 0.12.2. Identity decisions use source culture keys, resident distributions and explicit configuration, not country or population history from older campaigns. Rule updates apply to subsequent conversions; existing candidate packages need the project-upgrade process.

## Rules and scope

- `culture_mapping.json` maps source culture keys. It retains the general converter's existing cross-save review and applies explicit corrections from `m5_culture_identity_corrections.json` and `m5_culture_framework.json`. Earlier campaigns' populations do not determine a new save's cultures.
- `assets/` contains only culture, religion, heritage, language and cultural-group definitions, identity localization and religious icons. Definitions merge by key, with the latest explicit corrections taking priority. It carries no country, population, economic or territorial history, or old-tag country names.
- `identity_homelands.json` combines historical cores and confirmed identity rules. Ordinary cultures require current source-resident anchors intersecting approved core states. Vanilla homelands remain; unresolved entries are not filled automatically by population share.
- Migrant cultures continue to derive from origin and colonial region; residents retain their religion. A migrant homeland requires strictly more than **50% of the entire state's population**, not a majority of one country's part. Ordinary cultures do not use this majority supplement.
- The Luyi design explicitly targets dates before the 1830s. From 1830 onward, the general configuration retains the existing cross-save-reviewed Lozi identity rather than applying the pre-Kololo language design to later saves. This is a conservative applicability boundary, not a simulated exact date of language change.
- Review status remains in configuration and reports. Display names omit workflow labels such as “review mapping” or “provisional”; internal `reviewed` keys are unchanged.
- All 16 custom religious icons are compiled to 256×256. Their visible content is cropped using transparency bounds and centered with a longest side of 240 pixels.
- Dynamic flags are regenerated from the current conversion's countries, laws and source flags. A subject-relationship change alone does not shrink the source flag into a canton. Composite flags for government changes retain the complete source image. Old-campaign country-name patches are not loaded.

These settings retain the limits of their historical evidence. Template names and appearances are not historical certification; unresolved core homelands remain empty, and cultural groupings are explicit game-design choices. Different source dates, maps and mods still require appropriate rules.

## 0.12.1 display and homeland repairs

Old `replace` localization can override new names. Upgrades remove old translations for the same identity keys and verify that Chinese and English entries are unique and match current rules.

Manchu, Jing, Uzbek and Polish regain single names. Chuvash, Romanian, Kanuri, Marathi, Burmese, Shan, Mazanderani and Chokwe also regain concise names. Population mappings and group membership remain unchanged. Jing homelands are restored in the vanilla Tonkin, Annam and Mekong core states where Jing residents are present.

`config/personal/religion_palette.json` centrally defines display colors for 16 added religions. Fire-orange Zoroastrianism, cyan-blue Bon and gold Jainism are map colors only; they do not change religious identity or taboos.

Shared identity resources no longer overwrite campaign event translations. Old packages recover missing text from the verified political output of the same source campaign. Export validation covers custom event titles, body text, flavor text and options. Upgrades use a separate directory, do not repeat economic supplementation or remap converted population, and replay saved edits. Static checks do not replace in-game event tests.

## Building and updating

Create a new rule directory from the old general rules without overwriting inputs:

```powershell
python -X utf8 tools/update_converter_identity_rules.py --root . --base <old-rules> --package <verified-M5-identity-package> --out <new-rules> --game <V3-game-directory>
python -X utf8 tools/verify_converter_identity.py --rules <new-rules> --game <V3-game-directory> --eu5 <EU5-game-directory> --output <verification-report.json>
```

For rules built from scratch, `build_converter_rules.py` accepts `--identity-package` and `--game`. Input identity packages first undergo output-hash validation. The resulting rules do not require the original identity-package directory or `.local` review reports at runtime; conversions still need the configured games and baseline.

Legacy local defaults are `.local/converter/rules/` in source workspaces and `build/ConverterWorkbench/data/rules/` in complete local builds. Keep backups before refreshing local rules. Portable first-use initialization creates a separate workspace directory and remembers its path. Every conversion copies an independent rule snapshot; existing runs are not changed retroactively.

## Validation

Rule readback checks cover every mapping target; culture references to religions, heritages and languages; heritage/language group references; Chinese and English localization; icon sizes and centering; absence of campaign-history leakage; and targets for source years 1337, 1780 and 1836.

Independent population readback checks culture, religion and complete allocation for every source POP. Output populations are compared group by group against resident ledgers and separately recorded template populations. State-history borders are compared with current political output, and migrant-homeland shares are recalculated over whole states. Dynamic flags are checked in subject and independent states. In-game appearance and long campaigns still require new-campaign validation.

See the [validation record](PUBLICATION.en.md) for public evidence and environments. Complete rules and game-derived icons are not distributed with source; see [release preparation](RELEASING.en.md) for resource prerequisites.
