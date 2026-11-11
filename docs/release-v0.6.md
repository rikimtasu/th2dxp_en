# v0.6 preview — translation quality fixes

This version rebuilds the patch from the current translation scripts, including
**25 text-record edits across 17 files** from the November 11 review. It retains
the v0.5 UI and font changes. Earlier releases remain available and unchanged.

**This build has not been runtime-tested.** Full bilingual review remains
incomplete. This is a preview, not a finished localization or production acceptance.

## Changes

- Repair confirmed word separators and broken continuations. Restore the omitted
  self-proclaimed alien reference and avoid repeated or misplaced meaning.
- Correct the subject in the inspector comparison and restore a serious tone of
  voice where the translation had added a facial expression.
- Restore two source-present honorifics and revise confirmed unnatural wording,
  including literal self-reference and the description of recalled facts.
- Resolve all five retained wording questions: correct three descriptions and
  retain two Nanako readings supported by the wider Japanese context. Preserve
  source-present terms without guessing an exact age from school or appearance.

The patch retains 75% normal-dialogue size, relative font-size controls and the
existing English ruby suppression. GenInterfaceJP remains the Japanese/Latin
font in all four atlases, with the previously approved compound punctuation,
map-label redraws and music-panel geometry.

These are targeted corrections. Unconfirmed boundary candidates were not
bulk-applied, and the review does not establish whole-script translation completeness.

## Download and install

The release asset is **`th2dxp_en-v0.6-installer.zip`**. It contains the Windows
installer, this guide and license notices. Python and a separate patch-data
download are not needed. Supply your own lawful PS3 **BLJM60381** dump.

1. Close RPCS3 and preserve personal saves and original backups. Prefer a
   disposable copy of your game dump.
2. Extract the ZIP and run `th2dxp_patch_gui.exe`.
3. Select the game folder or `PS3_GAME/USRDIR`. For any earlier patch, including
   v0.5, use **Restore original → Install**. Keep `USRDIR/.th2dxp-backup`.
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
| `EBOOT.elf` / identical `EBOOT_EN.elf` | 10,748,536 each | `e2d628fb8bcc6a1eba5b7967725048f53f1cfed62d36b43f51581615c4fdb84d` |
| Paired `assets/data.sdat` | 2,202,516,368 | `2907821bb17e820de78684d435c4e98432913dfef5f95dfa12860bb9cd278481` |

These full game files remain local. Only the patch-only installer ZIP is released.

## Attribution

Keep `NOTICE.md`, the project MIT license, GenInterfaceJP's SIL OFL and the
archive helpers' GPL-3.0 license. Corresponding helper source and local packer
repairs are identified in `NOTICE.md` and `upstreams.json`.

Ittaku remains credited as a translation reference. The user's earlier permission
confirmation is retained; no permission document or independent rights review is
claimed. Original game-content rights remain with their owners.
