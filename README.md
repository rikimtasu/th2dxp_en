# ToHeart2 DX PLUS — English translation project

Unofficial **PS3 / BLJM60381** English localization workspace, initialized from the supplied decrypted executable. The base-game dialogue is translated and an offline English artifact is staged (`build/english-v0.1/`), but **no runtime acceptance exists yet**: the 24 observation slots for the current engine build are still empty, so this is not yet a release-complete English patch. No RPCS3 process is launched by project tools, and the installed game is never patched automatically.

Uses [TH2DXP_KIT](https://github.com/hiroshil/TH2DXP_KIT), with workspace conventions from [fan-translation-template](https://github.com/minhnhattonthat/fan-translation-template) and the phased workflow from [translate-retro-game](https://github.com/minhnhattonthat/translate-retro-game). Exact upstream revisions: [`upstreams.json`](upstreams.json).

## Workspace

| Path | Purpose |
| --- | --- |
| `project.json` | Source SHA-256, paths and output target |
| `script/script_*.json` | Editable local extraction: change only text items' `translated_text` |
| `work/original-script/` | Immutable original extraction and hashes |
| `work/original-choice-text/` | Immutable companion baseline for native choice-caption operands |
| `glossary.md`, `glossary/` | Merged VNDB v20/v90 names, aliases, stable IDs and explicit display-name overrides |
| `[ittaku-subs]th2/` | User-supplied PC reference patch, never run its destructive BAT files |
| `reference/ittaku/` | Local reference material/index; see reference guide |
| `tools/project.py` | Message/choice extraction, validation, guarded growth rebuild, identity and offline smoke |
| `vendor/` | Pinned upstream checkouts, reproducible via bootstrap |
| `build/` | Local staged ELFs and verification reports; never automatic deployment |
| `docs/` | Status, decisions, fonts, RE findings, Ittaku and manual QA guides |

Game inputs, extracted Japanese text, reference translation, builds, upstream checkouts and saves are ignored by Git. **This repository is source-only**: it contains tools, tests, documentation and the OFL-licensed font, but no game files, decrypted executable, extracted scripts, save data or built ELF/SDAT. Do not force-add proprietary data. Translation publication/export and patch-only release packaging require a later rights/release review; no release command is advertised prematurely.

## Reproducing from your own copy

1. Obtain your own lawful **BLJM60381** dump and decrypt its `EBOOT.BIN` to `EBOOT.elf` yourself; no SELF decryption tool, key or game data is provided. Put the decrypted ELF at the repository root and keep the encrypted file untouched.
2. Run the bootstrap/install commands below, then `python -X utf8 tools/project.py extract` once. Extraction creates the ignored `script/` and baseline trees.
3. Edit only `translated_text` values, then run `check` and `build`. Diagnostics/UI staging use their own documented inputs and refuse overwrites.
4. For asset or live checks, set `game_usrdir` in `project.json` to your own `PS3_GAME/USRDIR`; do not point tools at a shared or installed copy while another process is using it.

Exact output hashes depend on the pinned toolchain and your own inputs. Build reports record the hashes that were produced. Game-data-bearing outputs — the patched ELF, the repacked `data.sdat`, extracted Japanese and translated text — are never published; the only distributable artifact is the packaging tool itself (`dist/th2dxp_patch.exe`, built from `tools/patch_game.py`), which installs a build you produced locally.

## Commands

Python **3.10+**, Git, pylzma and Pillow. On Windows pylzma may compile a wheel and require Visual C++ build tools; it was successfully built for this workspace's interpreter.

```console
python -X utf8 tools/bootstrap.py
python -m pip install -r requirements.txt

# Already extracted here. On a fresh workspace with the same EBOOT.elf:
python -X utf8 tools/project.py extract

# After editing translated_text:
python -X utf8 tools/project.py check
python -X utf8 tools/project.py build

# Offline verification; neither command launches an emulator:
python -X utf8 tools/project.py identity
python -X utf8 tools/project.py smoke
python -X utf8 tools/update_glossary.py --check
```

Commands resolve project paths from their own location, not the current working directory. Extraction refuses to overwrite an existing `script/`. Supply the original `EBOOT.elf` at the project root; the build refuses a different size/hash. Do not substitute the installed encrypted `EBOOT.BIN`.

Choice companions are already prepared here: **1,335 captions in 115 `script_####_choices.json` files**, bringing the editable inventory to **1,124 files / 183,446 records**. An older workspace without them uses `python -X utf8 tools/project.py extract-choices` once; it refuses overwrites. Existing scripts and `work/original-script/` are not rewritten. Edit only companion `translated_text`, never the duplicated original choice bytes inside a primary script's `opcode_gap`.

`build` writes `build/english/EBOOT.elf` plus a report. Before complete manual acceptance, unchanged work remains source-identical; a zero-translation native-corrected build is still not an English release. Valid `work/qa/manual-evidence.json` selects full-length native VWF/appended capacity for ordinary check/build/smoke; invalid evidence fails closed. `--engine-growth` requires that acceptance explicitly. Production never copies diagnostic text. Preserve the staged native template/manifest. `identity` stays source-only. Offline `smoke` now exercises message and choice markers; before cutover it stages its capacity diagnostic separately without enabling production.

## LinguaGacha export

Original Japanese PS3 messages and choices are available privately as UTF-8 `name`/`message` JSON. Import `work/linguagacha-original/base-game/gt_input/` first (**885 files / 102,062 native items**); the separate complete set contains **1,122 files / 183,446 items**. Speaker names are deliberately empty until native bindings are verified. Preserve filenames, row order, blank carriers and inline controls. See [`docs/linguagacha.md`](docs/linguagacha.md) for conversion, output folders, mappings and verification limits. This is not automatic translation insertion or runtime acceptance.

Translated `gt_output` is validated by `tools/import_gt_output.py` before any `script/` write (`--check` now reports `defect_count: 0` over all 885 base-game files), and a verified build pair is installed by `tools/patch_game.py` — or by the Python-free `dist/th2dxp_patch.exe` — which replaces `EBOOT.BIN` with the patched ELF, backs up the original SELF, and refuses an unrecognized `data.sdat`. The finished translation is staged as `build/english-v0.1/`: every changed payload is re-extracted from the assembled image and compared with `script/` (102,062 text items), 1,097 untouched payloads stay byte-identical, and the artifact carries the Latin/punctuation atlas plus the English default name `Kouno Takaaki`. Details and the exact order of operations are in [`docs/linguagacha.md`](docs/linguagacha.md#patching-a-test-installation).

## Editing and reference reuse

1. Read [`glossary.md`](glossary.md) and [`docs/decisions.md`](docs/decisions.md). Names default to given-name-first; retain source honorifics. The glossary merges **28 unique VNDB character IDs**, **22 shared** between [ToHeart2 v20](https://vndb.org/v20) and [AnotherDays v90](https://vndb.org/v90). Membership is not a PS3-release cast guarantee.
2. Use [`docs/ittaku-reference.md`](docs/ittaku-reference.md) for the complete source-backed PC extraction: **53,448 encoded string operands**, including `SetMessage2`, `AddMessage2` and choices, from the verified already-patched local `SDT.PAK`. The older 48,424-candidate ASCII index remains useful for quick substring search, not instruction boundaries. No unmodified archive or destructive BAT execution is needed for this prepared reference. Neither extraction is automatically aligned to PS3.
3. Find the Japanese context in `script/`. Keep every unit/item, original string, metadata field, control code, suffix and opcode gap intact. Change only `kind: text` items' `translated_text`. IDs are filename plus zero-based unit/item indices. `work/scenes/scenario-membership.json` records normal title-story routing ownership; it does not prove individual route feasibility.
4. Translate from the PS3 Japanese; use Ittaku to save reference work where context agrees. Do not auto-import PC-only content or assume matching script IDs across platforms. Credit/reuse rights must be resolved before publishing adapted Ittaku text.
5. Run `check`, then `build`. Validation rejects unencodable or lossy CP932, changed inline controls (including native name substitutions/font tags), literal newlines, blank replacements and metadata changes. Original text/compressed-slot budgets remain enforced before full manual engine acceptance; the guarded growth path removes those budgets without shortening text. Format/address bounds and safe label relocation still apply. Encoding bytes are not measured screen width; never cut meaning to pass a gate.

Search the prepared reference:

```console
python -X utf8 tools/ittaku_reference.py search "Konomi" --kind decoded --limit 5
```

To regenerate it, use the documented `index --patched-sdt` command. Bare `index` intentionally indexes only compressed patch fragments and replaces the decoded index.

## Manual testing and remaining boundaries

Follow [`docs/manual-testing.md`](docs/manual-testing.md). **You launch RPCS3 manually.** Builds are decrypted ELFs, not signed/encrypted SELF files. `tools/patch_game.py` (or `dist/th2dxp_patch.exe`) is the only supported way to install one: it copies the patched ELF **as `EBOOT.BIN`** — the form RPCS3 boots — after backing the original SELF up byte-exactly under `USRDIR/.th2dxp-backup/`, and `restore` puts it back. Do not overwrite `EBOOT.BIN` by hand. No runtime boot, layout, save compatibility, route reachability or font-width verification is claimed by offline checks.

Current staged pair: `build/english-v0.1/EBOOT.elf` (`a31bdd83…`) with `assets/data.sdat` (`bbb932bf…`). If your USRDIR holds an older diagnostic archive (for example `be72aa94…`), the patcher refuses to replace it: restore your own pristine `data.sdat` (SHA-256 `4509a4e9…`, 2,185,195,888 bytes) first.

The asset-decryption prerequisite is **cleared**: `work/assets/data.dat` contains 3,516 entries recovered read-only using a pinned standalone SDAT utility. Original font atlases were extracted and Latin glyph pixels visually inspected; runtime glyph mapping/spacing still needs manual proof. See [`docs/fonts.md`](docs/fonts.md), [`docs/rebuild-capacity.md`](docs/rebuild-capacity.md) and [`docs/status.md`](docs/status.md).

### Diagnostics and runtime gate

`tools/gates.py check` is the runtime/bulk gate. It intentionally exits nonzero until every required check has genuine exact-build manual evidence; production cutover also requires the complete accepted correction.

The current diagnostic pair, exact hashes, required cases and results-form path are in [`docs/pretranslation-gates.md`](docs/pretranslation-gates.md). Follow [`docs/manual-testing.md`](docs/manual-testing.md) and launch RPCS3 yourself. Diagnostic staging is explicit and never deploys:

```console
python -X utf8 tools/ui_probe.py
python -X utf8 tools/gates.py check
```

Staging refuses existing output directories and may need the documented predecessor probes; read the QA guides first. Emitted reports and staged builds remain local/ignored and are not published.

Base-game-first readiness is also tracked independently of runtime gates:

```console
python -X utf8 tools/base_game_inventory.py --check
```

This currently exits **1 for untranslated coverage, not membership**. The complete normal-title ToHeart2 denominator is **1,272 scenarios / 102,062 editable records**, including the one shared terminal program. AnotherDays is deferred; separate Ikuno/Konomi-Tamaki stories and inactive/debug programs retain explicit ownership metadata. All 1,884 scenarios are classified from native title/calendar/load effects and the base terminal barrier, not PC names or a static opening closure. Individual route feasibility is not claimed. Zero work records are translated; all **16,172 message read-marker candidates** remain context-unverified and do not align choice companions automatically.

Coverage report schema3 exposes `coverage.uncovered_base_game_records`. `--review-evidence` accepts attributed exact-text-hash reviews, not automatic approvals. A generic `translation_completeness` claim must refer to changed text. Unchanged legitimate names/tokens require separate `unchanged_exceptions` entries with `review_kind: unchanged_token_exception`, a `proper_name`/`nonlinguistic_token` category and rationale; these count as covered exceptions, never translated records. Unreviewed unchanged text remains uncovered. Full schema: `tools/base_game_inventory.py`.

Base-message review preparation can proceed independently: `python -X utf8 tools/alignment_candidates.py` stages the source-bound base-only queue under `work/alignment/base-game-message-candidates/`, refusing overwrites. It retains all101,829 base-message records exactly once;233 base choice captions remain explicitly outside message-marker alignment. Every candidate remains context-unverified and barred from automatic import. See [`docs/ittaku-reference.md`](docs/ittaku-reference.md#current-base-only-message-review-queue).


## Attribution and licensing

See [`NOTICE.md`](NOTICE.md). Project-owned Python tools/docs use MIT; the separately linked `tools/pc_reference_dump.cpp` is explicitly GPL-2.0. Game data, Ittaku translation and VNDB-derived data have separate rights. No game/BIOS downloads, automatic publication, or redistribution permission is implied. Setup/tooling used AI assistance.
