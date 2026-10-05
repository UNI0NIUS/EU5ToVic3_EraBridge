# EraBridge desktop workbench 0.12.2

[简体中文](CONVERTER_WORKBENCH.md) · **English** · [Documentation](README.en.md) · [Release preparation](RELEASING.en.md)

Since beta.3, **语言 / Language** switches the interface between Simplified Chinese and English. Import and export have a separate **Game display language** setting. Both localization sets remain in the mod; Victoria 3 chooses which to display. To create a `.v3` save, enable the exported mod, start a campaign and save in the game. See [language support](LOCALIZATION.en.md).

This guide covers the portable release and complete local builds. Beta.3 is available as a Windows x64 community preview. The repository provides source; first use requires rules generated from your installed games and baseline save. See [building](BUILDING.en.md). Developer-machine checks have passed, while independent Windows and in-game acceptance remain incomplete.

The native Windows desktop workbench supports map inspection, population and arable-land adjustments, region editing and mod export. Complete builds include Python; no browser or local HTTP service is required.

## Startup and workflow

In a portable release, run `EU5Converter.exe` in the extracted folder. In a source checkout with a complete local build, use `Open-ConverterWorkbench.cmd` or `build/ConverterWorkbench/EU5Converter.exe`. Keep the whole directory together. Use Exit or the window close button to quit. Closing during conversion asks whether to stop it; saves and exports finish before exit to avoid partially written files. Restarting restores the last project.

**Open project / result** loads an existing candidate directory containing `package_report.json`. Its referenced mod files must match the report hashes. Saved projects restore parameters, merge decisions and revision history.

On first use, choose **Prepare rules**. In Victoria 3 1.13.11, disable all mods, start a new 1836 campaign, remain paused and save immediately. Select the EU5 installation, Victoria 3 installation or `game` folder, and that `.v3` save. The program checks date, version and baseline population, then creates identity definitions, localization and icons from installed resources. Missing mod fields in a save do not prove that no mods were enabled; check the launcher yourself.

Rules are written to a new workspace directory and their path is remembered. Failures retain errors without overwriting existing rules. Current recipes target EU5 1.3.11 and V3 1.13.11. Map or referenced-resource mismatches stop initialization; validation cannot be bypassed.

**Import EU5 save** accepts `.eu5` saves, including supported compressed, binary and decoded text formats. Browse opens a Windows file or folder dialog associated with the main window. Supply the EU5 installation, V3 `game` folder and rule `manifest.json`. The next import restores those paths.

With no explicit mod directories, the importer matches names and versions in the current Steam library's Workshop content in the save's recorded load order. Missing or ambiguous matches report an error. Alternatively, enter one exact mod root per line. Automatic matches are recorded in `source/resolved_mods.json`. Mods are not downloaded automatically, and arbitrary third-party rules are not guaranteed compatible. A successful conversion opens the map workbench.

Loading and conversion run in the background, with progress at the bottom. Failures display a reason and save logs. Native import failures show the cause from `log.txt`, such as a missing mod, rather than only an exit code.

Each new-save pipeline independently performs import; population, culture, religion and literacy extraction; geographic completion; country and political rules; economy; armies/navies; supply chains; arable land; and opening wars. Ownership and population come from the current save. Rules supply geographic correspondences, identity mappings, definitions, economic policies and explicit empty-population templates, not older campaign histories.

War records marked `Declined` remain in reports but do not join a side. Wars explicitly named `AGRESSION_WAR_NAME` without serialized goals use the existing humiliation/border-budget approximation, recorded in `war_mapping.json` as `limitation`; nonexistent source territorial demands are not inferred. Other unrecognized goals still stop conversion.

Unknown binary tokens, cultures or religions, map-hash mismatches, unresolved wilderness and unsupported war goals stop conversion and retain the stage, reason and logs. Failed directories do not appear as completed candidates. A sampled 1338 KNI binary save fails with `Unknown EU5 binary tokens` in beta.3; support for binary saves does not mean every binary save is compatible. See [validation](PUBLICATION.en.md) and [reporting problems](SUPPORT.en.md).

## Parameters and warnings

