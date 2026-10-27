# Repository Guidelines

## Project Overview

Unofficial English localization workspace for **ToHeart2 DX PLUS, PS3 BLJM60381**, using a supplied decrypted `EBOOT.elf`; not a completed English patch. Complete the **base game first**; localize/redraw its UI before full dialogue translation and defer AnotherDays. Preserve full meaning and immutable source assets. The user approved GenInterfaceJP for staged Latin letters/digits; original Japanese, other punctuation and private glyphs remain intact. Capacity/layout failures never permit shortening translations.

Before changing game text, read `docs/decisions.md`, `docs/status.md`, and `glossary.md`. Use `docs/ittaku-reference.md` for contextual PC-reference reuse, never automatic import. Verify PS3 Japanese correspondence and retain provenance; filenames, PC availability and static reachability do not prove edition/route membership.

## Architecture & Data Flow

1. `project.json` pins source size/SHA-256, CP932 encoding and workspace paths. `tools/project.py` orchestrates extraction, validation and staged builds.
2. `tools/scenario_source.py` decodes the complete native index and continuation chunks. The pinned `vendor/TH2DXP_KIT/scenario_eboot_tool.py` supplies structured message codecs and compression; retain local container handling, not the kit's incomplete extraction/selective importer.
3. Extraction creates editable message JSON in `script/` and immutable baselines in `work/original-script/`. `tools/choice_text.py` exposes native choice captions as `script_####_choices.json`, backed by `work/original-choice-text/`; their duplicated bytes in primary `opcode_gap` items remain immutable.
4. Validation permits only text-item `translated_text` changes. Build reconstructs messages **before rescanning/rebuilding choices**, relocates symbolic labels safely, and verifies every scenario payload before staging an ELF/report under `build/`.
5. Before manual acceptance, production uses original compressed slots/pointers. `tools/production_engine.py` enables guarded VWF/save-preview/pagination, long-text/checkpoint and typography corrections plus appended scenarios with 64-byte starts only after acceptance. Presence of `work/qa/manual-evidence.json` selects growth for ordinary `check/build/smoke`; invalid evidence fails closed. Production copies approved native/UI corrections, never diagnostic dialogue.
6. UI localization is source-bound: `native_ui_patch.py` relocates strings/pointers; `native_history_patch.py` adds owned history and helpers inside non-writable R-X PH2. `native_latin_font_patch.py` binds generated Latin/bracket pixels to68 exact source metric pairs; `native_backlog_view_patch.py` scrolls whole records with existing controls. `ui_graphics.py` redraws selected TPL records. `ui_archive.py` validates native chunks and DAT → SDAT → DAT integrity; use `scenario_source.pack` (32-KiB chunks, 8-KiB dictionary, explicit size, no EOS), never the vendor DAT compressor. Scenarios occupy the next free mapping.

Reference extraction/alignment and scenario membership inventories are separate analysis paths, not translation-import approval. Offline diagnostic assembly does not enable production or prove runtime behavior.

## Key Directories

| Path | Purpose / editing boundary |
| --- | --- |
| `tools/`, `tests/` | Offline Python CLIs/helpers and synthetic regression tests |
| `script/` | Local message/choice translations; edit only `translated_text` |
| `work/original-script/`, `work/original-choice-text/` | Immutable baselines/manifests; never change to pass validation |
| `work/qa/`, `work/scenes/`, `work/alignment/` | Exact-build evidence, scope inventories and unverified alignment candidates |
| `work/ui/` | Private native/graphics translation inventories, soundtrack provenance, immutable source TPLs and readable previews |
| `work/pc-reference/`, `reference/ittaku/`, `[ittaku-subs]th2/` | Private reference data; do not modify installed PC references or run destructive patch BAT files |
| `glossary/` | Character snapshots, stable IDs, provenance and editorial overrides |
| `vendor/`, `build/` | Reproducible pinned tools and staged outputs; not deployment |
| `docs/` | Decisions, status, manual gates, fonts, capacity and reverse-engineering evidence |

## Development Commands

Run from the repository root; tools resolve project paths relative to their source files.

