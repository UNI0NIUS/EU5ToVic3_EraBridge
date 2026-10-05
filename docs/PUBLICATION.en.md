# Public materials and validation scope (0.12.2)

[简体中文](PUBLICATION.md) · **English** · [Documentation](README.en.md)

`v0.12.2-beta.3` provides source and a Windows x64 portable package for community testing. The earlier `beta.1` source-only tag is preserved. The dated records below distinguish historical checks from later verification.

## Included materials

- Upstream Git history, original copyright notices, licenses and submodule references.
- C++ save-import changes, Python conversion/workbench tools and tests.
- Conversion settings, mappings and their research basis.
- EraBridge icons, launchers and the necessary usage/build documentation.

Public documentation covers usage, technical rules, architecture, builds and releases; see the [documentation index](README.en.md). Development conversations, personal installation records and progress logs are not published. Some settings in `config/personal/` belong to older campaigns: check their field scope before reuse.

## Excluded materials

Game installations, player saves, baseline saves, complete generated rules, extracted game assets, candidate mods, project edit records, logs, caches and compiler toolchains are excluded. Portable ZIPs are Release assets, not source-repository files. Personal installation scripts remain local.

## Historical validation

On 2026-10-03, `tools/Build-Personal.ps1` completed the C++ build and CTest on the Windows development machine: 27 suites and 121 tests. After first-run initialization and acceptance tools were added, all 530 Python tests passed using Python 3.13.9, NumPy 2.3.1 and Pillow 12.0.0.

A candidate runtime was checked in a separate path containing Chinese characters and spaces. With external Python settings cleared and PATH restricted to Windows system directories, NumPy calculations, Pillow image reading/writing, Rakaly loading, and Tk workbench creation/closure passed. Default game and candidate paths were empty. This was a relocation check on the development machine; full acceptance on a machine without development tools remained pending.

Candidate `66a99fe` used bundled Python for a fresh run from local game installations, a vanilla V3 starting save and an original 1337 save. Rule initialization, complete conversion, static checks, population readback, project save/reopen and export readback passed, with consistent data for 3,292 regions. No previous conversion intermediates were reused. This result came from the Windows development machine, not an independent test machine.

After rerunning final generation and validation on that fresh conversion, V3 1.13.11 advanced to 1836.1.7. Opening and first-week saves were read back. Both sides of all five opening wars matched the source records. Law retention, religion color formatting, localization-key conflicts and repeated HRE log errors were fixed. Later participants appeared during the first week; they are not treated as opening-war mappings.

In-game acceptance did not fully pass: the engine still reduced some buildings exceeding actual resource capacity, and vanilla scripts such as dynamic state names still reported invalid scopes or missing text. Resource-capacity calculations need to agree with engine readback. Unit tests or successful first-week advancement cannot substitute for those checks. This review reused the economic intermediates from the earlier fresh conversion; it was not a rerun of every conversion stage after the fixes.

The 1337, 1780 and 1787 samples also have historical conversion or partial-check records. These do not establish that a clean clone, arbitrary saves or long campaigns work. Portable packages include dependency licenses and notices; disclosed compatibility limits remain open for community testing.

## beta.2 release materials

Usage documentation describes software behavior; technical documentation preserves rules, conditions and validation limits. Historical debugging evidence is not presented as current-version acceptance. Upstream licenses and third-party originals are retained.

`v0.12.2-beta.2` rebuilt the importer and launcher with Visual Studio Community 2022 17.14 and Windows SDK 10.0.26100.0. C++ tests and 532 Python tests passed; eight packaging tests passed separately after adding source-commit information to the manifest. The Windows package includes the official Visual C++ runtime, Python and dependencies. First launch requires acceptance of third-party component terms. The acceptance tool explicitly keeps `clean_machine_verified: false`; development-machine checks are not independent-environment certification.

The beta.2 portable runtime also completed fresh rule initialization, native import, full conversion, project save/reopen and export readback from an original 1337 save in a path containing Chinese characters and spaces. Data for 3,292 regions agreed. It used bundled Python 3.13.9, NumPy 2.3.1, Pillow 12.0.0 and Tk 8.6 with external Python settings cleared. This ran on the Windows development machine; that round did not repeat first-week or long-campaign gameplay tests.

## beta.3 release and follow-up checks (2026-10-04)

The isolated release source passed 133 targeted Python tests: 116 workbench/language, six initialization, eight packaging and three release-integrity tests. The launcher was rebuilt. The unchanged C++ importer reused the released beta.2 native binary after hash verification. Bundled-runtime checks covered dependency isolation, the initialization dialog and Chinese/English switching in a path containing Chinese characters and spaces.

The actual GitHub download was downloaded again and verified against `SHA256SUMS.txt`. Its SHA-256 was `9aeefb91f4581bf3581095479240e2861494df9162d940e97d5482eb5f103726`. All 2,653 manifest payload files matched the downloaded package and local publishing copy. The audit also compared 225 documentation, license and metadata files against the release-tag snapshot. These counts describe that dated release audit; subsequently updated documentation on `master` can differ from the immutable tag and ZIP.

A randomly selected 1338 KNI binary save failed in the native importer with `Unknown EU5 binary tokens: import refused`. A diagnostic copy with compact empty strings normalized still failed. The unsupported field has not been identified, and this save is not claimed as supported. The original was unchanged.

A vanilla 1337.4.1 CHI (Yuan) control save completed fresh rule preparation, full conversion, project save/reopen and Chinese/English export readback using the downloaded release on the development machine. Results agreed on 3,292 regions, 40,717 provinces, 394,557,661 people and 4,191 building levels. Each language check covered 22,748 localization keys. The two exported mods had 1,056 identical files; only the mod `id` in `.metadata/metadata.json` differed, as expected for different export directories. The source save was unchanged. The final comparison allows those expected independent mod IDs; an earlier overly strict comparison was a test-harness issue, not a conversion failure.

This follow-up did not load the exported mods in the game. English in-game appearance, independent Windows environments and long campaigns remain unverified. Existing resource-capacity and vanilla-script limitations still apply.

Preparation scripts produce a separate directory, per-file manifest, SHA-256 values and provenance report. See [release preparation](RELEASING.en.md), [beta.3 notes](releases/v0.12.2-beta.3.en.md) and [issue/save submission](SUPPORT.en.md).