| Control | Default | Meaning |
|---|---:|---|
| Population multiplier | 1.0 | Reallocates from project input population, without compounding; written to export |
| Arable-land multiplier | 1.0 | Changes state totals and estimates country shares using largest remainders; written to state definitions |
| Workforce share | 25% | Risk estimation only |
| Formal-job staffing share | 75% | Planning scenario for formal-building jobs and output |
| Food-consumption standard of living | 10 | Uses native game consumption baskets; risk estimation only |
| Low arable land | **≤ 3** | A country's allocated arable land in a state, not its province count |
| Severe job-capacity shortage | ≥ 25% | Estimated workforce share beyond available job capacity |
| Food-supply shortage | ≥ 20% | Effective food shortage after estimated market access |

Low land, severe job shortage and food shortage trigger independently and can coexist. Search the risk list by country, state display name, state key or tag. Map views cover countries, states/provinces, markets, arable land, employment and food. Click a list entry or map region to locate it; drag to pan and use the wheel or buttons to zoom. Both sidebars scroll so lower controls remain accessible in smaller windows.

## Arable land, buildings and state borders

Select a region and open the region editor. **Whole-state arable land** sets the state's base total; export then applies the global multiplier and allocates country shares in proportion to province counts. Building editing can switch among countries sharing the state, filter buildings and set levels. Zero removes a building; remaining arable land supplies subsistence buildings automatically. New buildings use production methods available to the owner without unlocking technology. Barracks edits synchronize battalion counts; new regions without existing unit types receive basic infantry. Naval-building edits do not automatically add ships.

The arable-land calculator suggests two targets: bring the selected region below the severe-unemployment warning, or provide job capacity for its entire workforce. It shows the state's required base total and increase, the selected region's allocated land and estimated remaining shortage, and can fill the value for preview. It includes the global multiplier, province allocation, existing agricultural land use, formal jobs and subsistence production methods. Suggestions provide sufficient model capacity, not a proven strict minimum, and apply to the selected region. They do not establish actual recruitment, wage or income improvements.

**Map provinces / state borders** transfers selected provinces into a neighboring region and can change both country ownership and state membership. Alternatively, Ctrl-click provinces in one region on the main map before opening the editor. The original state must retain at least one province; deleting states or drawing new pixel provinces is unsupported. Transfers conserve global population and building levels. Since inputs contain regional rather than province-level population/buildings, splits allocate them by province count using largest remainders; building counts can then be edited separately. Border edits synchronize province lists, state history, population, buildings and army stations. Displaced city and other map markers move to remaining provinces in the original state. Arable-land and resource totals do not transfer automatically; adjust state arable totals explicitly.

Every edit shows an impact preview before confirmation and saving, and supports stepwise undo. Agriculture beyond available arable land is flagged and must be reduced or supported with more land before export. Preview and export use the same operation records. Original saves and input mods are not overwritten.

Food calculations include subsistence output and subtract industrial consumption. Following the existing planning rules, 95% of subsistence farmers' food rations are treated as production for their own consumption; unemployed households retain full demand. Markets follow actual candidate subject relations, market agreements and bloc rules, including bloc identity and `power_bloc_customs_union_bool` in active principles. Ordinary blocs do not automatically share a market; `grant_own_market` retains a separate one. The selected region's assumptions dialog explains its bloc and market evidence.

The interface distinguishes local, market and effective shortages. Land connections, including game-defined straits, or usable coastal ports at both ends combine with local infrastructure capacity to estimate market access. Only output and demand expected to reach a market enter its totals. Industrial food inputs are offset by commodity across regions; remaining supply is allocated proportionally to demand so the same food is not counted repeatedly. Disconnected regions retain local risk. Integration, capital moves and diplomatic changes recalculate markets.

This remains a capacity scenario. It does not simulate convoy tonnage, blockades, external trade, prices, wages or actual hiring, and is not an engine-measured market-access value. **Food risk is not observed famine, and a job-capacity shortage is not measured in-game unemployment.** Unparseable capacity or access is shown as unknown and does not trigger automatic mergers.

## Merging on the map

Select a source region, then choose the current state's region or the whole country. Pick a neighboring recipient in the dropdown or activate map target selection and click it.

