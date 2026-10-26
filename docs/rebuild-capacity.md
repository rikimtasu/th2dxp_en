# Scenario completeness and growth capacity

## Complete container decoding

The upstream scanner catches chunk-decoding exceptions and continues. It interpreted a continuation prefix such as `80 00 2B 2F` as an enormous single compressed length, silently omitting **60 scenarios**. The raw native index actually has **1,884** nonzero entries, not 1,824. All 60 omitted entries contain editable text.

`tools/scenario_source.py` now reads each slot as 32 KiB chunks: a big-endian prefix contains the high-byte flag and low-24-bit compressed length; `0x80` means continuation and `0x00` a final LZMA-ALONE chunk. It also understands raw `0x40` chunks. Decoding validates slot bounds, flags, terminal status, combined uncompressed length and trailing data. The index scan never silently skips a bad entry.

`tools/project.py recover` migrated this workspace to a complete baseline, adding the 60 missing JSON files without replacing an existing translation. It also preserves the actual native names (for example `010301000`) separately from stable `script_0000.json` IDs. Existing 949 files matched the recovered provenance exactly. Portable LF serialization prevents a Windows newline-only mismatch from masquerading as changed provenance.

The immutable primary extraction contains **1,009 message scripts**, **153,503 logical units**, **278,972 items**, **182,111 message records** and **32,929 explicit control records**. Separate native-choice companions add **115 files / 1,335 captions** without changing those originals: total editable inventory is **1,124 JSON files / 154,838 units / 183,446 records**. Five permanent container regressions cover continuation data, incorrect final flags, truncation, neighbor-slot boundaries and declared-size mismatch.

## Arena measurements

| Property | Observed value |
| --- | --- |
| Scenario arena | File offsets `0x29F000`–`0x639CF8` (exclusive end) |
| Arena bytes | 3,779,832 |
| Original indexed slot bytes | 3,734,108 |
| Inter-slot gap bytes | 45,724; all zero |
| Original slot allocation alignment | 64 bytes |
| Multi-chunk scenarios | 60 |

The kit's `DEFAULT_INPLACE_MAX_SIZE` is the sum of original slots, not the full file-offset span. A selective repacker must not overwrite unchanged/omitted scenarios. Before complete manual acceptance, production preserves each original slot/pointer, chunks changed scenarios correctly, and verifies all 1,884 output payloads. The guarded appended production implementation below is not enabled merely by successful offline assembly.

## Offline growth experiment

```console
python -X utf8 tools/rebuild_audit.py
```

This creates **only** `build/growth-probe/EBOOT.elf` and `report.json`. It grows the first text record of native scene `010301000` by **86 bytes**, uses the upstream structured codec's label-table adjustment, then packs **every** indexed scenario into the bounded original file-backed PT_LOAD arena. Unchanged scenarios keep their original compressed bytes. All table data pointers/sizes are updated and every decompressed payload is verified. No file/segment extension or write outside the scenario arena/index is allowed.

Retaining 64-byte allocation alignment exceeded the arena and was rejected without writing an ELF. The diagnostic instead tests the upstream container's four-byte chunk alignment, reclaiming zero inter-allocation padding. **Four-byte alignment is experimental runtime behavior, not a proven safe production change.**

Observed compacted use: 3,734,148 bytes; remaining arena capacity: 45,684 bytes. This is **not** enough evidence that the entire English translation will fit; translated compression budgets remain unknown.

Diagnostic SHA-256: `2417a36b15a0718448dfe423420889af2ef170243e09d8d0793c7d9c49bcbeb0`.

## Full-length text with original 64-byte allocations

`tools/scenario_capacity.py` now stages a separate diagnostic arena instead of reclaiming four-byte-alignment slack. It reuses the original empty ordinary RW `PT_LOAD` header, appends file data at `0x650000`, and maps it at `0xA30000`—after the existing mapped **memory/BSS** end `0xA228E8`, not merely after file-backed bytes. Original code/data/TLS mappings, the program-header count and the old compressed scenario arena are retained.

```console
python -X utf8 tools/capacity_probe.py
```

The exercised capacity-only output is `build/capacity-probe/EBOOT.elf`, SHA-256 `401c656a719c67cf40b51b2b3fac84b0efaf8824193c5c9df21716aca2f8d485` (10,398,968 bytes). It moves all **1,884** scenarios into a 3,779,832-byte appended arena, retaining original **64-byte starts** and verifying every actual output payload and approved write range.

The opening uses the complete context-reviewed Ittaku alarm-clock sentence: **66 CP932 bytes versus 62 source bytes**, preserving the boundary space across the same two original text items. Actual codec re-extraction verified the four-byte scenario growth, original item ordering/counts, untouched text and all controls/opcode items. No meaning was cut to fit.

This removes the original compressed-slot/arena ceiling for the diagnostic, **not all platform limits**: the allocator still rejects overlap and addresses outside the engine's 32-bit space. Initial loader/grown-opening and ordinary continuation have visual evidence, and the user reports a new spare save loaded successfully. That does not establish old-save compatibility, all-scenario execution or full-game memory/loading/compression requirements.

The historical capacity-only ELF lacks metric-aware layout and keeps `manual_target_ready: false`; do not test it instead. The user tested the paired **`build/vwf-capacity-probe/EBOOT.elf`**: the full English sentence fits across two lines, and another existing same-session capture reaches original Japanese units1–3. Fingerprinted runtime evidence: `work/qa/probe-observations/vwf-capacity-opening-success.json`.

## Unclosed runtime gate

