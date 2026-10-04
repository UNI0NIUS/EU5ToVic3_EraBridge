# Desktop workbench

[简体中文](CONVERTER_WORKBENCH.md) · **English** · [Documentation](README.en.md)

The native Tk desktop workbench runs locally on Windows. It does not require a browser. This guide covers the beta.3 release with English support; see [language coverage](LOCALIZATION.en.md) for the remaining untranslated diagnostics.

## Start and import

Run `EU5Converter.exe` from a complete portable distribution. For a local build, use `Open-ConverterWorkbench.cmd`. For a source checkout with dependencies installed:

```powershell
python -X utf8 tools/converter_desktop.py --language en
```

Choose **English** in **语言 / Language** to change the interface. Wait until current operations finish before switching. The workbench remembers the choice.

1. Click **Prepare rules**. Select EU5, the Victoria 3 `game` directory, and your own vanilla V3 starting save. With Victoria 3 1.13.11, disable mods, start an 1836 campaign, pause immediately and save. Generated resources remain local.
2. Click **Import EU5 save**. Select your text, compressed or binary EU5 save, the games and the rules manifest. Add source mod directories, one per line, or leave them empty for exact local Workshop name/version matching. Missing or ambiguous matches stop conversion.
3. Choose **Game display language** independently of the interface language. Conversion generates the existing Chinese and English localization sets and validates the selected one.
4. Wait for conversion to finish; the map loads automatically. Unknown identities, unsupported war goals, map mismatches and other unresolved inputs may stop conversion. Inspect the reported stage and saved log.

Use **Open project / result** to resume a project or open a candidate folder containing `package_report.json`. Projects and exports use separate directories; input saves and mods are not overwritten.

## Inspect and edit

Drag to pan, scroll to zoom, and click a region or table row for details. Search by name, state key or country TAG. Layers show ownership, state/province borders, strategic regions, markets, arable alerts, job gaps and food gaps.

| Setting | Default | Effect |
|---|---:|---|
| Population multiplier | 1.0 | Changes exported population |
| Arable land multiplier | 1.0 | Changes exported state arable land |
| Workforce share | 25% | Risk estimate only |
| Formal staffing | 75% | Planned formal capacity only |
| Food consumption SoL | 10 | Consumption basket for estimates |
| Low arable alert | ≤ 3 | Country's share within a state |
| Severe job gap | ≥ 25% | Estimated workforce without capacity |
| Food gap | ≥ 20% | Effective gap after estimated access |

Multipliers recalculate from project inputs rather than compounding on repeated application. Food and unemployment figures are static estimates, not measured famine, employment, wages or profitability. Market estimates include local infrastructure and connectivity but do not simulate the full game economy.

**Edit land / buildings / provinces** provides state base arable land, region building levels and province transfers. Zero building levels remove the building. Subsistence capacity uses remaining arable land. Building availability follows the receiving country's rules. Arable advice estimates capacity for the selected region; it does not guarantee hiring or income.

Province transfers can change ownership and state membership. The source state must retain at least one province. Population and buildings are apportioned by province counts; total world population and building levels are conserved by transfers. Arable and resource totals do not automatically follow moved borders. Review before applying, and use **Undo last edit** to reverse an operation.

## Merge and bulk tools

Choose a source, scope and adjacent target. A region merge transfers that country's part of the current state; a country merge transfers all its territory. Manual merges require land adjacency. The recipient retains its identity, laws and technology while residents retain their cultures and religions. Capital, diplomatic, war and building conflicts are shown in the preview.

Bulk merging can group by state or strategic region, using selected food/job risks or an entire scope. The recipient has the most provinces in that grouping; TAG order breaks ties. Strategic merging may cross state borders without changing those borders. Building conflicts offer a choice between skipping affected regions and explicitly demolishing conflicting buildings. One undo reverses the batch.

Other tools reduce population by percentage or job capacity, add arable land for severe unemployment, and estimate construction for one selected province. Review their affected regions, caps and tradeoffs. Reducing population can also reduce subsistence output; additional buildings may face technology, resource, land, coast, workforce or supply-chain limits. These tools do not guarantee that all risks disappear.

## Export and save in Victoria 3

Click **Export mod**, enter a launcher display name and choose **Game display language**. The project remembers the name and language. The converter validates edits and localization, writes an independent output folder and provides installation guidance in the selected language.

Copy `eu5_converted` and `eu5_converted.mod` into the Victoria 3 user `mod` folder. Enable this candidate in the launcher, set Victoria 3 to the chosen language, and start a new campaign. Save in the game to create a `.v3` file. The workbench itself exports a mod, not a native save.

Both language sets remain available; changing the game's language selects the corresponding resources. Custom names are preserved. Static checks and a successful export do not establish in-game compatibility or long-term stability.

The [Chinese reference](CONVERTER_WORKBENCH.md) contains additional implementation detail. [Language documentation](LOCALIZATION.en.md) explains persistence, coverage and how to add translations.
