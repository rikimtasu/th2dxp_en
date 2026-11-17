# v0.7 preview — broad script and boundary fixes

This version rebuilds the patch from the current translation scripts after a
repository-wide structural and prose audit applying **11,179 unique `translated_text`
edits across 466 script files** (`333` targeted prose/quote/continuity fixes across
`147` files and `10,856` missing inter-item space insertions across `410` files).
It retains the v0.5 UI, font, and 75% dialogue-scale changes. Earlier releases remain
available and unchanged.

**This build has not been runtime-tested.** Full bilingual review remains
incomplete. This is a preview, not a finished localization or production acceptance.

## Changes

- **Phase 1 (333 records / 147 files):** Repair corrupted/duplicated fragment splits,
  inverted actor/addressee translations (such as `script_0638.json` and
  `script_0549.json`), swallowed fragments, broken multi-item continuations, stray
  Japanese punctuation/characters in changed records, spelling/hyphenation typos,
  13 `”`-for-apostrophe typos, and unbalanced outer/inner quotes and parentheses.
- **Phase 2 (10,856 records / 410 files):** Insert missing trailing spaces across
  adjacent zero-suffix text fragments that the engine concatenates directly
  (`alpha+alpha`, punctuation+word, opening-quote/digit bounds, `<W#>` wait pauses,
  and inline control endings), while preserving genuine single-word splits, SFX
  elongations, ruby reading carriers, engine controls, and private-use glyphs.
- Retain 75% normal-dialogue size, relative font-size controls, ruby reading
  suppression (`177` readings), and GenInterfaceJP Regular in all four atlases with
  the approved compound punctuation, map-label redraws, and music-panel geometry.

These fixes target structural, continuity, punctuation, and concatenation defects
across `script/`; a full line-by-line bilingual semantic review of all lines remains
incomplete.

## Download and install

The release asset is **`th2dxp_en-v0.7-installer.zip`**. It contains the Windows
installer, this guide and license notices. Python and a separate patch-data
download are not needed. Supply your own lawful PS3 **BLJM60381** dump.

1. Close RPCS3 and preserve personal saves and original backups. Prefer a
   disposable copy of your game dump.
2. Extract the ZIP and run `th2dxp_patch_gui.exe`.
3. Select the game folder or `PS3_GAME/USRDIR`. For any earlier patch, including
   v0.6, use **Restore original → Install**. Keep `USRDIR/.th2dxp-backup`.
4. Start a **fresh ToHeart2 New Game**. Saves that resume a story at a position in
   an older build are not supported. Keep personal saves separately and use new,
   disposable same-build saves.

Allow about **7 GiB** free. The installer never starts RPCS3, downloads a game or
edits saves. Do not replace `EBOOT.BIN` manually or mix files from different builds.

## Packaging and limits

The installer applies an executable diff and archive replacement chunks to your
original files. It supports both previously supported original archive variants
and retains their differing native entries. Complete ELF, DAT, SDAT, extracted
scripts, reference files and saves are not release assets.

Encrypted SDAT bytes depend on the installation path. The installer verifies
the complete decrypted DAT against the expected output for your source variant.
Arbitrary or already-patched archives are not accepted as originals.

Offline checks do not establish GPU rendering, voice/page timing, route
reachability, full-game memory fit or save compatibility. Earlier runtime reports
do not transfer to this build. Manual observations and production acceptance
remain unchanged.

## Offline verification

Reconstruction compared **183,446 text records** across **1,884 scenario payloads**,
checked **115 choice files** and retained **877 untouched payloads** without byte
changes. All **303 unit tests** passed. The new SDAT passed authentication and
complete decryption back to its expected DAT. Both original archive recipes
reconstructed their expected outputs.

| Local rebuilt file | Bytes | SHA-256 |
| --- | ---: | --- |
| `EBOOT.elf` / identical `EBOOT_EN.elf` | 10,749,496 each | `71826c7d9bd0dcb237bdb78323be3600a124b1f91ba96544a0b165a91f8d3fcd` |
| Paired `assets/data.sdat` | 2,202,516,368 | `c2a662b9cd4cb7fc59a44cc8d0a8d69e2a1b2f1deda848dd923cd06cfcc61f29` |

These full game files remain local. Only the patch-only installer ZIP is released.

## Attribution

Keep `NOTICE.md`, the project MIT license, GenInterfaceJP's SIL OFL and the
archive helpers' GPL-3.0 license. Corresponding helper source and local packer
repairs are identified in `NOTICE.md` and `upstreams.json`.

Ittaku remains credited as a translation reference. The user's earlier permission
confirmation is retained; no permission document or independent rights review is
claimed. Original game-content rights remain with their owners.
