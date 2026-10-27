# Original PS3 text for LinguaGacha

The private export uses LinguaGacha's [Message-JSON format](https://github.com/neavo/LinguaGacha/wiki/SupportedFileFormatEN): an ordered array of objects with string `name` and `message` fields. Messages come only from the immutable original Japanese PS3 baselines, not English drafts or PC-reference translations.

## Which folder to import

| Input folder | JSON files | Native text items |
| --- | ---: | ---: |
| `work/linguagacha-original/base-game/gt_input/` | 885 | 102,062 |
| `work/linguagacha-original/all-original/gt_input/` | 1,122 | 183,446 |

**Use the base-game folder first.** It contains101,829 message fragments and233 native choice captions. The complete set contains182,111 message fragments and1,335 choices, including AnotherDays, separately owned stories and other packaged programs. These sets overlap: do not import both into one LinguaGacha project. Membership describes native normal-title ownership, not proof that each individual route executes.

Start with `base-game/gt_input/010301000.json` (the opening,402 rows). Files use native scenario names; `_choices.json` files contain native choice captions. Import only `gt_input`, not the export root or `metadata`.

## Translation contract

- JSON is UTF-8 without BOM. Every native editable text item has exactly one row, including unfinished fragments, duplicates and original blank carriers. There are6,237 blank carriers in the base set and38,054 in the complete set; they are not missing translations.
- Every `name` is `""` because native speaker bindings have not been verified. This means unresolved speaker, **not** asserted narration. Keep these fields empty; do not infer speakers or enable translated-name output.
- Preserve filenames, row counts and row order. Do not merge, split, deduplicate, trim source whitespace or remove/fill blank carriers. Each translation must preserve the meaning of that same native fragment, even when unfinished.
- Preserve ordered inline controls/name substitutions such as `\k`, `\n`, `<S10>`, `*nnk`, and private-use glyphs. Do not introduce literal newlines or other control characters into message strings. Eventual native output must strictly round-trip through CP932; JSON validity alone does not ensure this.
- End-of-item `control_suffix` values are deliberately outside translatable messages. `metadata/records/<native filename>.json` maps every row to `script:unit:item`, its exact suffix and protected controls. Do not translate or import these sidecars.
- Save translated files under the matching subset's `gt_output/`, keeping filenames and row order; do not overwrite `gt_input/`. Pure `name`/`message` arrays cannot reliably detect equal-count translated-row reordering.

The exporter does not automatically import translations into `script/`. `restore_units` is an in-memory validation helper, not a translation-import CLI. Returned output still needs source/fragment review and native validation before any separately authorized insertion. Runtime/production acceptance requirements remain unchanged.

## Reproducing the export

This workspace's export already exists. **Do not rerun the default command into it.** On a prepared workspace with the original source, immutable message/choice baselines and complete source-bound membership report:

```console
python -X utf8 tools/linguagacha_export.py
```

To create a distinct export without replacing existing work:

```console
python -X utf8 tools/linguagacha_export.py --output work/linguagacha-original-new
```

Outputs must be a new directory beneath `work/`; existing destinations are refused. No source, baseline, editable script, build, installed game or save is changed. Proprietary exports remain private/ignored; this is not redistribution permission.

## Patching a test installation

For v0.1 the end-user path is **`dist/th2dxp_patch_gui.exe`**, a single windowed program that needs no Python, no decrypted `EBOOT.elf` and no build directory. Point it at the folder you installed in RPCS3 (the one containing `PS3_GAME`) and press *Install*: it decrypts that folder's own `EBOOT.BIN` and `data.sdat`, applies the hash-pinned patch data it carries, verifies both results and only then writes them. The **user** runs it; it never launches RPCS3, never writes saves, and never deletes a backup. `--self-test` (exit code 0) checks that the program found its own patch data and both pinned archive helpers; `--version` prints the version.

`tools/patch_game.py` installs one **local** verified build pair into a test `PS3_GAME/USRDIR`, for development. `dist/th2dxp_patch.exe` is that tool frozen with PyInstaller:

```console
python -X utf8 tools/patch_game.py status
python -X utf8 tools/patch_game.py apply --build build/english-v0.1          # dry run
python -X utf8 tools/patch_game.py apply --build build/english-v0.1 --apply  # write
python -X utf8 tools/patch_game.py restore --apply
```