```console
python -X utf8 tools/bootstrap.py
python -m pip install -r requirements.txt
python -X utf8 tools/project.py check
python -X utf8 tools/project.py build
python -X utf8 tools/project.py identity
python -X utf8 tools/project.py smoke
python -X utf8 -m unittest discover -s tests -q
python -X utf8 tools/update_glossary.py --check
python -X utf8 tools/gates.py check
python -X utf8 tools/base_game_inventory.py --check
```

- `build` writes `build/english/EBOOT.elf` and `EBOOT.report.json`; accepted UI-enabled growth also stages its exact `data.sdat`. `identity` requires source-identical reconstruction; `smoke` stages message/choice markers using temporary baseline copies. Never mix original-slot ELFs with an existing localized SDAT.
- `project.py check` is script/domain validation, not a configured Python style linter. `gates.py check` is the separate runtime/production gate. The user explicitly authorized **bulk private editorial drafts before runtime acceptance**; this exception does not authorize insertion into `script/`, production growth/builds, fabricated test passes or automatic reference import. Inventory `--check` writes reports before returning its coverage status.
- Fresh extraction only: `python -X utf8 tools/project.py extract`. Already extracted here; it refuses existing workspaces. `extract-choices` is a one-time companion migration, not a routine refresh; `recover` repairs older incomplete extractions while preserving translations.
- Supporting workflows: `tools/assets.py prepare` / `inspect`, `tools/scene_catalog.py`, `tools/flow_probe.py`, and `tools/rebuild_audit.py`. Read their guides before generating diagnostics; staged probes commonly refuse overwrites. There is **no automated game-run command**.
- UI archive reconstruction requires the separate GPL packer (`python -X utf8 tools/build_sdat_tool.py`, existing GCC, one-time only). `python -X utf8 tools/ui_probe.py` stages `build/gen-latin-reload-probe/`; changed Latin/UI pixels require a new paired SDAT, not the earlier c4898391 or a660c827 archive. It uses the SHA-verified original backup identified by retained archive provenance. Existing outputs are preserved; read QA guides first. No command deploys anything.

## Code Conventions & Common Patterns

- Plain synchronous Python: four-space indentation, `snake_case` functions/locals, `UPPER_CASE` constants. Reuse simple modules and explicit loops; no async framework or dependency-injection container.
- Configuration/`Path` constants live in `project`; helpers receive codec (`kit`), metadata and payloads explicitly, with keyword-only safety options such as `allow_growth`. Intentional deferred/circular imports require project paths to exist before importing `choice_text`; do not casually reorder imports.
- Reuse `project.load/save` for UTF-8 JSON: `ensure_ascii=False`, two-space indentation, LF and final newline. Use explicit binary endianness; ELF/container fields are big-endian, VE headers/choice lengths/label offsets little-endian. Mutate temporary `bytearray` buffers and return `bytes`.
- Raise descriptive `ValueError` for invalid data; CLI boundaries report `ERROR:` and exit nonzero. Never silently skip malformed records, weaken guards or add fallback acceptance.
- Translation edits must preserve filenames, ordering, original strings, lengths, bytecode, metadata, suffixes and ordered engine controls, including backslash controls, angle/font tags and native name substitutions. Require strict **round-tripping CP932**, not merely encodability; reject blank replacements and literal control characters. Record IDs use `filename:zero-based-unit:zero-based-item`.
- Apply the user-supplied translation prompt in `docs/ittaku-reference.md`: resolve subjects/pronouns from context, keep vivid colloquial voice and full original detail/tone. One source `text` item requires one translation of that same fragment, unfinished when the source is unfinished; never merge, split or redistribute adjacent lines. Translate readable narration/dialogue/names/sounds, not variables, escapes, tags, IDs or paths.
- Coverage reviews are not context hints: changed English needs exact-hash completeness review; unchanged names/tokens need individually attributed `unchanged_token_exception` entries. Never auto-exempt names or count unchanged dialogue as translated. Inventory schema3 reports reviewed translations, explicit exceptions and `uncovered_base_game_records` separately.
- Keep original-slot budgets until growth acceptance; retain format/address bounds and safe label relocation afterward. Do not change source hashes, baselines or codec settings to make a patched input pass.
- Native long text crosses geometry, opacity, VM-scratch, checkpoint, history-record and backlog-scratch limits. Preserve raw progress/unread nodes and complete logical records. Native history retains 100 fixed-stride slots with owned growable payloads; destroy/reset release overflow, and backlog scanning owns full-size temporary input. Tagged checkpoint entries retain fixed save-slot size and depend on the same scenario offsets. Corrupted saves are evidence, not migration inputs.
- Word lookahead changes geometry, never script bytes or raw progress. Native controls delimit runs; active angle-command operands must not enter lookahead. Glyph queue endpoints are inclusive and must become full screen/UV edges before backend transforms.
- Redrawn UI keeps normal proportions and complete words: uniformly scale the selected source-bound glyph mapping, wrap whole words and fail on unreadable cells rather than squeeze/truncate. Main labels require at least14 source pixels; only small rotated calendar captions may use12. Relocated crops require matching native geometry; inspect native-size previews.
- `geninterface_latin.py` generates62 alphanumeric and six bracket-alias R-plane cells at47px em/baseline37, preserving every unrelated packed bit. Native a/b pairs must match quantized ink; keep Japanese/private/punctuation metrics and pixels. Retain actual b+6 help/options/dialogue and b+2 save/music protocols. `594E8` already applies bearings, so `59488 →1BE28` stays fixed-cell. Compare actual caller scales/panels and caption/music bounds after a font cutover.
- Native UI strings preserve ordered printf conversions, numeric suffixes such as `%d0`, and private font glyphs. Preserve PS3 music-role bindings even when album credits differ; `work/ui/music-credit-reference.json` records the two requested VGMdb references and Japanese title correspondence.
- `glossary.md` is generated. Edit `glossary/sources/project_overrides.json` by stable VNDB character ID with a reason, then run `python -X utf8 tools/update_glossary.py --offline`. Use project display names, given-name-first order and source-present honorifics; preserve contextual nicknames/titles.

