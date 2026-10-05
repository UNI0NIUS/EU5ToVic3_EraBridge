# Conversion rules

[简体中文](CONVERSION_RULES.md) · **English** · [Documentation](README.en.md)

This guide describes the 0.12.2 conversion principles and code entry points. Rules use the source save, matching game definitions and explicit configuration. Where game mechanics have no direct equivalent, the output should record approximations and unresolved cases.

## Geography and population

Source locations map to target provinces through reviewed mappings. Conversion stops when map hashes differ, a populated source location has no mapping, or wilderness ownership remains unresolved. Unknown territory must not be silently filled using neighboring countries or an older campaign.

The population ledger preserves source culture, religion, population and allocation evidence. Integer allocation must support readback; template population is recorded separately. A target culture's default religion does not override residents' actual religion. Literacy is weighted by allocated population and written in a numeric format the engine accepts.

The economic pipeline supports preserving baseline population or calibrating it to job capacity. `preserve` retains calibrated baseline counts; `reserve_15` targets a workforce of at least 115% of job capacity. Population changes are recalculated from the baseline, not repeatedly applied to already reduced output.

Entry points: `extract_m4_population.py`, `extract_m4_literacy.py`, `converter_source_population.py`; mappings and policies are in `config/geography/` and the population configuration. See [culture and religion settings](CONVERTER_IDENTITY_SETTINGS.en.md) for identity scope and historical-homeland conditions.

## Countries, cores and flags

Country identity prioritizes verifiable source definitions. Matching names or tags alone do not justify reusing a target country. Countries generated in uncolonized territory require resident identity and continuous geographic evidence; colonial projects and native countries are handled separately.

Source cores determine province-level release territory. At least half the mapped source locations must support a country's core before a target province qualifies. A whole-state claim separately requires qualifying core provinces to cover at least 30% of all assigned land provinces in that state. See [cores and release boundaries](CONVERTER_SOURCE_CORES.en.md).

Flags prioritize recoverable source designs. Unrecoverable designs receive an explicitly identified fallback. Unknown dynasty or territory conditions do not count as satisfied; see [flag rules](FLAG_GENERATION_RULES.en.md).

## Politics and technology

Laws and institutions prioritize source systems and valid conditions. Historical references are an inference layer and must be identified as such. Insufficient source evidence leaves an explicit baseline or unresolved status; a country name alone must not assign a complete institutional system.

Where vanilla country conditions restrict chiefdoms, elder councils, manorialism, hereditary bureaucracy or peasant levies, the converter adds retention conditions only for countries that use those laws at the converted start. After changing laws, adopting them again still requires vanilla conditions. The engine creates eligible HRE identity journal entries automatically; history scripts must not add duplicates.

Technology uses source evidence, combined conditions and target prerequisites. Similar source technology names do not establish equivalent capabilities. Economic, military and social branches are evaluated separately. Output checks revisit incompatible laws and building or unit prerequisites.

Entry points: `extract_political_features.py`, `political_rulebook.py`, `converter_source_politics.py`; military rules are in `config/personal/military_technology.json`. Organization identities and journal entries do not imply implementation of elections, reforms or every diplomatic mechanic.

## Economy and military

Economic conversion reads source industries, employment, development and mapped technology. A building's `employed` field is employment for the whole building: do not multiply it by building levels again. Buildings explicitly referencing nonexistent population objects are excluded from conversion, with their original records retained for diagnosis.

Buildings, production methods and expansion are constrained by technology, resources, labor, arable land and infrastructure. Supply-chain supplementation within shared markets also checks upstream inputs and records unresolved shortages. Full-staffing capacity, base prices and standard-of-living scenarios are planning estimates, not actual GDP, income, recruitment or market prices.

Armies and fleets derive from source military data. Deployment must respect target territory, building capacity and unit prerequisites. Units that cannot be placed, and special categories such as transports, are recorded separately rather than counted as fully restored combat power.

Entry points: `extract_economy_source.py`, `build_economy.py`, `complete_economy.py`, `converter_source_complete.py`; policies are in `config/personal/economy*.json`.

## Opening wars

The converter restores representable sides and goals using the target game's budget, primary-goal and peace rules. `Declined` participation records appear in reports but do not add participants.

If a save explicitly names a war `AGRESSION_WAR_NAME` without serialized goals, the existing humiliation/border-budget rules provide an approximation, recorded as a `limitation`. This does not infer territorial claims absent from the source. Other unsupported goals stop conversion.

Participant checks require all source members on both sides and reject extra aligned countries. Neutral observers in diplomatic plays are not participants. Opening-state validation is recorded separately from countries joining normally later. Existing edited exports are not overwritten by source-war records; fully applying war-generation fixes requires a new conversion.

Restoring opening-war relationships does not fully restore occupation, losses, mobilization or diplomatic plays. Entry points are `extract_war_source.py` and `opening_wars.py`; configuration is in `config/personal/opening_wars.json`. Engine behavior requires separate validation against the actual output.

## Unknown inputs and validation boundaries

Unknown tokens, identities, maps or rule conditions must produce a specific error or limitation, not a hidden success. Static checks establish only their stated structural and numeric constraints. Game loading, long-term economic balance and arbitrary mod compatibility require separate tests; see the [validation record](PUBLICATION.en.md).
