# Runtime attribution and licensing notes

[简体中文](THIRD_PARTY_NOTICES.md) · **English**

EraBridge's Windows portable package uses Python, NumPy, Pillow, Tcl/Tk and their runtime dependencies. `licenses/runtime-inventory.json` records component versions and file provenance. Original copyright and license texts remain in their respective directories. These notices do not replace those licenses or their applicable terms.

This software is based in part on the work of the FreeType Team and uses the FreeType font engine. The package selects the FTL licensing option; the original text is at `licenses/runtime/freetype-*/docs/FTL.TXT`. Project website: [FreeType](https://freetype.org/).

This software is based in part on the work of the Independent JPEG Group.

The XZ inventory may list several licenses. The bundled liblzma uses 0BSD; licenses for XZ auxiliary scripts must not be applied automatically to that library. Zstandard uses its BSD licensing option. Actual binaries and original component documentation determine the scope.

The Rakaly wrapper, its parser dependencies and Microsoft runtimes each retain their applicable terms. `licenses/rakaly-0.12.7/dependencies/` collects lock-file dependency notices, not complete corresponding source. See [licensing](../docs/LICENSING.en.md) and [release preparation](../docs/RELEASING.en.md).
