# Flag conversion and generation rules

[简体中文](FLAG_GENERATION_RULES.md) · **English** · [Documentation](README.en.md)

Flags prioritize recoverable designs from the source save. Where evidence is insufficient, explicit identity and source data guide fallback generation. Generated results must not be labeled historical originals. See [source cores](CONVERTER_SOURCE_CORES.en.md) for dormant-country release flags.

## Principles and priority

1. **Identity before place names.** Read culture, government, reforms, formation origin and actual overlord relationships from the save. Matching place names do not establish identity with a real country, tribe or modern administrative region.
2. **Original arms first.** Search saved flag keys, current tags and definition tags; parse constants, parent arms and assets. Variant priority considers era, government, reform and former-tag conditions only where source evidence supports them. Unknown dynastic and territorial conditions do not count as satisfied.
3. **Verified identity fallback.** If source arms cannot be recovered but a reviewed V3 identity exists, retain its V3 flag. Matching tag letters alone are insufficient.
4. **Cultural patterns before generic religious symbols.** Generated flags may reuse EU5 wampum, Tujia white tigers, Miao patterns, Mongol ornaments and South American designs. The cultural-asset dictionary is a cross-campaign rule, not a country whitelist. Reusing one emblem does not reconstruct a complete original flag.
5. **Geography and production require evidence.** Source location counts and whether the target capital state is coastal identify maritime candidates for small coastal countries; this is not strict island detection. Aggregate products by source RGO employment: one product needs at least 45% to be dominant. Zero employment or missing data does not justify a guess. Products with corresponding motifs can affect the emblem; otherwise retain the cultural/regional design.
6. **Government determines layout, not an invented dynasty.** Republics may use clear geometric fields. Cultural textiles and wampum do not receive European shields. Monarchy alone does not grant the arms of a historical dynasty.
7. **Overlord relationships determine cantons.** Actual colonies and companies retain dynamic overlord-flag cantons and use overlord heraldic colors for related styles, including ensigns, local shield flags and trade flags. Ordinary subjects are not automatically colonies; independent countries have no overlord canton. Companies prioritize maritime motifs.

Within evidence-constrained choices, stable hashes determine layout and border details, not culture, religion or overlord relationships. Generated flags are checked for duplicates, missing assets, flag boundaries and canton overlap.

## Implemented input interfaces

`tools/m3_flag_art.py` provides:

- `economic_features(countries, source_economy, coastal_states)`: accepts any campaign's countries, source economic locations and coastal states, without hard-coded country names or tags.
- `contextual_design(identity, color, country, src, colonial, region, company)`: designs from culture, government, source evidence and the features above.
- `compile_design(design)`: emits native V3 coat-of-arms script.

`FlagExporter` optionally reads source economic features from `world.flag_features`. Without them it uses supported cultural/regional evidence, not inferred specialist industries. Callers should pass the matching campaign's economic data and verify its source hash.

Only some cultural assets and product motifs are supported; missing ones retain explicit regional fallbacks. Strict whole-territory coast/island recognition, complete interpretation of dynasty/territory variants and export of in-game dynamic arms are not implemented.

## Rendering

V3's local `jomini/gfx/FX/coat_of_arms/coat_of_arms_textured_emblem.fxh` uses color1 as the base, the green channel to blend color2, the red channel to blend color3, and the blue channel for lighting. Complex cultural textiles must not be reduced to three identical colors.

The compiler emits all three colors explicitly; the preview uses the same channel order. Previews do not simulate every game-rendering effect. A gray canton is an overlord-flag placeholder, not an in-game screenshot.

## Evidence and validation boundaries

A modern flag with the same name is not automatically the original flag of an alternate-history campaign. Empty saved coat-of-arms managers, missing definitions and unevaluable conditions retain their reasons in reports. Reports distinguish source-script flags, reviewed target-identity flags and procedural fallbacks.

Validation should cover generic designs for unknown countries, no product inference at zero employment, cultural-pattern color separation, canton bounds, duplicate flags and asset references. Rendering and generation changes also require in-game checks for appearance and caching; static previews are not screenshots of engine behavior.

Flag assets may come from the user's installed games. Licensing the generator code does not license redistribution of those assets; see [licensing](LICENSING.en.md).