- A regional merger transfers that country's complete share of the state, including provinces, population and buildings, without changing state boundaries. If it is the source country's final region, country relationships are reconciled as for a whole-country merger.
- A country merger transfers all source regions while retaining the recipient's identity, laws and technology. Residents retain culture, religion and population.
- Manual mergers require genuine land adjacency; jumping across the sea does not qualify.
- If the source survives the transfer of its capital region, its capital moves to the remaining state with the most population, then province count and state key as tie-breakers. Previews show the move. Country mergers redirect diplomacy, remove self-relations, internal treaties and duplicates, prioritize the recipient's existing subject/organization relationships, and avoid subject cycles. Conflicting production methods use ones available to the recipient; locked buildings are still reported.
- If a merger makes war sides overlap or removes a target region, that opening war is ended and listed before confirmation. Other valid wars remain with redirected participants. This is an editing policy, not a new inference about EU5 history. Changes also appear in `package_report.json` under `adjustments`.
- Mergers create no land, jobs or food. The workbench recalculates affected regions; jobs in another state do not automatically solve local unemployment.

Confirmation saves the project's decision and recalculates risk. Undo individual operations or restore the original plan. Each change checks the revision and records history. Changed inputs require reload so that old decisions cannot be applied to a different map.

## Batch integration and responsiveness

Strategic regions use definitions from the selected game installation and have a map layer. Process the whole map state by state or strategic region by strategic region, or only the current state/strategic region. A strategic region's recipient is the country with the most provinces across that entire region; ownership can transfer across states, even into a state the recipient did not previously own, while state borders stay unchanged. Tags break ties. Previews list each selected region's reason, recipient and food-shortage measures.

Selection conditions distinguish market food shortage, local food shortage and shortage remaining after estimated access. They use shared-market totals, local production/demand, and effective shortage respectively. Select any combination, optionally including severe unemployment; matching any selected condition qualifies. Unknown values are excluded. A locally food-deficient region in an adequately supplied market does not qualify solely on that basis for a market-shortage batch. Administrative integration itself does not create food.

Map layers separately display market membership, market food shortage, province-local food shortage and effective shortage after access. Membership colors identify ownership only. Market-food colors are shared within a market. The local layer draws regional values along province borders and does not claim historical food data for individual provinces. Shortage colors are green for none, yellow below the warning threshold, red at/above it, and gray for unknown.

Batch integration offers current or whole-map scope at state and strategic-region levels. Recipients are fixed from pre-operation province counts, with tag tie-breakers; territory already owned by a recipient stays unchanged. Batch integration permits nonadjacent regions inside the selected scope; individual manual mergers still require adjacency.

Before confirmation, review scope, capital moves and political changes. Locked, conditional or production-method-incompatible buildings are listed by type, level and reason. Choose to retain buildings and skip conflicting regions (the default), or remove listed conflicting buildings and integrate. Removal affects only listed conflicts; other buildings transfer with the territory. Export reports retain the removal list. The batch is one undoable operation, restoring both territory and removed buildings. If every region conflicts, the retain option cannot confirm an empty operation; choose removal or cancel. If a country's final territory is divided among several recipients, the recipient taking the most provinces inherits its diplomatic relationships, as shown in the preview. Integration does not guarantee elimination of food or job shortages; merging within one market may change only regional statistics.

Construction and quick integration are separate. After integration, select exactly one province in the province/state editor and request construction advice for that province. Select a production building, a food or employment goal, and a maximum increase. The model divides regional demand equally by province count, estimates levels from marginal improvement per level, and recalculates the proposal's actual static effect. It displays added levels and before/after regional food and job shortages, writing the operation only after confirmation. Technology, arable land, fixed resources, coastal conditions, regional labor and the per-operation limit constrain proposals. Unknown conditions or a worsening metric after one added level produce no automatic proposal. Special buildings outside agriculture, fixed resources and manufacturing remain manually editable.

V3 buildings belong to state-country regions, so suggested construction is assigned to the selected province's current region. Province population/demand is an equal-share estimate, not a historical record. Construction does not guarantee adequate supply-chain inputs or profitability and does not automatically complete an entire country after a merger.