## Important Files

- `project.json`, `upstreams.json`, `requirements.txt`: authoritative source/path, upstream-revision and Python-dependency configuration.
- `tools/project.py`, `tools/choice_text.py`, `tools/production_engine.py`: main entry point, choice reconstruction and guarded production assembly.
- `tools/scenario_graph.py`, `tools/scenario_membership.py`, `tools/base_game_inventory.py`: source graph, closed normal-title story ownership and reviewed translation coverage. Ownership is not per-route feasibility; separate stories/inactive programs remain explicit, not deleted.
- `tools/native_pagination_patch.py`, `tools/native_pagination_smoke.py`: queue-safe pages and encoded replay; preserve unread nodes and raw-byte/save progress.
- `tools/native_runtime_text_patch.py`, `tools/native_runtime_text_smoke.py`: opacity/literal/checkpoint safeguards. `tools/native_history_patch.py`, `tools/native_history_smoke.py`: history ownership/crash replay. `tools/native_backlog_smoke.py` covers reveal; `tools/native_backlog_view_patch.py`, `tools/native_backlog_view_smoke.py` cover within-record scrolling and clipped submissions. Never split logical history or inherit retired gameplay ordinals.
- `tools/native_typography_patch.py`, `tools/native_typography_smoke.py`, `tools/typography_probe.py`: glyph-cell edges/word wrapping and retained input. `tools/geninterface_latin.py`, `tools/native_latin_font_patch.py`, `tools/native_latin_font_smoke.py`: approved Latin atlas/metric generation and real-pixel/caller sampling; native copy guards bind exact source-derived pairs.
- `tools/native_ui_patch.py`, `tools/native_ui_smoke.py`, `tools/ui_graphics.py`, `tools/ui_archive.py`, `tools/ui_probe.py`: UI strings, actual native geometry, readable selected-font redraw and paired encrypted staging. Private manifests stay under `work/ui/`.
- `tools/build_sdat_tool.py`, `tools/sdat_pack.c`: separately licensed exact-source packer repairs and strict SDAT authentication; build outside `vendor/`, retain the original decryptor and failed artifacts.
- `tools/alignment_candidates.py`: source-bound **base-message-only** review queue at `work/alignment/base-game-message-candidates/`; requires fresh complete membership and immutable baseline hashes. Candidates are not import approval, route feasibility or choice alignment.
- `docs/pretranslation-gates.md`, `docs/manual-testing.md`: current diagnostic artifact, exact remaining cases and evidence procedure; prefer these over historical status entries.
- `docs/re/README.md`, `docs/fonts.md`, `docs/rebuild-capacity.md`: native-format/layout findings and limitations. Workflow reference: `vendor/translate-retro-game/skills/translate-retro-game/SKILL.md`; PS3 manual-QA deviations take precedence.

