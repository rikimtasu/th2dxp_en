# Planned v0.3 — expanded drafts and unified GenInterfaceJP

**Preview candidate.** This release uses the diagnostic under
`build/english-v03-review-fixes-fresh-20261031/`, including Ikuno text, ruby,
auxiliary-font and targeted glossary corrections. The exact pair has **not**
been runtime-tested; the earlier user's testing concerned a different build.

## Selected payload

- Current live translation drafts, including the69 targeted bilingual-review
  corrections across34 files. The assembly checks183,446 editable text rows and
  all1,884 scenario payloads. These are reconstruction counts, not a claim of
  complete bilingual review or complete translated coverage.
- **GenInterfaceJP Regular Japanese and Latin**, with7,261 Japanese replacement
  cells in all four native font atlases. Private icons/unselected glyphs remain
  intact; existing Latin/punctuation mappings are retained.
- **75% normal-dialogue size**; backlog and UI constructors retain their scales.
- Four font replacements plus10 UI TPLs, with separate validated archive recipes
  preserving both previously supported original source variants.
- Self-contained Windows installer: one game-folder selection, no Python or
  separate patch-data download.

The selected decrypted ELF is 10,758,840 bytes, SHA-256:

`8141bd02c3f9745b0fd9ae91f12524ac7d3ff5c0ee2727e7c1793a1902c5ed35`

Its staged SDAT is 2,202,627,776 bytes, SHA-256:

`53e711ec09a2684a4f0a52393d6ad4ff7d068e1aae614e3aa33ccd466b8bf43a`

These complete game files are **not release assets**. The patch-only installer
reproduces the selected ELF exactly and verifies the correct source-specific DAT.
Encrypted SDAT bytes can differ by rebuild path; the installer authenticates the
rebuilt container and verifies its complete decrypted DAT instead.

## Testing and limits

The user's earlier testing report concerned a different build, not this exact
pair. No live rendering, save/reload, route or full-game runtime acceptance is
established for this candidate. The 24-case form remains unfilled; the separate
production gate is unchanged.

Expanded AnotherDays/standalone-story drafts are present, but first-draft insertion
is not editorial completion. Formal exact-text completeness review remains open.
No dedicated voice/page synchronization fix or complete save-compatibility claim
is introduced. This is a preview candidate, not a finished localization.

## Planned install or upgrade

1. Close RPCS3 and preserve personal saves. Prefer a disposable copy of your own
   lawful **BLJM60381** dump.
2. Extract the local `th2dxp_en-v0.3-installer.zip` and run
   **`th2dxp_patch_gui.exe`**.
3. Select the game folder (or `PS3_GAME/USRDIR`). For an existing patch, use
   **Restore original** before **Install**. Preserve `.th2dxp-backup`; modified
   folders without exact original backups require a fresh dump.
4. Start a **fresh New Game**. Changed scenario offsets make older builds'
   execution-position saves unsafe. Use disposable same-build slots only.

The installer does not launch RPCS3 or edit saves. Allow about7GiB free. Neither
this preparation nor the user's release selection deploys anything automatically.

## Attribution and publication boundary

Local packaging contains the installer, this guide, `NOTICE.md`, the MIT license,
GenInterfaceJP's OFL and the archive helpers' GPL-3.0 notice. Corresponding helper
source is identified in `NOTICE.md` and `upstreams.json`, including the separate
packer repair. Preserve those notices and source obligations.

No complete ELF, DAT, SDAT, extracted script, PC reference or save is a release
asset. Original game-content rights remain with their owners. The user confirmed
that permission was obtained; no permission document or independent verification
was supplied. The project records Ittaku as a translation reference.
Older v0.2 packages and the superseded v0.3 diagnostic remain untouched.

## Historical superseded local assets — 2026-10-31

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `dist/v0.3/th2dxp_patch_gui.exe` | 38,165,352 | `16dc6f539456f4fb6cd657dc25bba6469b6069d9377d72f1beef955278e98864` |
| `release/th2dxp_en-v0.3-installer.zip` | 37,900,260 | `548d026e7f322fedac90703ba12aeb7222a81add7517b2870dd57bec59b772b6` |

These assets contain the earlier, superseded pair. All17 embedded patch files match its verified payload. Both source-variant DAT
recipes reconstruct successfully; the frozen executable patch reproduces the
selected ELF exactly. Frozen `--self-test`/`--version`, ZIP CRC/content checks
and275 unit tests pass. No game installation was run for packaging, and no
public upload was performed. The packaged README contains the installation and
scope text above, without this subsequently recorded asset-hash table.
