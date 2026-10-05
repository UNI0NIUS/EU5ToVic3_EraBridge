# Original third-party licenses

[简体中文](README.md) · **English**

`rakaly-0.12.7/LICENSE.txt` preserves the [original librakaly v0.12.7 license](https://github.com/rakaly/librakaly/blob/v0.12.7/LICENSE.txt) exactly as downloaded. Its SHA-256 is `91276db973f25602d1aa43491f59cbc84cb88e6f151e1d0cc82a755563ce0195`.

The candidate receives this version's license only when its Rakaly DLL matches the 0.12.7 hash recorded in `tools/toolchain-lock.json`. `dependencies/inventory.json` records provenance, archive hashes and notice hashes for 101 packages from Cargo.lock, including build and optional dependencies; that does not mean every package is statically linked. `review_required` marks missing individual license declarations or notices.

The pdx-tools `eu5save`, `vic3save`, `bumpalo-serde` and derive-macro dependencies originate from AGPL repositories and retain the corresponding root license. The maintainer has confirmed authorization to redistribute Rakaly in this release. The wrapper's MIT license does not replace dependency licenses; see [licensing](../docs/LICENSING.en.md). This directory is not complete corresponding source and grants no additional downstream license.

The preparation script collects Python runtime licenses from matched package caches and the runtime installation; machine-local cache directories are not committed. See [release preparation](../docs/RELEASING.en.md).

Supplementary runtime attribution and selected licensing options appear in [THIRD_PARTY_NOTICES.en.md](THIRD_PARTY_NOTICES.en.md).

`microsoft-community-2022/LICENSE.docx` is Microsoft's original Community 2022 license. `LICENSE.txt` is a convenience text extraction; the original controls. Windows packages also retain the UCRT SDK license. First-launch third-party terms are in [END_USER_TERMS.txt](END_USER_TERMS.txt), with separate Chinese and English sections.
