# v0.5 preview — script corrections and UI rendering fixes

This release packages the exact new diagnostic from
`build/ui-rendering-fixes-20261102/`, rebuilt from the current live translation
scripts. **It includes the previously applied translation-script fixes**, not
only the three UI changes. v0.4 and its retained artifacts remain unchanged.

**This new pair has not been runtime-tested.** Earlier player reports do not
transfer to it. Exhaustive bilingual review is incomplete and stopped; the
release is a preview, not a finished localization or production acceptance.

## Changes

- Include the previous glossary-name corrections and the subsequent targeted
  script corrections: damaged apostrophes/name substitutions, required fragment
  separators, lost narration, duplicated dialogue and broken outcome wording.
  Retain the other applied editorial fixes without claiming full bilingual review.
- Match private compound punctuation `!?`, `!!` and `??` to GenInterfaceJP Regular.
  Preserve their codepoints and controls; the three approved codepoints occupy
  six selected native cells. Every other private/unselected font bit is retained.
- Redraw all 135 map labels directly from the selected face at final UI size,
  with full grayscale coverage and matching punctuation. Preserve complete words,
  whole-word wrapping, normal proportions and the original source-bound cells.
- Move the music row panel, selection extent and scrollbar together so the
  complete Composer/Arranger column and artist names no longer occupy the old
  scrollbar area. Keep existing wording, credit roles, font sizes and row spacing.
- Retain 75% normal-dialogue size, relative F10/F20 behavior, contraction spacing,
  177 suppressed English ruby readings, GenInterfaceJP Japanese/Latin in all four
  fonts and auxiliary Latin aliases.

## Exact pair and patch-only distribution

| Selected diagnostic file | Bytes | SHA-256 |
| --- | ---: | --- |
| `EBOOT.elf` / identical `EBOOT_EN.elf` | 10,748,600 each | `cd2bc463c8886397c40a887f99cd422261dfcb85372ee9cc8825aba977422e1b` |
| `assets/data.sdat` | 2,202,516,368 | `25753e9266bbd478b759e729801cf81d47759159e5e9a35472d73ca2fc767d72` |

The release asset is **`th2dxp_en-v0.5-installer.zip`**, containing the
self-contained Windows installer, instructions and notices. No complete ELF,
DAT, SDAT, extracted script, reference text or save is distributed.

The installer carries an executable diff and 14 source-bound archive chunks.
Both supported original archive variants retain their own differing native
entries. Rebuilt decrypted DAT identities are:

| Original archive variant | Rebuilt DAT SHA-256 |
| --- | --- |
| Fresh BLJM60381 (`389bf3ca…` SDAT) | `7f2af008fd55349cf29e4896e3e3ef2fe30a9dcb71ff74c4dd1bf14f71ae886f` |
| Earlier original (`4509a4e9…` SDAT) | `8b540a29bce14009361c6842da07845d8b34acbaaf7c424935362b2ab2fefccd` |

Encrypted SDAT bytes may differ after installation because encryption binds
header hashes to the output path. Complete decrypted content must match the
selected source-specific identity. Arbitrary or already-patched archives are
not accepted as originals.

## Install or upgrade

1. Close RPCS3 and preserve personal saves and original backups. Prefer a
   disposable copy of your own lawful **BLJM60381** dump.
2. Download and extract `th2dxp_en-v0.5-installer.zip` from the GitHub v0.5
   release. Run `th2dxp_patch_gui.exe`; no Python or separate patch data is needed.
3. Select the game folder or `PS3_GAME/USRDIR`. When upgrading **any earlier
   patch, including v0.4**, use **Restore original → Install**. Preserve
   `USRDIR/.th2dxp-backup`; unknown modified inputs require a fresh dump.
4. Start a **fresh New Game**. Older execution-position saves are not supported;
   use only new disposable same-build saves and retain personal saves separately.

Allow about **7 GiB** free. The installer never starts RPCS3, downloads a game or
edits saves. Do not replace `EBOOT.BIN` manually or mix archives and ELFs.

## Verification and remaining limits

Offline staging re-extracted 183,446 text records across 1,884 scenario payloads,
checked 115 choice companions and retained 877 untouched payloads byte-identically.
Actual packed compound/map pixels and native-size map previews were inspected.
Encoded music replay covered all 51 records and 10 selected/locked/scroll cases;
449 code/data spans and all 7,402 main metric pairs bind that bounded replay to
the final growth image. Full output SDAT authentication and complete decrypt/DAT
equality passed. Both patch-data source recipes reconstruct their pinned outputs.

These are software proofs, not GPU rendering, controller-driven transitions,
voice/page timing, route reachability, full-game memory fit or save compatibility.
The exact-build manual form remains unfilled; no old observations are copied.

## Attribution

Preserve `NOTICE.md`, the project MIT license, GenInterfaceJP SIL OFL and the
archive helpers' GPL-3.0 license. Corresponding helper source and local packer
repairs are identified in `NOTICE.md` and `upstreams.json`.

Ittaku remains credited as a translation reference; reference independence is
not claimed. The user previously confirmed permission for translation/game-derived
patch data, without providing a permission document or independent rights review.
Original game-content rights remain with their owners.