The original combined candidate's save-list overflow remains preserved. The corrected **`build/save-preview-probe/EBOOT.elf`** retains all 1,884 scenario payloads, VWF helpers, fonts and serialized save behavior. The `16_56_54` DataLoad image accepts proportional in-row English preview text and legible Japanese rows/menu elements. The subsequent **“all ok.”** accepts requested same-build loading, page advance/auto/skip and backlog return by user report, not screenshot inference. Evidence: `work/qa/probe-observations/save-preview-visual-success.json` and `save-preview-controls-success.json`. Do not rebuild or repeat accepted checks; this is not all-scenario acceptance.

Runtime/production remain gated. Current pair: **`build/gen-latin-reload-probe/EBOOT.elf`**, SHA-256 `a15f4f08499d7bbc07a5ce19eda0c8a9fccac0274ae4541a8a3acd479765c806`, plus **be72aa943b397ce1d033666b629cdaaf603f1665c3b821ae57897b6a1c0fc1f8** `assets/data.sdat`. Form: `work/qa/gen-latin-reload-results-to-fill.json`: all24 fields unobserved after the corrected reload/selector/UI staging. Navigation/close/reopen, long skip/save, story/choices and every new-font UI surface still need genuine observations; the failed66786e63 pair retains its previous eight scoped passes/16 unobserved fields. Preserve earlier failed pairs/forms and corrupted006/007; never repeat confirmed scrolling merely to reconfirm it. Full-game memory acceptance remains manual.

## Guarded production engine path

`tools/production_engine.py` defaults to the192-site/240-data-patch template plus68 exact source/font-derived Latin/bracket metric pairs. It guards original RX helpers, bounded non-writable R-X UI mapping and supplemental-code hashes. Dialogue59488 and save/music consumer protocols remain original; Gen metrics/pixels are verified together. Projection excludes diagnostic dialogue, verifies all1,884 payloads and keeps64-byte scenario starts.

`project.py check`, `build` and `smoke` automatically select this path only when complete `work/qa/manual-evidence.json` validates. An invalid existing file fails closed; `--engine-growth` explicitly requests acceptance and currently refuses the missing evidence before writing production. Original-slot behavior remains available for the source-only identity/historical diagnostics. Keep the staged template/manifest available; no assembler is needed for production copying.

The current UI/native segment owns PH2 at file`0x650000` / VA`0xA30000`, with8,620 non-writable R-X bytes. Scenarios still select PH3 at file`0x660000` / VA`0xA40000`; do not reuse A3. Native viewport offset`+0x554` lies inside the existing`0x560`/1,376-byte context allocation, adding no runtime buffers or fake logical records. History still grows complete owned payloads and releases overflow/scratch on reset/destroy. Runtime memory fit remains unproved.

Offline smoke: the reviewed 66-byte opening produces the **exact existing diagnostic SHA-256 `6027c7c9221cd79522167218a4bc433a710152db1c7bf83704470a4cc4ff3eed`**. A 1,087-byte replacement for a 42-byte record re-extracts completely with source controls preserved; a separate real `*nnk` record retains its dynamic nickname and wait suffix. Each case verifies all 1,884 payloads. No new ELF was deployed or approved; production remains source-identical. Report: `build/production-engine-smoke/report.json`.

Current projection: `build/gen-latin-reload-probe/projection-smoke.json`; all1,884 original payloads,142 UI strings, approved Latin/bracket metric pairs and exact paired copying pass without diagnostic dialogue. Font proof uses the supplied TPL and actual caller scales; viewport proof brings all1,286 paragraph glyphs intoY52–680 across four views, preserves history/metadata/gameplay state, and exercises older/newer/close/reopen. Signed16/unsigned16 boundaries use explicit adapted cache/origin/scroll fixtures. Long updates and finite font/allocator boundaries remain disclosed; no GPU/full-scheduler/loader or long-session acceptance is claimed.

## Native choice companions and compiler smoke

Native command `0x22` captions originally appeared only inside primary JSON's immutable `opcode_gap`. `tools/choice_text.py` now exposes their text through separate `script_####_choices.json` views and an immutable `work/original-choice-text/` baseline. The one-time extraction prepared 1,335 captions in 115 files; existing scripts, original metadata and `work/original-script/` were not rewritten. Edit only companion `translated_text`, never the duplicated gap bytes.

Compilation rebuilds messages first, then reparses current choice offsets. Literal resizing adjusts VE code size and symbolic label-table targets by cumulative deltas while retaining branch bodies and selection expressions. It rejects labels inside resized literals, 16-bit length overflow, unsupported dynamic captions and the kit's unmodeled direct-offset references. Strict CP932 and ordered native-control guards apply to both surfaces.

The actual `project.py smoke` first hit **2,768 compressed bytes against a 2,764-byte original slot** when adding its choice marker. That rejection was retained as capacity evidence, not avoided by shortening or selecting another record. Before production cutover, smoke now exercises the real appended engine in a separate diagnostic, re-extracting both `[EN TEST] Hello.` and `[EN CHOICE] Go.` and verifying unchanged scenario payloads. The regression suite passed 19 isolated tests after this work.

The retained window/height stage contains11 diagnostic-only edits: nickname/punctuation, the full1,286-byte paragraph, complete reviewed choices and unchanged-branch markers. Its1,884 payloads remain identical through pagination and the current runtime-text correction. The earlier seven pagination/44 layout fixtures excluded the native literal clamp, opacity consumer and bounded live save-text area; passing them did not establish runtime safety. Current expanded evidence is `build/runtime-text-probe/runtime-smoke.json`; runtime fields remain unpassed.