- The target is `--game-dir <path>/PS3_GAME/USRDIR`, or `game_usrdir` if you have added that key to `project.json`; no machine-specific default is committed.
- `apply` refuses an ELF whose SHA-256 differs from its `EBOOT.report.json`, refuses an archive that does not match the pair declared by that report, and refuses to run while `rpcs3.exe` is active.
- The patched executable is written **as `EBOOT.BIN`**, which is the form RPCS3 boots directly, so the game starts normally with no separate ELF selection. The original SELF is copied byte-exactly to `USRDIR/.th2dxp-backup/EBOOT.BIN` first and `restore` puts it back. Any old side-by-side `EBOOT_EN.elf` is removed.
- `data.sdat` must keep its name, so it is backed up once under the same directory before replacement. An archive that already matches the staged pair is skipped instead of copied again, and an archive that is **neither** the pristine BLJM60381 file **nor** covered by a recorded backup is refused rather than overwritten. The first install needs roughly twice the 2.2 GB archive in free space.
- `.th2dxp-en-patch.json` records every install, hash and backup. `restore` verifies the recorded backup hashes and only then writes.

### The GUI installer's own flow

`tools/patch_gui.py` drives `tools/patch_engine.py`, which uses `tools/ps3_self.py` for the executable and `tools/patch_data.py` for the data patch:

