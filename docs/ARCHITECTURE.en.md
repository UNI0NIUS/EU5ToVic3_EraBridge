# Architecture

[简体中文](ARCHITECTURE.md) · **English** · [Documentation](README.en.md)

EraBridge's desktop application combines a C++ save importer, a Python conversion pipeline and a Tk interface. C++ reads and audits the source save; Python generates the complete target mod in stages. Parts of the upstream C++ target-world implementation remain placeholders, so that executable alone is not the desktop application's full conversion entry point.

## Module responsibilities

| Entry point | Responsibility |
|---|---|
| `EU5ToVic3/` | Source-save parsing, import auditing and native converter infrastructure |
| `tools/converter_desktop.py` | Tk windows, map interaction, task status and error display |
| `tools/converter_controller.py` | Connects the interface to projects, conversion, previews and exports |
| `tools/converter_pipeline.py` | Isolated run directories, subprocesses, stage scheduling, cancellation and final checks |
| `tools/converter_source_*.py` | Geography, population, politics, economy and complete candidate construction |
| `tools/converter_project.py` | Project data, file hashes and persistence helpers |
| `tools/build_converter_rules.py` | Freezes mappings, configuration, identity resources and provenance hashes |
| `tools/package_converter_app.py` | Collects the local runtime, native executable, code and rules |
| `tools/prepare_release.py` | Creates separate candidates and release-verification materials |

`config/personal/` is a retained directory name containing both general rules and some older campaign configurations. Check each field's scope; the entire directory is not a default configuration for arbitrary saves.

## Conversion flow

1. Validate the save, EU5 installation, Victoria 3 `game` directory and rule manifest; create a separate run directory.
2. Check rule-file, game-map and baseline-save hashes. The native importer parses the input and produces an audit.
3. Extract countries, population, cultures, religions, literacy, politics, economy, armies, navies and wars from that same source save.
4. Build target geography and countries, allocate population and identities, then generate laws, technology, economy, military forces, supply chains and opening wars.
5. Read the output back and check population, territory, references and startup scripts. Successful runs produce a completed package and hash manifest.

Each run's rule snapshot and input hashes provide traceability. Failures retain their stage, error and logs; incomplete directories are not presented as successful results. Cancellation terminates only that task's process and its children.

## Data boundaries

| Data | Included in source distribution? | Use |
|---|---|---|
| Conversion code, configuration, application icons | Yes | Maintained in version control |
| Installed games, player saves, baseline saves | No | Supplied locally by the user |
| Complete generated rules and game-derived resources | No | Prepared locally; provenance is checked separately before distribution |
| Conversion runs, editing projects, exported mods, logs | No | Stored in the workspace, separated by run or project |

Rules provide geographic correspondences, identity mappings and explicit policies. Ownership and population come from the current save. Country IDs, population history and territorial history from an older campaign must not become defaults for a new save. Shared resource updates operate on identity keys and must not overwrite campaign event translations.

## Editing and export

The workbench loads a verified candidate and stores parameters and operations in a project. Preview, confirmation and export use the same operation logic; undo restores the corresponding revision. Input-fingerprint or revision mismatches require reloading so that old decisions are not applied to changed data.

Export creates a separate directory and rechecks population, provinces, state membership, capitals, buildings and related references. Territorial transfers and mergers reconcile diplomacy and wars according to explicit rules, showing the effects before confirmation. See the [workbench guide](CONVERTER_WORKBENCH.en.md).

## Validation and extensions

New conversion rules should describe their input evidence, applicability, fallback behavior and unrepresentable features. Changes to population, territory, identities or buildings must demonstrate conservation or explain the reason for each change. Unknown information must not be treated as a satisfied condition.

Unit tests validate deterministic rules; readback checks validate output consistency; in-game tests establish how the engine behaves. See the [validation record](PUBLICATION.en.md), [build instructions](BUILDING.en.md) and [release procedure](RELEASING.en.md).