State data is rebuilt in grouped passes, successive edits replay incrementally, and confirmation/undo reuse calculated results. Highlighting uses a separate background task; rapid clicks retain only the latest result without making the whole interface busy. Esc exits target selection. Clicking a non-target also exits and selects normally. A completed merger selects the receiving region.

## Batch population reductions

Population adjustment supports the current state-country region, state, country, strategic region or whole map. Filter by market, local or effective food shortage, severe unemployment, or select every region in scope. Proportional mode takes the percentage to remove; job-based mode estimates remaining population from current job capacity and skips unknown capacity. Every populated region retains at least one person. Culture/religion groups retain their proportions through largest-remainder allocation; provinces, buildings and armies are unchanged.

The confirmation preview shows affected regions, actual population reduction including the global multiplier, and before/after food and job shortages. Reductions may lower subsistence food output or leave buildings and armies understaffed; they do not guarantee that food shortages disappear. One undo restores the whole batch. Source saves and input mods remain unchanged.

## 1337 command-capacity compatibility

V3 1.13.11 scales rank effects by national army/navy rank-impact multipliers. Early-date conversions may lack technologies that supply those multipliers, leaving commanders with ranks but no personal command capacity.

When the native multiplier is nonpositive, the converter provides a base compensation using the game's smallest positive technology increment: currently 20% for armies and 25% for navies. It is removed automatically once native multipliers become available, without granting technology. New conversions and workbench exports both include it.

Scripts require a game restart to load. New campaigns update during initialization; existing saves update at the next monthly country update. Code, script structure and numeric rules have been checked; in-game individual commander panels still require verification.

## Export, files and validation boundaries

Exports can use custom mod names, including Chinese, up to 120 characters. Names appear in launcher metadata, the `.mod` descriptor and export reports. Cancellation creates no output.

Every export creates a new directory and reads back population totals, all provinces and state membership, map-state definitions, capital ownership, building levels and population-region references. Insufficient arable land for existing agriculture or reference conflicts prevent export. Output includes:

- `eu5_converted/` and `eu5_converted.mod`: the independent candidate mod.
- `project.json`: parameters and merge decisions.
- `risk_report.json`: regional risks and assumptions.
- `package_report.json`: input fingerprints, output hashes and validation results.
- `localization_verification.json`: selected-language coverage and file-format checks.
- `README.txt`: installation instructions in the selected output language.

When launched through the release's `EU5Converter.exe`, paths are relative to the application folder:

| Data | Location |
|---|---|
| Completed initial conversion | `data/runs/<timestamp-id>/complete/` |
| Workbench export | `data/exports/<timestamp-id>/` |
| Saved projects | `data/projects/` |
| Complete conversion tasks and their logs | `data/runs/` |
| Workbench errors | `data/logs/` |

**Open output directory** opens the latest output. Source-mode defaults use `.local/converter/`; an explicit `--workspace` changes the root. Exports are not written directly into Victoria 3's mod directory.

Copy the mod into the Victoria 3 user's `mod` directory and enable it in the launcher. Test with a new campaign. The application does not install or replace existing mods automatically. Static checks and successful conversion do not establish in-game behavior, economic balance or long-term stability.

Rules contain resource hashes. When moving to another computer, the player must still supply the local Victoria 3 baseline text; `baseline` and `baseline_sha256` in `manifest.json` must agree. The release includes no games, player saves or baseline saves.

## Development and builds

See [building](BUILDING.en.md), [architecture](ARCHITECTURE.en.md) and the [validation record](PUBLICATION.en.md).

`tools/initialize_converter.py` handles first use; maintainers use `tools/freeze_release_rules.py` to update recipes. The older rule-building entry point is `tools/build_converter_rules.py`, and general conversion stages are in `converter_source_*.py`. Rule and asset manifests constrain support; general input interfaces do not establish compatibility with arbitrary game versions or mods.

Reopening old projects can upgrade their base candidate in a separate directory and replay saved edits. A new reference is saved only after upgrade succeeds. See [culture and religion settings](CONVERTER_IDENTITY_SETTINGS.en.md) and [source cores and release boundaries](CONVERTER_SOURCE_CORES.en.md).