1. hash `EBOOT.BIN` and `data.sdat` and refuse anything that is not the pristine pair (or the tool's own previous install),
2. back both up once under `.th2dxp-backup` on the same volume, recording their hashes in the journal **before** anything is rebuilt,
3. decrypt `EBOOT.BIN` with the single BLJM60381 application keyset, apply the 255 edit runs and the appended segment, and verify the pinned `a31bdd83…` hash,
4. decrypt `data.sdat`, append the eleven pre-compressed atlas chunks, rewrite their eleven table rows, and verify the pinned `0438c3af…` DAT hash,
5. re-encrypt, authenticate the new archive with `make_npdata-pack --verify`, then **decrypt it again** and require the same `0438c3af…` DAT — the container hash cannot be pinned because `forge_npd_title_hash` hashes the input DAT's path string into the NPD header, so a rebuild is content-identical but never byte-identical to the build machine's archive,
6. move both verified files into place and record the install.

Free space is checked against the peak of (backup + pristine DAT + patched DAT), (backup + patched DAT + new archive) and (backup + new archive + read-back DAT) plus 256 MiB — about 6.4 GiB on a first install; intermediate files live in `USRDIR/.th2dxp-work` and are removed on success or failure. A failure at any step leaves the installed game untouched.

Patching installs a **staged artifact**; it does not create one and does not imply runtime acceptance.

## Text defects: fixed, validator clean

`python -X utf8 tools/import_gt_output.py --check` now reports `defect_count: 0` for all885 base-game files (`blocked_files: 0`), so the translations are structurally importable. Two auditable passes produced that:

| Pass | Rows | Files | Record |
| --- | ---: | ---: | --- |
| CP932/name normalization (`normalize.py --apply`) | 3,380 | 302 | `work/translation/fix-gt-output/normalization-log.json` |
| Editorial re-cuts (`apply_recuts.py --apply`) | 279 | 101 | `work/translation/fix-gt-output/recuts.json`, `.../recuts-log.json` |

- Normalization kept every sentence: `—`→`―` (the horizontal bar the Japanese source already uses 8,242 times), `–`→`-`, Latin-1 diacritics reduced to base letters, macrons expanded with glossary-first names (`Kusugawa`, `Yuuji`, `Ruuko`, `Maaryan`/`Saaryan`, `Tonami`, `Kousaka`).
- The re-cuts are hand-authored replacements, not mechanical moves: each one puts an inline control (`*nnk`, `*nf`, `*nl`, `*nfk`, `*h2`, `\k`, `\n`) or a private-use glyph back into the fragment that owns it in the Japanese row, and closes the sentence the control interrupted. `apply_recuts.py` refuses any replacement whose ordered controls or private-use glyphs differ from the immutable original row, so the checks cannot be satisfied by loosening them.
- Eight rows that still carried the Japanese suffix after a name token (`*nnk坊`) now read `*nnk-bou`. The remaining rows containing Japanese are deliberate: quoted kanji the scene is about (`『具民』`, `『県民』`, `『世露死苦』`, `姫百合`, `瑠璃`, `の`).

Both passes are re-runnable and write nothing without `--apply`:

```console
python -X utf8 work/translation/fix-gt-output/normalize.py            # report only
python -X utf8 work/translation/fix-gt-output/apply_recuts.py --verify # control/glyph audit
python -X utf8 tools/import_gt_output.py --check --report work/translation/gt-output-defects.json
```

The 9,332 rows that still equal the original are carriers, not untranslated dialogue: 6,237 blank, 2,876 punctuation-only (`「……」`, `……。`, `「♪～」`) and 219 control/tag/label rows (`*nf、`, `<S1>`, `\n\n`, `W60`, full-width Latin quiz strings). The only translatable rows left were two name shouts, now `「*nf～!」` and `「*nf―!」`; no row containing kana or kanji is left in Japanese. These carriers must keep their exact original bytes, so a coverage count that treats them as missing translation is measuring the wrong thing.

`project.py build` still refuses growth without the manual form, but the finished translation is not blocked on it: `tools/stage_english_build.py` assembles the same engine image offline and stages it for testing.

```console
python -X utf8 tools/stage_english_build.py --verify-only   # assemble + re-extract proof, write nothing
python -X utf8 tools/stage_english_build.py                 # build/english-v0.1/{EBOOT.elf,EBOOT_EN.elf,assets/data.sdat}
python -X utf8 tools/patch_game.py apply --build build/english-v0.1          # dry run
python -X utf8 tools/patch_game.py apply --build build/english-v0.1 --apply  # you install it
```

Staged artifact (v0.1): `build/english-v0.1/EBOOT.elf`, 10,687,608 bytes, SHA-256 `a31bdd834a61cd38fa310f0f63832d2991bc4a09558859a7ba63415e245e5735`, paired with `assets/data.sdat` (`bbb932bf0b07f0f5f4b254f1586261c85eda10a43f094a61f04656bde0b1366f`, 2,202,570,928 bytes) whose font atlas (`fa17b5ad…`) carries the 62 letters/digits, six brackets and **23 ASCII punctuation** cells. The six native default-name strings are repacked as `Kouno Takaaki` / `Taka`. Every changed payload is decoded back out of the assembled image and compared item-by-item with `script/` (102,062 text items), choice captions are re-extracted from their parent payloads, the 1,097 untouched payloads stay byte-identical, and the two corrections are proved not to alter any scenario payload; repeat assembly gives the same digest.

The archive is repacked from the pristine `4509a4e9…` dump, so this pair supersedes `build/english-dialogue/` (`0c5a43bd…` / `be72aa94…`) and the older diagnostic archives; do not mix them. A delta patch is not viable here: the staged archive shares zero identical 16 KiB ciphertext blocks with the pristine one (block chaining), so an xdelta payload would be the whole 2,100.5 MiB file.

The tool never writes `work/qa/manual-evidence.json`, so `project.py check`, `build --engine-growth` and `gates.py check` keep reporting the manual gate as closed, and the staged file implies no runtime result. Production naming stays closed until the 24 `windows` observations exist:

```console
python -X utf8 tools/project.py build --engine-growth
# ERROR: Production engine growth needs complete manual acceptance:
# work/qa/manual-evidence.json
```
## Verification and limits

All serialized files were read back and restored to their exact original structured units. Original native codec samples passed for `script_0000.json` and `script_0006.json`, including the latter's three choices. Five synthetic tests cover fragment identity, blank/duplicate preservation, control/encoding rejection, separate sets/sidecars and safe output publication:

```console
python -X utf8 -m unittest discover -s tests -p test_linguagacha_export.py -q
```

Two control-only views (`script_0809.json` / `421020001` and `script_0810.json` / `421020002`) contain no editable text and are recorded in the manifest rather than emitted as empty translator files. Other native bytecode remains in the original baselines.

LinguaGacha's Message-JSON implementation was inspected at commit `4c3bbe948c92eb8b30a9868cb9ec13d71794a74a`; its reader accepts string messages, including empty strings, and preserves string names. No LinguaGacha GUI import/export or game execution was tested. Conversion checks do not establish translation quality, rendering, save compatibility or runtime acceptance. Exact counts, source bindings and native sample results are in `work/linguagacha-original/metadata/manifest.json`.
