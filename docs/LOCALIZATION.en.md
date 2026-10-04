# Workbench and game languages

[简体中文](LOCALIZATION.md) · **English** · [Documentation](README.en.md)

Starting with `v0.12.2-beta.3`, the release includes Simplified Chinese and English workbench languages and independent output-language selection.

## Workbench language

Use **语言 / Language** in the main window to switch immediately. The preference is stored in the workspace's `desktop.json` alongside `last_project`. Switching preserves unapplied settings, map layer, filter, selected region and merge scope. Wait for background operations, map loading and selection to finish before switching.

Menus, settings, legends, edit dialogs and workbench-owned messages have English translations. State, country, market, strategic-region and building names use the selected language's game and mod resources. Mod resources override the base game; `replace` overrides ordinary mod localization. Chinese display can fall back to English. Custom names remain unchanged; missing names retain an existing label or script key.

Calculation assumptions, market relationships, arable advice, construction and edit validation now have English messages. First-launch prompts and component terms are bilingual. Long labels wrap and table headers expand. Food and employment construction goals use separate internal values rather than translated text prefixes.

Original logs and saved reports retain their source language. Backend diagnostics not yet connected to translation, and dynamic sentences in historical reports, may still be Chinese. The legacy browser workbench (`converter_app.py`) has not been migrated.

## Output language and saves

1. Choose **Game display language** when importing an EU5 save. Initially it follows the workbench language; subsequent imports remember the previous choice.
2. Conversion generates both language sets and checks the selected language against mod localization keys and dynamic country-name references. Missing keys, incorrect headers or missing UTF-8 BOM prevent successful completion.
3. Choose the output language independently again when exporting edits. The project saves `output_language` with a new revision. Existing projects without this field remain readable.
4. The output `README.txt` uses the chosen language. `package_report.json` records the choice; `localization_verification.json` records coverage. Both existing language directories remain in the mod.
5. Set Victoria 3 to the matching language, enable the mod and start a new campaign. Save from within Victoria 3 to create the `.v3` file.

The converter creates a starting-world mod, not a `.v3` save, and does not change Victoria 3's language setting. The game selects its own localization. Language choices do not alter population, ownership, diplomacy, identity identifiers or conversion rules. User-defined country, character and mod names are not machine-translated.

Validation checks key presence and file format, not translation quality or in-game behavior. Empty surnames and event flavor paragraphs can be intentional and are not considered missing keys.

## Adding translations

Workbench translations live in `tools/converter_locales/en.json`; Chinese source messages provide fallback. `tools/converter_i18n.py` loads catalogs, checks formatting placeholders and resolves game labels. Route new interface text through the instance's `self.tr(...)`. Never translate TAGs, paths, JSON field names or operation identifiers. Use numbered placeholders for complete sentences; translations may reorder them but must preserve their set.

To add a language, update `LANGUAGES`, language-code normalization, the JSON catalog, and the output-language registry and installation guidance in `converter_output_language.py`. Game-content generators currently explicitly produce `english` and `simp_chinese`. A third game language also needs country names, dynamic identities, events, cultures, religions and related generators extended; renaming English localization headers is insufficient.

Use `Message(source_template, *arguments)` for backend messages that appear in the UI, then render with `self.tr(...)`. The value remains a source-language string, preserving JSON and log formats. Do not perform substring replacement on assembled user text. Workers use the optional `error_message` field for the template while keeping the original `error` string; older status files remain readable.

Both release packaging and local code refresh must include `converter_locales`. Run:

```powershell
python -X utf8 -m unittest discover -s tools -p test_converter_i18n.py
python -X utf8 -m unittest discover -s tools -p test_converter_desktop.py
python -X utf8 -m unittest discover -s tools -p test_converter_workbench.py
python -X utf8 -m unittest discover -s tools -p test_prepare_release.py
```
