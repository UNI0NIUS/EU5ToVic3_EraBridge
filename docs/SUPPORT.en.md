# Reporting issues and submitting saves

[简体中文](SUPPORT.md) · **English** · [Documentation](README.en.md)

Start with a report in [this fork's Issues](https://github.com/UNI0NIUS/EU5ToVic3_EraBridge/issues/new?template=bug_report_en.md), including the behavior, reproduction steps and relevant logs. An initial public report does not require a complete save. If reproduction needs input files, supply the smallest set that reproduces the problem.

## What to report

- EraBridge version or commit, download source and Windows version.
- EU5 and Victoria 3 versions, source-save date and player country.
- Whether mods were enabled; list names, versions and load order.
- Workbench language, selected output language and V3 game language.
- Stage: rule preparation, import, conversion, map editing, project saving, export or gameplay.
- Steps, expected/actual results and the complete error message. For gameplay, include the date, country, state or building. For localization, include displayed text or script keys.

Check the [validation scope](PUBLICATION.en.md) and [release notes](releases/v0.12.2-beta.3.en.md). Some binary saves fail with `Unknown EU5 binary tokens: import refused`. For native-import failures, retain the original `.eu5`; do not edit or re-encode it and present that copy as the original.

## Default paths and logs

When a release is launched through `EU5Converter.exe`, these paths are relative to the extracted application folder, not the game installation:

| Material | Path |
|---|---|
| Initial complete conversion | `data/runs/<timestamp-id>/complete/` |
| Subsequent workbench export | `data/exports/<timestamp-id>/` |
| Saved projects | `data/projects/` |
| Conversion progress/errors | `data/runs/<timestamp-id>/conversion.log` and `status.json` |
| Native import log | `log.txt` in the corresponding run directory |
| Workbench errors | `data/logs/desktop-*.log` |
| Startup failure | `data/startup.log` |

Use **Open output directory** to find the latest output. In an exported package, `localization_verification.json` records language checks; `package_report.json` records input fingerprints, output hashes and validation results. Source-mode defaults use `.local/converter/`; an explicit `--workspace` overrides the root. Exports do not default to Victoria 3's `mod` directory; see the [workbench guide](CONVERTER_WORKBENCH.en.md) for installation.

Only the relevant stage's logs or error excerpts are needed. Logs, projects and reports may contain usernames, private paths and input data. Remove unrelated personal information from shared copies while retaining error context. Do not upload the entire `data/` folder, acceptance directory or game installation.

## Supplying a save for reproduction

1. Keep the original and put a reproducing `.eu5` in a ZIP. Include a short note with software/game versions, save date, country, mod load order and steps. Preserve the save's original bytes inside the ZIP; compression does not repair or change the input.
2. Drag a ZIP of up to 25 MB into the Issue body or a comment. For larger files, share a cloud-storage download link with the filename, size, access instructions and expiry. GitHub supports ZIPs and limits ordinary attachments to 25 MB; public-repository attachments are accessible without signing in. See [GitHub's attachment documentation](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files).
3. Optionally include the original save's or ZIP's SHA-256, clearly identifying which file it describes, so the download can be verified:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'D:\Report\sample.eu5'
```

Do not upload a private save to a public Issue or treat a publicly posted password-protected link as a private channel. Report the problem first, then agree with the maintainer on a suitable private transfer method and retention period. There is currently no dedicated private-save upload endpoint. Confirm that you are comfortable sharing the save's contents with the recipient. Exclude game installations, complete Workshop packages, account credentials and unrelated files.

Normally start with the original EU5 save. If the problem occurs only after running V3, identify the exported mod, campaign date and reproduction steps, then provide the `.v3` and related output if needed. A `.v3` alone may not reproduce a conversion-stage problem. Keep original files and local backups; the maintainer may request further relevant information.
