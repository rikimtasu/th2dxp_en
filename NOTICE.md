# Attribution and redistribution

This unofficial project is not affiliated with AQUAPLUS, Leaf, Sony, RPCS3, VNDB or the Ittaku team. Original ToHeart2 / ToHeart2 AnotherDays / DX PLUS content remains its owners' property. Supply your own lawful game dump. No game or BIOS is downloaded by these tools.

## Requested upstreams

- [hiroshil/TH2DXP_KIT](https://github.com/hiroshil/TH2DXP_KIT), MIT, copyright (c) 2026 Hiroshi. The workflow imports its structured scenario codec and uses DAT/TPL asset tools. Project-owned container decoding corrects omitted continuation scenarios; upstream source is unchanged.
- [minhnhattonthat/fan-translation-template](https://github.com/minhnhattonthat/fan-translation-template), MIT, copyright (c) 2026 minhnhattonthat. Workspace and documentation conventions adapted here.
- [minhnhattonthat/translate-retro-game](https://github.com/minhnhattonthat/translate-retro-game), MIT. Workflow reference only; no claim of PS3 emulator support. Pinned revisions are in `upstreams.json`; complete upstream license texts accompany fetched checkouts.
- [VelocityRa/make_npdata](https://github.com/VelocityRa/make_npdata), written by Hykem, GPL-3.0; pinned large-file fork used as **two standalone executables**: `make_npdata` for SDAT decryption and a repaired `make_npdata-pack` for re-encryption and authentication of the rebuilt archive. Source and the full GPL-3.0 text are under `vendor/make_npdata/`. They remain GPL-3.0, are **not** relicensed under this project's MIT license, and are now embedded in the installer (`th2dxp_patch_gui.exe`); the archive `licenses/make_npdata-GPL-3.0.txt` carries the license text and NOTICE.md names the corresponding source.
- [ripdog/th2xr-portable](https://github.com/ripdog/th2xr-portable), GPL-2.0, referencing Aquaplus's published engine source. Its pinned headless PC parsers are built separately under ignored `work/upstream/` / `work/pc-reference/` for private reference analysis. **`tools/pc_reference_dump.cpp` is GPL-2.0, not MIT**: it links the upstream archive/scenario/bytecode implementation and carries an explicit SPDX notice. The independent Python wrapper remains MIT. Retain the upstream license and comply with corresponding-source requirements if distributing a compiled helper; no helper binary or portable game engine is packaged here. GPL source rights do not grant rights to Ittaku's translation or original game assets.

Project-owned Python tooling and template-derived documentation use the root MIT license; the GPL-2.0 C++ helper and the two bundled GPL-3.0 `make_npdata` executables above are explicit exceptions. That license does **not** grant rights to original game text/assets, Ittaku material, third-party fonts or VNDB data.

## Bundled utilities in the installer

`th2dxp_patch_gui.exe` is a single-file program. Besides this project's own Python code (MIT) it contains:

- `make_npdata` and `make_npdata-pack`, GPL-3.0, from [VelocityRa/make_npdata](https://github.com/VelocityRa/make_npdata). They are invoked as **separate child processes** with pinned SHA-256 (`662fd552…f57fac` and `81c2cd3a…b510b7`); the installer refuses any other build. They are not linked with, and are not derived from, this project's code. **Corresponding source** is the upstream repository at the revision pinned in `upstreams.json` together with the local packer repair (`tools/sdat_pack.c`, `tools/build_sdat_tool.py`); both are published in this repository and can be rebuilt with the documented commands. The GPL-3.0 text is bundled as `licenses/make_npdata-GPL-3.0.txt`. Neither the upstream author nor this project endorses anything beyond use of that software.
- The **single BLJM60381 application keyset** required to decrypt that game's own `EBOOT.BIN`. Those constants are Sony's platform secrets; they were taken from publicly documented PS3 research material ([RPCS3](https://github.com/RPCS3/rpcs3), GPL-2.0, `Crypto/key_vault.cpp`) and carry no Sony code. They are used only to decrypt the user's own lawfully obtained copy, in place, so the patch can be applied without distributing a decrypted executable. No game data, no decrypted executable and no keyed content of any other title is redistributed.
- No game data. The program ships a hash-pinned data patch (an executable diff plus pre-compressed archive chunks) that it applies to the copy you supply; the released archive contains no `.elf`, `.dat`, `.sdat`, save or font-atlas file.

## Bundled font

`fonts/GenInterfaceJP-0.8.1/` is the **Gen Interface JP 0.8.1** family (Regular/Display weights), licensed under the **SIL Open Font License 1.1**. The complete `OFL.txt` is bundled alongside it. Copyright 2026 The Gen Interface JP Project Authors (https://github.com/yamatoiizuka/gen-interface-jp); it also carries Inter (2016 The Inter Project Authors) and Adobe Source notices. The project uses the Regular face to generate Latin/bracket cells and redraw selected UI. The OFL permits bundling and redistribution; it does not grant rights to game data.

## Reference and glossary

Ittaku/ittaku-subs' ToHeart2 Xrated PC patch is credited as translation reference. The supplied README credits Conman (translation/project lead), AlphaSixNine, Rem, Velocity7, Kano, editors and other contributors. Consult the supplied README for the full staff list. No redistribution or adaptation permission has been established merely by possessing the patch. Keep recovered/reference text private until rights are resolved.

The merged character dataset credits VNDB and its contributors and carries ODbL 1.0 / DbCL 1.0 notices in `glossary.md` and `glossary/characters.json`; it is not MIT-licensed game content. Project display names are separately identified editorial overrides.

Python dependencies retain their own licenses: pylzma and Pillow; optional native analysis uses Capstone and Unicorn. The work-local [Keystone Engine](https://www.keystone-engine.org) 0.9.2 assembler uses BSD-licensed Python bindings and a GPLv2/commercial dual-licensed core, as recorded in its wheel metadata. Its pinned wheel/hash provenance is under ignored `work/tool-cache/`; no assembler binary is packaged here. The bundled replacement font is documented above under its own OFL.

Project setup, tooling and translation/editorial work used AI assistance. The v0.2 gameplay payload received limited player testing with three supplied screenshots; this is not a full bilingual review or full-game runtime/save/route acceptance. Releases are patch-only, preserve the notices above and do not grant rights to original game content or PC-reference translations. The v0.2 QC pass introduces no PC-reference import; recovered Ittaku material remains private.