Update `docs/status.md` after work; record changed decisions/limitations honestly. Do not claim translated coverage, runtime verification, redistribution permission or a release without evidence.

## Runtime/Tooling Preferences

Use **Python 3.10+**, pip, Git and pinned dependencies from `requirements.txt` (`pylzma`, Pillow). Use `python -X utf8` for Japanese text on Windows; pylzma may need Visual C++ build tools. UI SDAT packing additionally needs existing GCC; staging never downloads/builds it automatically. Native diagnostics have module-specific dependencies and are not routine tests. Preserve the separate GPL licensing of `tools/pc_reference_dump.cpp`, `tools/sdat_pack.c` and the generated make_npdata derivative.

**Never launch, download, install or configure RPCS3, deploy an ELF/SDAT to the installed game, modify installed game/reference files, or overwrite saves.** The user performs runtime testing manually. Root `EBOOT.elf` and both baseline trees are immutable. Do not substitute encrypted `EBOOT.BIN`. Keep proprietary inputs, extraction/reference text, builds and saves out of version control/releases; do not force-add ignored data. Publication requires rights review and patch-only packaging.

## Testing & QA

Tests use standard-library `unittest` with synthetic binary/text fixtures, temporary directories, patched project paths and `assertRaisesRegex` for rejected inputs. Follow `tests/test_*.py`; unit tests do not require game assets or an emulator. Cover consumer-visible invariants: continuation bounds, control/encoding preservation, choice-label relocation and layout preservation. No test-coverage percentage is configured; translation coverage is a separate inventory metric.

Use quiet `unittest` for routine regressions (usually a few seconds); `-p test_ui_graphics.py` or the affected filename focuses iteration. Asset-backed native replays are separate, slower checks: run the changed path, not every replay or `ui_probe.py` after ordinary edits. Complete staging is for a distinct changed artifact. Retain parent/long-record/ownership/wrap/encoding/relocation/authentication boundaries; trim duplicate matrices, not safety guards. Final `check → build → smoke` follows actual translation insertion.
Current UI acceptance binds **both** `build/gen-latin-reload-probe/EBOOT.elf` and its `assets/data.sdat`; form: `work/qa/gen-latin-reload-results-to-fill.json`. All24 checks require real observations. Preserve earlier pairs/forms:66786e63/a660c827 has the confirmed save-reload crash and UI defects;62bdc049 reveals long backlog text but reports incomplete g and bottom overflow. The new path uses existing up/down controls within a whole record, then navigates records; source gameplay progress/history ownership must remain unchanged. Offline proofs are not runtime acceptance.

Inter was canceled. The user subsequently approved **GenInterfaceJP Regular Latin letters/digits**, superseding the earlier comparison-only boundary; Japanese/punctuation/private glyphs and original inputs stay unchanged. Native ASCII aliases also serve full-width Latin, so those Latin appearances change. Keep font/OFL provenance and the staged OFL notice. Font pixels, native metrics, wrapping, baseline/cell padding and actual UI consumers must be verified together; a TTF swap alone is insufficient.

Offline success and encoded native replay do **not** establish rendering, pagination, branch reachability, save compatibility or full-game memory fit. Follow the current manual guides; record real results with exact artifact hash, tester, version, scene, notes and screenshots. Preserve accepted/failed evidence on its original build; never fabricate passes or request repeats merely to reconfirm established results. Earlier short-run control passes do not accept the new long-text skip, story-state or checkpoint codec; inspect authorized saves/logs read-only.
