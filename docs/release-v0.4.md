# v0.4 preview — tested diagnostic and retained editorial corrections

This release packages the exact selected diagnostic from
`build/english-retained-review-fresh-20261101/`. The user reports **“current build
tested”** and requests its publication as v0.4. No per-case results, emulator
version, scenes or screenshots accompanied that report. Full bilingual review,
full-game runtime acceptance and the separate production gate remain incomplete.

## Changes

- Correct contraction spacing by staging lexical English apostrophes through the
  native proportional path, without changing standalone quotation marks or controls.
- Keep normal-dialogue font-size controls relative to the staged **75%** size:
  returning to normal no longer resets that context to 100%. Intentional smaller
  spans remain smaller; other contexts keep source font-size-control behavior.
- Remove **177 English ruby readings** using zero-length native literals, not
  invisible spacing carriers. Retain the surrounding controls and reviewed meaning
  in the base wording.
- Apply **4,754 additional editorial record edits across 124 files** from the
  retained findings: fragment joins, source-bound names/honorifics, grammar,
  quotation boundaries and missing or misplaced meaning. This is not an exhaustive
  bilingual pass; unchanged/content-limited dispositions are not completeness credit.
- Retain expanded base-game/AnotherDays/separate-story drafts, GenInterfaceJP
  Regular Japanese and Latin in all four native font atlases, auxiliary-font
  aliases and the existing English UI. Private icons remain intact.

## Selected pair and patch-only packaging

| Selected diagnostic file | Bytes | SHA-256 |
| --- | ---: | --- |
| `EBOOT.elf` | 10,748,216 | `53d1b3be345915b2fe8c4e41cb7137e49add6923d21acf94f02f5aad0c406d54` |
| `assets/data.sdat` | 2,202,627,776 | `646e64f96503060ffe17fdeba485b89d3554f6c6f6de66cc4c65e3ecc7a650ff` |

Complete game files are **not release assets**. The self-contained Windows
installer carries an executable diff and source-bound archive replacement chunks.
It reproduces the selected ELF exactly and verifies the complete source-specific
DAT. Re-encryption binds SDAT header hashes to the output path, so rebuilt SDAT
bytes need not equal the diagnostic container's hash; decrypted content must match.

The selected source variant's output DAT SHA-256 is
`1fccccd6045bb9d1291145a30c9cb6f0598e0f62185d9990db3d56e231f02e5a`.
The other supported original source retains its own differing native entries and
its separately pinned output DAT identity. Arbitrary or already-modified archives
are not accepted as original inputs.

## Install or upgrade

1. Close RPCS3 and preserve personal saves. Prefer a disposable copy of your own
   lawful **BLJM60381** dump.
2. Download and extract **`th2dxp_en-v0.4-installer.zip`** from the GitHub v0.4
   release. Run **`th2dxp_patch_gui.exe`**; no Python or separate patch-data download
   is required.
3. Select the game folder or `PS3_GAME/USRDIR`. When upgrading, use **Restore
   original** before **Install**. Preserve `USRDIR/.th2dxp-backup`; a modified folder
   without exact original backups requires a fresh dump.
4. Start a **fresh New Game**. Changed scenario/checkpoint offsets make older
   builds' execution-position saves unsafe. Preserve them and use new disposable
   same-build slots only.

Allow about **7 GiB** free. The installer never starts RPCS3, downloads a game or
edits saves. Do not replace `EBOOT.BIN` by hand or mix an ELF with another pair's
archive. Older releases and diagnostics remain preserved.

## Verification and limitations

Diagnostic staging re-extracted **183,446 text records across 1,884 scenario
payloads**, verified 115 choice companions and retained 877 untouched payloads
byte-identically. Output archive authentication and complete DAT decrypt equality
passed. Native contraction and encoded font-size-control replays passed; these are
software/native proofs, not RSX/GPU rendering or full story execution.

The user's general test confirmation does not fill the 24 general or four targeted
manual observations. It does not establish route reachability, full-game memory
fit, voice/page synchronization or cross-build save compatibility. Whole-script
bilingual review remains deferred. This remains a **preview**, not a finished
localization.

## Attribution and publication boundary

The package includes this guide, `NOTICE.md`, the project MIT license,
GenInterfaceJP's SIL OFL and the archive helpers' GPL-3.0 license. Corresponding
helper source is identified in `NOTICE.md` and `upstreams.json`, including the
published packer repair; preserve those notices and source obligations.

Ittaku is retained as a translation reference; reference independence is not
claimed. The user previously confirmed permission for translation and game-derived
patch data; no permission document or independent rights verification was supplied.
Original game-content rights remain with their owners. No complete ELF, DAT, SDAT,
extracted script, reference material or save is included as a release asset.
