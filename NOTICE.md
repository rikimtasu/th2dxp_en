# Attribution and redistribution

This unofficial project is not affiliated with AQUAPLUS, Leaf, Sony, RPCS3, VNDB or the Ittaku team. Original ToHeart2 / ToHeart2 AnotherDays / DX PLUS content remains its owners' property. Supply your own lawful game dump. No game or BIOS is downloaded by these tools.

## Requested upstreams

- [hiroshil/TH2DXP_KIT](https://github.com/hiroshil/TH2DXP_KIT), MIT, copyright (c) 2026 Hiroshi. The workflow imports its structured scenario codec and uses DAT/TPL asset tools. Project-owned container decoding corrects omitted continuation scenarios; upstream source is unchanged.
- [minhnhattonthat/fan-translation-template](https://github.com/minhnhattonthat/fan-translation-template), MIT, copyright (c) 2026 minhnhattonthat. Workspace and documentation conventions adapted here.
- [minhnhattonthat/translate-retro-game](https://github.com/minhnhattonthat/translate-retro-game), MIT. Workflow reference only; no claim of PS3 emulator support. Pinned revisions are in `upstreams.json`; complete upstream license texts accompany fetched checkouts.
- [VelocityRa/make_npdata](https://github.com/VelocityRa/make_npdata), written by Hykem, GPL-3.0; pinned large-file fork used as a **separate standalone executable** for SDAT recovery. Source and full GPL license are fetched under `vendor/make_npdata/`. It is not relicensed under this project's MIT license. If distributing that executable, comply with GPL corresponding-source and notice requirements; this workspace does not package it in a release.
- [ripdog/th2xr-portable](https://github.com/ripdog/th2xr-portable), GPL-2.0, referencing Aquaplus's published engine source. Its pinned headless PC parsers are built separately under ignored `work/upstream/` / `work/pc-reference/` for private reference analysis. **`tools/pc_reference_dump.cpp` is GPL-2.0, not MIT**: it links the upstream archive/scenario/bytecode implementation and carries an explicit SPDX notice. The independent Python wrapper remains MIT. Retain the upstream license and comply with corresponding-source requirements if distributing a compiled helper; no helper binary or portable game engine is packaged here. GPL source rights do not grant rights to Ittaku's translation or original game assets.

Project-owned Python tooling and template-derived documentation use the root MIT license; the GPL-2.0 C++ helper above is an explicit exception. That license does **not** grant rights to original game text/assets, Ittaku material, third-party fonts or VNDB data.

## Bundled font

`fonts/GenInterfaceJP-0.8.1/` is the **Gen Interface JP 0.8.1** family (Regular/Display weights), licensed under the **SIL Open Font License 1.1**. The complete `OFL.txt` is bundled alongside it. Copyright 2026 The Gen Interface JP Project Authors (https://github.com/yamatoiizuka/gen-interface-jp); it also carries Inter (2016 The Inter Project Authors) and Adobe Source notices. The project uses the Regular face to generate Latin/bracket cells and redraw selected UI. The OFL permits bundling and redistribution; it does not grant rights to game data.

## Reference and glossary

Ittaku/ittaku-subs' ToHeart2 Xrated PC patch is credited as translation reference. The supplied README credits Conman (translation/project lead), AlphaSixNine, Rem, Velocity7, Kano, editors and other contributors. Consult the supplied README for the full staff list. No redistribution or adaptation permission has been established merely by possessing the patch. Keep recovered/reference text private until rights are resolved.

The merged character dataset credits VNDB and its contributors and carries ODbL 1.0 / DbCL 1.0 notices in `glossary.md` and `glossary/characters.json`; it is not MIT-licensed game content. Project display names are separately identified editorial overrides.

Python dependencies retain their own licenses: pylzma and Pillow; optional native analysis uses Capstone and Unicorn. The work-local [Keystone Engine](https://www.keystone-engine.org) 0.9.2 assembler uses BSD-licensed Python bindings and a GPLv2/commercial dual-licensed core, as recorded in its wheel metadata. Its pinned wheel/hash provenance is under ignored `work/tool-cache/`; no assembler binary is packaged here. The bundled replacement font is documented above under its own OFL.

Project setup/tooling used AI assistance. No claim is made that the scenario has already been translated or manually playtested. Releases, when established, must be patch-only and must disclose provenance and assistance accurately.
