# Source cores, claims and release boundaries (0.12.2)

[简体中文](CONVERTER_SOURCE_CORES.md) · **English** · [Documentation](README.en.md) · [Release preparation](RELEASING.en.md)

Source cores determine releasable provinces; whole-state claims use a separate coverage threshold. Releasable-country flags prioritize recovery from source definitions.

## Boundary rules

1. Use only current `cores` in the source save. Do not revive expired historical grants or equate cultural homelands with country cores.
2. When several EU5 locations map to one V3 province, at least half the distinct mapped locations must hold that country's core for the province to qualify. This is discrete mapping support, not pixel area, population share or a conclusion about historical sovereignty.
3. A whole-state claim requires qualifying core provinces / all assigned land provinces in the state **≥ 30%**. The denominator includes provinces owned by other countries and assigned provinces without source mappings; it is not restricted to the claimant's territory.
4. Release uses the native `provinces` list, not `states` or `use_culture_states`. Small countries below 30% can still be released on qualifying core provinces. Receiving a whole-state claim does not enlarge their release territory.
5. After province transfers or state-boundary edits, export recalculates state coverage and dormant-country capitals. Mergers do not transfer the core provinces themselves to a conqueror's core set.

30% is a moderately conservative gameplay parameter, not a historically established boundary. The 1787 sample produced:

| Rule | Source-core state claims |
|---|---:|
| Old rule: any overlap | 3472 |
| Province-support filter, 20% state threshold | 1258 |
| Province-support filter, 30% state threshold | 996 |
| Province-support filter, 40% state threshold | 800 |
| Province-support filter, 50% state threshold | 677 |

The old rule once granted all of Alaska, a 1,028-province state, from a single province. The state threshold removes such tiny overlaps; higher thresholds also remove more cross-state edge claims. Another 99 claims from the existing independent-region rules remain separately recorded. The table counts only source-core-derived claims.

## Evidence for province-level release

In vanilla V3 1.13.11, `game/common/country_creation/00_releasable_countries.txt` defines release territory for JAN, NAS, ALT and others using `provinces = { ... }`. NAS lists three provinces directly and does not require the whole state. The implementation uses this existing engine interface rather than releasing a state and returning land afterward.

The [official Paradox modding diary](https://www.paradoxinteractive.com/games/victoria-3/news/victoria-3-dev-diary-60-modding) explains that states contain provinces and multiple countries can own parts of one state region. Use the matching game version's files for the specific release syntax.

## Flags and reports

Dormant countries also use `FlagExporter` to recover patterns, emblems, textures and named colors from source flag lists and evaluable conditions. Reused vanilla tags have their old flag lists overridden to avoid displaying another country's flag. Released subjects retain the complete source flag by default.

Of 750 dormant releasable countries in the same 1787 sample, 596 recovered EU5 scripted flags. The other 154 lacked recoverable source definitions and received explicitly audited procedural fallbacks; these are not historical originals. The source `coat_of_arms_manager` was empty (`next_id=0`), so no additional saved dynamic arms could fill those gaps.

`source_claims.json` records each country's core provinces, state coverage, retained claims, flag provenance and failure reasons. Old-project upgrades use separate directories without repeating economic supplementation; population, buildings, starting ownership and saved edits remain. Changing starting files does not retroactively remove claims from an existing game save. Boundary repairs require a new campaign for verification.
