# Decisions

## 2026-10-23 — Project baseline

- Target: Japanese PS3 **ToHeart2 DX PLUS**, **BLJM60381**. Source is the supplied decrypted `EBOOT.elf` (6,596,336 bytes; SHA-256 `8d8bc60d2b02d12f509a9a3ee9c126876ac8524d4f02c7871206aca9bd66e828`). The installed game's decrypted ELF has the same hash. The encrypted `EBOOT.BIN` is a distinct SELF, not an interchangeable input.
- Use TH2DXP_KIT for scenario parsing, encoding, compression, and available asset tooling. Pin all three requested upstreams in `upstreams.json`; `tools/bootstrap.py` reconstructs ignored `vendor/` checkouts. Adopt the fan-translation-template's agent instructions, glossary, status/decisions/font/RE documents and ignored local assets.
- Adopt translate-retro-game's identity → extraction → marker → translation → QA discipline, **not** its non-PS3 emulator harness. User explicitly owns manual RPCS3 testing. No emulator is launched, installed, configured, or automated by project scripts.
- Keep original input, editable extracted script, immutable extraction baseline, Ittaku material, and outputs local/ignored. Do not automatically stage copyrighted text. Publication requires a reviewed patch-only workflow; no release is claimed at project initialization.

## Safe executable rebuild

At the pinned kit revision, `command_rebuild --use-hash` imports only changed entries, while `repack_entries_into_eboot` starts writing them at `0x29F000`. The supplied source already has scenarios there. Selective relocation can therefore overwrite scenarios whose table entries still point to original locations.

The project wrapper instead rebuilds each changed scenario with the kit codec and compresses it with the required pylzma settings, writes **only within that scenario's original compressed slot**, and updates its original table size fields without changing pointers. It verifies all 1,824 output scenario payloads before writing the output. A record cannot grow, and a compressed scenario cannot exceed its original slot. This deliberately rejects some valid English drafts instead of silently risking unrelated routes. Engine growth, relocation and wider text boxes require separate research and visual proof; never shorten meaning merely to pass this initial gate.

## Initial editorial policy

- Use explicit given-name-first display names and retain honorifics present in the source, following Ittaku's supplied README (translation-style paragraph). These are project defaults, not a claim that the user separately approved every spelling.
- VNDB canonical names/aliases and stable IDs are retained separately from project display names. The merged v20/v90 cast is title-level, not proof of each character's appearance in this PS3 release.
- Use Ittaku's base-game English as contextual reference when recoverable, not automatic one-to-one PS3 alignment. PC Xrated content/version differences and PS3 additions must be checked against the Japanese. Do not carry PC-only scenes into PS3.
- Do not assume an Ittaku permission grant. Keep recovered text local, credit the original team, and resolve redistribution rights before publishing adapted translation.

## Verified already-patched PC reference

A bounded local search located the supplied `SDT.PAK`. Its 3,299,331-byte length and Adler-32 `9C1D5E5E` match the supplied Ittaku VCDIFF target; SHA-256 is `e709dd30f4ff82b83fec30ed9378f1162b3b5a1ec51537beecdffe27a36028f4`. Use it read-only through `tools/ittaku_reference.py index --patched-sdt ...`, rather than applying the patch twice or requiring an unmodified original unnecessarily.

The real KCAP/LZSS archive decoded successfully and yielded 48,424 bounded ASCII text candidates from 775 entries. Index/search retains archive entry offsets and engine controls. These are reference candidates, not verified complete dialogue-line boundaries or PS3 alignments. A damaged archive is rejected by target checksum before decoding. The installed PC archive remained unchanged.

## Pre-translation gate audit — corrected extraction and recovered assets

The raw native index has **1,884** entries. The initial kit scan skipped **60 continuation scenarios**, so the prior 1,824/949 extraction totals were incomplete. `tools/scenario_source.py` now decodes the flag/24-bit chunk length and fails on malformed entries instead of silently skipping them. Recovery added the omitted scenarios while preserving existing translation files; the complete baseline has **1,009** editable JSON files and **182,111** editable records. Native names are retained, including `010301000` for generated `script_0000.json`.

The SDAT prerequisite was reachable without RPCS3. A separately compiled, pinned GPL-3.0 `VelocityRa/make_npdata` recovered `work/assets/data.dat`; integrity/decryption output, size, DAT index and hashes were checked. The installed source remained unchanged. Original TPL font atlases were recovered with TH2DXP_KIT and Latin glyph pixels visually inspected. This supersedes the earlier statement that a decrypted archive was still missing; it does not establish runtime ASCII mapping or layout.

## Separate diagnostic growth from production support

Production stays fixed-slot/no-growth. `build/qa-probe/` marks the first records of native `010301000` with 16 fixed-length diagnostics. `build/growth-probe/` separately tests 86 bytes of true record growth and bounded repacking of all 1,884 scenarios, updating pointers and verifying each payload. Retaining original 64-byte allocation alignment overflowed the arena; the diagnostic tests compact four-byte chunk alignment and remains **experimental**. The original scenario arena is not extended and no native code is patched.

No manual behavior is inferred from decompression success. Native VM control-flow details, ASCII glyph mapping/advance widths, name/choice layout and save compatibility remain subject to actual manual evidence. `tools/gates.py check` must pass before bulk translation; a null/empty results form is deliberately not evidence. User-only RPCS3 launching remains unchanged. Ittaku permission and patch packaging are publication gates, not offline runtime substitutes.

## Historical raw-probe failure and explicit-break candidate

The user reported **Q02 skipped**, backed by sequential Q01 → Q03 screenshots; longer Q05/Q07/Q09 records also overflow. This is ground truth, not a request to rerun merely to confirm timing. The old fixed-byte-length raw probe is now historical failure evidence, not an accepted layout target. Uppercase/lowercase Latin and digits work; layout/page flow does not.

Source audit located the native backslash+n dispatch at `0x6E364` and byte-position/half-width cursor calculations in renderer `0x6DF90`. This proves an existing explicit line command, not a complete native root-cause reversal or a universal ASCII auto-wrap contract. Reproducible read-only audit: `tools/native_text_audit.py` (optional Capstone dependency).

That candidate used `tools/text_layout.py` for conservative 24-column word/long-token breaks and leading no-wait breaks before later changed fragments. It preserved visible characters and original wait/page/opcode items, enforced original record/compressed-slot budgets, and verified all 1,884 payloads. At that stage no native code was patched and no scenario pointer relocated. The initial eight-record experiment exceeded the compressed slot; the successful 12-unit / 16-marker image fit without shortening real translation content. Production builds remained unwrapped.

That opening candidate was `build/flow-probe/EBOOT.elf`, SHA-256 `c051bd3cf61ac4c8bca7c1850dc23ae4cab9294f787aaf6105a3f5daf8e460df`. It subsequently failed in the user's screenshots: post-newline tails and F02/F08 were still missing. Its ELF and failed results remain historical evidence; it is no longer the active manual target.

## Native terminal-span diagnostic — retain the original font

The user chose to keep the game's original font. The local Inter/M PLUS/GenInterfaceJP assessments do not authorize font deployment. No font assets or installed files have been changed.

Renderer `0x6DF90` forces final-span submission for a terminal two-byte character via `0x6E318`, but its ordinary single-byte branch at `0x6E64C` bypasses that test. With `r24 == 0`, `0x6EC50` skips submission; the loop can then exit with pending ASCII unsubmitted. This explains absent unsuffixed F09/F11, visible `\k\n`-suffixed F10/F12, and missing post-newline tails without invoking font coverage or record parity.

The active diagnostic changes only `bne 0x6E9D8` to `bne 0x6E318` at VA `0x6E64C` / file `0x5E64C`: `4082038c` → `4082fccc`. The existing terminal block preserves nonterminal batching and existing flushes; special `'*'` dispatch and original controls remain unchanged. Two independent read-only reviews found no scalar-state clobber issue and confirmed equivalent vector-copy setup.

`tools/flow_probe.py` reproduces the previous failed image hash before patching and writes `build/native-flow-probe/EBOOT.elf`, SHA-256 `b8706df38955e3a98f71dff02ed6f634c64c6f92efb01c3c68ae2a82b1c5ecc3`. Whole-image comparison found differences only within that native instruction. All 1,884 scenario payloads and 16 markers were checked. The original script, fonts, widths and controls are retained for a meaningful A/B comparison.

`tools/native_text_audit.py --scalar-smoke` exercised ten integer-branch cases with Unicorn 2.1.4 and Capstone 5.0.7. Vector-register copies are NOPed only in scratch RAM; replay stops before common cursor/emission code. This establishes the terminal flag behavior, not full-renderer/VM/GPU or manual runtime acceptance.

Production and growth remain unpatched pending actual opening validation. `tools/gates.py` fingerprints the native candidate, preserves earlier forms, and separately blocks bulk until production contains the validated terminal correction. Later screenshots establish restored spans but failed spacing; the partial-result form is not a pass. Do not rerun `TH2_EN_FLUSH.elf` merely to reconfirm those failures. Safe widths, name/choice/backlog/save behavior remain separate checks.


## 2026-10-24 — Preserve original drawing metrics; reject isolated cursor/flower patches

The remaining spacing failure is distinct from terminal submission. Actual ASCII drawing advances by `(metric_second_byte+6)*glyph_scale*position_scale`, while scanner commitment/bounds and several independent flower endpoint paths use `cell_width*glyph_scale*visible_bytes*0.5`. The bearing adjustment must be included when deriving that drawing formula. Original two-byte Japanese advancement already agrees; globally replacing `0.5` would break it.

Retain the original font, glyph placement and terminal restoration. A future diagnostic must use compatible metric-aware measurement for scanner bounds, scalar/vector commitment and normal/wait/final/reposition-all flower endpoints without changing VM byte counts or controls. No one-instruction correction was supported by this trace; no new ELF is staged and no manual rerun is requested.

The existing audit now reproduces original source metric lookup for all 95 printable ASCII characters. Four 64-bit index operations are adapted to equivalent bounded 32-bit operations only in scratch RAM. The initialized-table path is exercised, not fallback initialization. Pen advances are arithmetic models, not native floating-point execution; attempted isolated FP replay trapped. No full renderer/GPU/VM, emulator acceptance or production cutover is inferred. Formulas, native addresses and numeric examples: [`re/README.md`](re/README.md#ascii-advance-mismatch--2026-10-24).


## 2026-10-24 — Base game first, full text and bounded verification

The user requires the entire base game first, with AnotherDays deferred. Preserve the complete Ittaku translation where Japanese context verifies correspondence, translate uncovered PS3 base-game content, and expand engine capacity/layout rather than abbreviating meaning to meet original limits.

The initial 25-turn allowance was subsequently raised to 100, then **1,000 work turns** with explicit user approval. The earlier 25-turn stop no longer applies. Stop sooner for necessary manual runtime evidence or genuine intervention. Use one targeted smoke per distinct engine change and one final `project.py check` → `build` → `smoke`; do not repeat checks on unchanged inputs. Bulk work still requires the existing runtime gate, and original fonts/source/assets/metadata/installations/PC reference inputs remain untouched.

The supplied `ripdog/th2xr-portable` revision is now pinned as a GPL-2.0 reference. Its separately built headless PC bytecode inspector provides real length-delimited `SetMessage2` operands; it is not a PS3 engine implementation or permission to reuse the translation. No portable game engine was launched.

Current inventory explicitly leaves unproved PS3 base-game/AnotherDays membership unresolved rather than treating matching PC filenames, absent references, numeric ranges or cast names as proof. One assistant-context-reviewed opening correspondence is preparation only; no bulk import is approved and no translated coverage is claimed.


## 2026-10-24 — Original-font VWF and appended capacity diagnostics

Implement the user's VWF request by keeping original glyph drawing and changing **geometry-only** scanner counters to design pixels. Integer text/VM byte bookkeeping and original controls stay intact. Use selected-font metrics after command parsing, preserve source coordinate-domain/newline quirks, include ink reservation, and cache width per span for all flower paths. Grow the source span allocation by four bytes; do not reuse byte-progress storage or globally change the Japanese half/full-cell factor.

Keep metric lookup read-only. All four pinned `1D504` font setups supply fallback width 46, so first-use prediction stays consistent across queued font switches without moving the source cache write. Extend RX mapping explicitly into verified zero padding; unmapped padding is not executable by assumption.

The staged VWF A/B retains the known F01–F16 script bytes. The paired capacity target combines identical native code with the complete reviewed 66-byte English sentence and a new arena retaining 64-byte scenario starts. Reuse an empty RW header after existing BSS; do not reclaim unsafe overlap, shorten meaning, or silently enable production relocation. Exact hashes, exercised software proof and manual dependency are recorded in `status.md` / `pretranslation-gates.md`.

Only the new targets are active runtime gates. Preserve historical failures and require complete native/capacity production cutover separately from manual acceptance. Software instruction replay does not prove native FP, allocator/GPU/VM behavior, automatic page-height handling or full-game memory fit.

## Complete PC operands and explicit scenario-scope uncertainty

Use the GPL-2.0 standalone helper plus independent MIT Python reader to retain every encoded PC string operand and provenance, not just one message opcode or printable runs. Keep the C++ helper's license explicit. Normalize per-file read-ID offsets only when unique, contiguous and equally sized; structural candidates never authorize automatic import.

Native title-atlas/callback/date evidence establishes positive startup inclusion. Deferred event slots, calendar conditions and transfer sites are inventoried without claiming complete path feasibility or an exclusive/shared base-game partition. Unknown membership remains in the coverage denominator; unmatched PC names do not identify PS3-only base-game content.

## 2026-10-24 — Scoped VWF opening visual acceptance

Accept the user's six screenshots as evidence that F01–F16 text, the F02/F08 flower endpoints and F09/F11 mixed-fragment placement work in the shown states. The current runtime log ties `TH2_EN_VWF.elf` to all screenshot filenames; current installed/staged hashes match, but no full ELF SHA-256 was recorded at boot. Preserve that distinction in `work/qa/probe-observations/vwf-opening-visual-success.json`.

Record only observed opening cold boot, markers, Latin glyphs and shown-marker no-clipping checks. Leave full controls/punctuation/backlog/name/choice/save and all growth checks unpassed. Do not promote partial evidence, change production or repeat the successful marker test. Proceed to the already-staged paired capacity target for the next necessary manual evidence.

## 2026-10-24 — First-page growth and ordinary continuation observed

Accept the user's `14_44_23` capture as scoped evidence that the combined VWF/appended-capacity target boots and displays the complete grown English sentence without clipping or indicator overlap. A separately discovered same-session capture at `14_44_29` matches original units1–3. Distinguish the user attachment from that existing log-linked image, and distinguish ordinary progression from branching/unrelated-scene coverage.

Record only growth cold boot, full sentence visibility and shown-opening no-clipping checks as true. Leave controls/backlog/branching/unrelated-scene/save-load checks null; startup savedata loading is not a player save/load test. Keep production and bulk disabled, preserve all earlier evidence, and continue remaining checks on the same build without repeating successful initial pages or rebuilding unchanged inputs.

## 2026-10-24 — Save/load report, backlog attribution and bounded save captions

Accept the user's explicit report that a new spare save loaded successfully. The yellow-text capture is **backlog**, as the user corrected, not restored gameplay evidence. It shows the complete English sentence but does not prove backlog return. The save-list capture shows a real overflow, so the historical capacity candidate's overall no-clipping result becomes false. Preserve that failed candidate and its exact-hash form.

The save-caption path uses native fixed-cell renderer `1BE28`, independently of dialogue layout: ASCII advances 25 pixels at its original scale. Correct only its two draw calls through a private copy using original proportional ASCII metric arithmetic; retain original Japanese drawing and punctuation behavior. Bound actual cell quads to the source row's conservative inner-right edge, X=1010. For unusually wide excerpts, use the existing CP932 ellipsis on a whole-character prefix in the **temporary display buffer only**. Never shorten dialogue, change the serialized excerpt writer, alter saves or replace fonts.

Stage a distinct diagnostic and fresh growth evidence row. Earlier successful opening/save-load observations remain attributed to their original build, not silently repinned to new native code. The next manual check is the corrected save/load list with the existing English spare slot and Japanese rows; production and bulk remain gated.

## 2026-10-24 — Scoped corrected save-preview visual acceptance

Accept the user's `16_56_54` DataLoad capture as evidence that the corrected slot005 English caption has proportional spacing and stays inside its row, while shown Japanese rows/menu elements remain legible. Bind it to the logged `TH2_EN_SAVE_UI.elf` boot, same-session screenshot and matching current installed/staged hash; do not claim a full ELF hash was captured at boot.

Record only direct ELF startup reaching the menu and the shown save preview as new growth-row passes. Leave full-dialogue visibility/clipping, save/load, controls, backlog return, branches and unrelated scenes unobserved on this build. Preserve the previous candidate's failure and earlier save-load/backlog attribution. Continue remaining checks on the same diagnostic without a rebuild, repeated preview check or save overwrite. Production and bulk remain gated.

## 2026-10-24 — Reported controls acceptance and guarded full-length production assembly

Treat the user's “all ok.” as acceptance of the immediately requested same-build spare-save loading, page advance/auto/skip and backlog open/return. Attribute these passes to the conversation report, not the earlier menu image. Do not invent a follow-up timestamp, full-dialogue screenshot, branch/scene/name/choice pass or whole-game approval. Do not repeat accepted checks.

Implement the real production engine path without enabling it prematurely. Copy only source-guarded native instructions, RX mapping sizes and the complete injected cave from the exact SHA-pinned diagnostic; reconstruct every scenario from original or validated translated units. Never copy the diagnostic's English into production implicitly. After complete manual evidence validates, ordinary check/build/smoke select full-length VWF plus appended 64-byte capacity. Invalid evidence fails closed, and explicit `--engine-growth` rejects missing acceptance before production writes. Source-only identity and historical diagnostic builds retain their original-slot path.

Preserve native inline protocol, not merely backslash escapes. Source `6E34C..6E8C4` also handles angle tags and `*nf/*nl/*nn` kana/length variants plus `*h2`. A reproduced lost-nickname acceptance is fixed by ordered control-token validation. Reject CP932 round-trip changes rather than silently changing Unicode punctuation. Offline proof reproduces the existing reviewed diagnostic exactly, retains a 1,087-byte record and preserves a real dynamic-name record; native code and user files are not changed by these smokes.

## 2026-10-24 — Native choice companions without baseline mutation

Expose source-bound command `0x22` caption operands through separate `script_####_choices.json` text views and immutable `work/original-choice-text/`, not edits to existing primary scripts' opcode-gap metadata or `work/original-script/`. The one-time preparation adds 1,335 captions across 115 companions; all remain source-identical. The inventory denominator now includes 183,446 records across 1,124 editable JSON files. Existing message read-marker candidates do not align choices automatically.

Rebuild messages before reparsing choices, retain full strings and the source's controls, and update symbolic label targets by actual growth deltas. Reject ambiguous labels inside resized operands, unsupported dynamic captions, format overflow and unmodeled direct offsets. Preserve selection expressions and original branch bodies. An original-slot smoke overflow of four compressed bytes is a capacity finding, not a reason to shorten the marker or translation; use the real appended engine for the separate offline diagnostic while production remains gated.

## 2026-10-24 — Case-scoped acceptance and explicit page-height stress

Retain four opening-marker checks on their observed opening artifact and five accepted control/menu checks on the corrected save-preview artifact. Assign the genuinely unexercised name, punctuation, full-growth visibility/clipping, height, choices, branch and unrelated-scene requirements to one new window diagnostic. Do not silently transfer passes, repeat accepted cases or fill unknown fields from software evidence.

Preserve the earlier `windows-probe` output, but use **`build/windows-height-probe/EBOOT.elf`**, SHA-256 `9c0b32374aa597dc9d6de58db8a4795ff28c05dc85847a7ef4c0678ddcad0ba1`, as the pending target. It contains a 1,286-byte H01–H08/HEND paragraph without added engine controls, real nickname/punctuation cases, complete context-reviewed PC choices and markers on unchanged original branches. Native code remains the accepted-control template's code. Successful insertion and branch-byte preservation do not prove pagination, visual fit or branch execution.

Stop the manual sequence at missing/clipped/unreachable height content; proceed to choices only if height passes. No personal save overwrite or repeat of accepted controls/save-preview is required. The user subsequently directed continued offline work without waiting for RPCS3: investigate source-supported pagination and membership gaps independently, without inventing runtime acceptance, shortening meaning or bypassing the bulk/production guard.

## 2026-10-24 — Recover missed graph evidence; do not guess pagination

Correct the bounded source scanner rather than classifying its two unmatched frames as harmless or promoting a clean census to full VM proof. Local-variable06 includes its index byte; direct assignment43550 leaves02 for VM dispatch, while operand43ED8 advances it separately. Source-bound fixes recover the flag write at `script_0042.json` payload+5478 and scenario load at `script_0761.json` payload+255. The complete-source inventory now has 13,246 transfer sites / 9,465 state-effect sites / zero unmatched supported-command frames. Synthetic regressions cover token-like indices and the shared assignment terminator; all21 tests pass. All1,335 choice views remain source-identical. Edition memberships remain unresolved instead of being guessed from the repaired graph.

Continue automatic-height research offline using the actual staged paragraph, not a shortened fixture. Its encoded scanner replay preserves all1,286 bytes and emits36 spans reaching Y1,680 without wait/page/end flags at heights144 and628. Record the initial instruction-cap stop and finite fixture-only extension honestly. Source constructor defaults do not establish a live dialogue viewport; the source `\p` flag includes a hexadecimal duration, not a proven page-clear protocol. Existing clear6DE5C deletes the whole queue, so do not add a speculative clear that could discard unread text. Keep runtime evidence null, production unchanged and the full-text requirement intact.

## 2026-10-24 — Preserve unread queues for native automatic pagination

Use the source renderer's wait/resume protocol, not inserted script controls or whole-queue clear. A dedicated context+550 pointer records the last fitting baseline row; allocation grows550→560. Completed-page advance unlinks/frees only its consumed prefix, rebases unread nodes/cursor/flower, and keeps raw source-byte progress unchanged. Saved raw checkpoints reconstruct later pages and account consumed state2 spans once. Backlog/special contexts and earlier explicit waits retain native behavior.

The actual pagination builder passed seven encoded cases, save restoration/clear/backlog checks and all44 layout cases while preserving every one of1,884 diagnostic payloads. The full1,286-byte paragraph is never shortened. The complete template now has48 guarded sites/3,724 helper bytes; `build/pagination-probe/EBOOT.elf` hash41508616beb8394ccd664a62e05c4b3aa79853fc77640a1512bddd939bd5814d supersedes only the pending manual target, not prior evidence/artifacts. Native GPU/FP/full-VM behavior and a row intrinsically taller than the viewport remain limits, not claimed passes. Production still requires genuine exact-build evidence.

## 2026-10-24 — Resolve normal-title routing ownership, not per-route feasibility

Classify from all four original title choices and native dispatch effects, never numeric ranges, PC presence/absence or an opening closure alone. ToHeart2 starts month3, AnotherDays10, Ikuno21 and Konomi/Tamaki20. Audit all constructor/load ingress and literal script/deferred-slot loads; reject computed ingress or unknown month effects. Include command63 unconditional jumps and command86 local-to-global copies. The base May20 morning terminal, paired date writes, forward-only terminal exits and native GOTITLE callback prevent calendar drift into AnotherDays.

`tools/scenario_membership.py` records normal-title source routing ownership, explicitly not individual conditional-route feasibility. The actual integrated inventory resolves all1,884 entries:1,271 base-only,496 AnotherDays,1 base-shared and116 other; base denominator1,272 scenarios/102,062 editable records. AD/standalone shared content without base ownership stays deferred, retaining every owner. Other retains separate stories and44 inactive/debug programs; nothing is deleted or declared globally unreachable through replay/modified saves/numeric boot.

Membership is no longer a coverage blocker. Zero translated/completeness-reviewed records means inventory still exits1; native layout/runtime/bulk gates remain independent and unchanged. Continue reachable offline work without waiting for RPCS3, inventing acceptance or importing unverified PC candidates.

## 2026-10-24 — Bind message review preparation to resolved base ownership

Use the complete native membership report to select base/shared-base scenarios before proposing PC message correspondences. Reject stale source/payload identities, missing/duplicate/unresolved scope and ownership/status contradictions; verify selected immutable baseline hashes. Preserve prior all-source outputs and stage a new base-only queue, never overwrite/import them.

The actual preparation command accounts for101,829 base-message IDs exactly once, with no other-story leakage. The233 native choice captions remain explicitly outside message-marker analysis. Structural matches stay context-unverified, route feasibility stays unproved, and automatic import stays disabled. Three focused scope regressions pass; production/runtime/bulk gates are unchanged.

## 2026-10-24 — Never equate unchanged text with reviewed English

Fix the reproduced case where generic translation completeness accepted unchanged Japanese. A changed record may receive exact-hash completeness review; unchanged text must instead have an individually attributed name/token exception with supported category, rationale and original/current hashes. Do not auto-exempt punctuation/names or permit duplicate translation/exception claims.

Keep reviewed translated and explicit-exception counts separate; both contribute to covered records, but exceptions never inflate translation counts. Coverage report schema3 replaces the old untranslated/potential-base aliases with `uncovered_base_game_records`. Six focused regressions, direct before/after replay and the complete actual inventory exercise the new path; real coverage remains zero, not silently promoted. Production/bulk/runtime guards remain unchanged.

## 2026-10-24 — Correct native long-text corruption, not story branding

Treat the ten supplied screenshots, wrong-opening report and skip black screen as failures of41508616... . Authorized read-only inspection binds slots006/007 to base programs while English bytes overwrite month/day/phase108/121/32. Native branding then selects AnotherDays. Do not force base branding, blame the user's selection, repair saves or alter source ownership to hide the corruption.

Fix three independent assumptions: move/expand all32-byte opacity producers and consumers to256 entries with an owned zero predecessor; relocate the VM scratch to a full65,536-byte area and preserve every u16 literal byte/cursor advance; replace unbounded inline checkpoint copying with bounded source-verified references, retaining legacy inline decoding. Modified scratch text cannot masquerade as an immutable reference. Keep the fixed save-slot size, but explicitly disclose extended entry semantics and same-build scenario-offset dependence.

Stage `build/runtime-text-probe/EBOOT.elf`, SHA-2566da9f08969688de1faa9fc8f0566122105e92065d01f324ab85dbf5089006206, without changing any of1,884 diagnostic payloads. Actual encoded parser/opacity/native skip and restore paths pass; native-only production projection retains all original payloads and replays an actual Japanese literal. Preserve failed ELF/forms and prior scoped passes. Add exact-build story-state, long-text skip and long-text save/load requirements rather than inherit old short-run acceptance.

No runtime recovery is claimed. Fresh New Game and disposable same-build saves are needed for corrected-build observations; corrupted006/007 are evidence, not migration inputs. Native history-ring behavior, GPU/native FP/full VM and full-game memory remain limits. Production and bulk translation remain gated; no emulator, installation or save is modified by tools.

## 2026-10-25 — Original-font typography and UI before dialogue

Keep original font assets. Correct the glyph backend's inclusive-to-edge conversion for both screen and UV right/bottom coordinates before the existing matrix transform, retaining the packed queue ABI. Still-image comparison alone did not prove which pixels caused the reported `g` appearance; encoded vertex replay establishes the independently verifiable one-unit cell shrink and its correction, not a GPU pass.

Reserve a fitting whole word using the existing read-only font metrics and shared scalar/vector bounds. Do not insert script newlines, consume extra bytes, or independently force only one overflow predicate. Native controls delimit runs and overlong tokens keep character fallback. Skip lookahead while the native angle-command flag is active: an initial replay caught duplicated numeric operands when wrapping command contents; the guarded version preserves the actual font/control state.

Stage the distinct typography hashce9da83e005d999e33966e45d449ac04d574cec867219fbb5176873826bb0f4c and preserve all earlier builds/forms. Eleven word cases, three glyph scales, full long-text checkpoint replay and native-only projection pass. Require exact-build descender/word-wrap observations rather than inherit old passes.

The user now prioritizes translating and redrawing the base-game UI before full scenario translation. Work on staged UI assets/labels with Japanese correspondence and native-use provenance; do not treat this as permission to deploy, edit installed files, shorten meaning, replace fonts or bypass scenario/runtime gates. AnotherDays dialogue remains deferred.

## 2026-10-25 — Readable UI requires a paired native/atlas cutover

Keep complete English and original font assets. Use uniform glyph scaling and whole-word lines, never horizontal squeezing or truncation. Main raster labels require14px or more; only rotated calendar captions may use12px (current minimum13px). Repack the13 footer cells at20px and give music-role words96px source banks at16px rather than force full words into the old32px fields. Relocate native source/destination geometry with those banks; retain original24px music titles and use the existing0.35 artist scale.

Bind142 translated native strings to source bytes/references and keep six personal defaults/name-dictionary values untouched. Preserve ordered printf arguments, `%d0` suffix semantics and private glyphs. Replace fixed label/help copies with complete read-only pointers, not shorter wording. Guard native/data/string mappings together. UI owns PH2 atA30000; scenario relocation chooses PH3 atA40000 rather than overlapping it. All1,884 diagnostic payloads remain identical, and the production projection retains all1,884 original payloads without diagnostic dialogue.

Use both user-requested VGMdb albums (1938/26275) as source-context references, not permission to import CD-only arrangements or overwrite PS3 roles. Direct access is403/Cloudflare; cached exact-URL MusicBrainz relationships and Japanese correspondence retain provenance for all51 PS3 rows. Correct 豆田将 to Susumu Mameda, keep credited-as aliases and all204 native role bindings. No music is changed.

Preserve the first packer failure rather than accept warning-bearing output. A separate exact-source GPL derivative repairs update-mode forging, ciphertext authentication, metadata-before-header CMAC order and final padding; vendor/decryptor files stay unchanged. That earlier pair's header/metadata/all134,125 block authentication and complete DAT decrypt/SHA proof passed under `build/ui-readable-probe/`, including temporary production-asset copy. These offline passes did not establish native loading; the later runtime failure below supersedes its pending acceptance target.

The initial UI form left23 window checks unobserved and preserved older hash-scoped passes. Source-size previews/native software replay were never full PS3 acceptance. Later user evidence records failures on that exact pair; do not erase those observations or treat initial null fields as current passes. Scenario translation, production cutover and publication remain gated.


## 2026-10-25 — Fix native asset/caller contracts exposed by UI testing

Accept all five new screenshots as failures, not missing setup or a font-replacement problem. Current installed hashes match the logged cb7864/9a5fe4 pair, with no complete boot-time hash claim. Preserve screenshots/logs/form under `work/qa/probe-observations/ui-runtime-failure*`; do not request another run of that failed pair.

Reuse the native-compatible scenario codec for DAT replacements:8-KiB dictionary, explicit per-chunk output size,32-KiB stride and EOS-free encoding. The vendor DAT compressor's unknown-size/8-MiB streams roundtrip in Python but EDGE rejects size-1. Validate header/flags/padding/known-size decoding and actual replacement bytes, not merely a Python ALONE success. Stop decoding at the declared output size: probing an EOS-free range flush for one more symbol falsely rejected a valid real chunk; the deterministic LCG regression now covers this.

Restore59488's original fixed-cell submission because594E8 already computes proportional, bearing-adjusted per-character positions. Retain raw option-value proportional calls, typography endpoints/word wrapping, save-caption behavior and original fonts. Composed encoded glyph replay reproduces `i/c` gap16 and corrects it to6, including the full opening/mixed Japanese/descenders at three scales. Measure/draw name help through its actual centered-text path, not a synthetic complete string at59488.

Stage the distinct90046ed1... ELF with its c4898391... SDAT under `build/ui-native-probe/`. All83 regressions,2,148 native-compatible replacement chunks, full archive authentication/decryption, native-only source projection and actual temporary asset copy pass. Source backups are read-only and fully SHA-checked before/after staging; never restore an installed archive automatically. New23-field runtime results remain unobserved and both hashes are required. Old failures and production/bulk guards remain intact.


## 2026-10-25 — Correct both backlog ownership limits and native UI tracking

Treat the reported backlog crash and tight-text screenshots as failed90046ed1/c4898391 evidence. The exact `. Ad`→object-list-head→2E204178 source/log match justifies fixing full scratch ownership, not suppressing the fault. Also remove unchecked840-byte aggregate history capacity. Preserve native100-slot grouping/retirement, use inline/growable owned payloads, resolve every reader/writer, and release overflow on destroy/reset. Scanner scratch owns the entire string until synchronous scan completes; source span allocation/copy proves subsequent text ownership. Never clamp, drop entries or prematurely roll records to hide length.

Keep original fonts and complete wording. UI ASCII tracking increases by4 before original scale/round with matching draw/measure. Check actual help scales/panels and slider bounds; reflow only words. Preserve fixed Japanese, accepted save captions and Music’s measured column/font contract. Supplemental helpers share the non-writable R-X UI mapping with exact code/payload hashes; loader/memory acceptance remains manual.

Stage `build/ui-backlog-probe/` with83c58c0f... ELF and byte-identical c4898391... SDAT. Reuse existing authenticated textures only after matching all graphic hashes and copied ciphertext SHA; do not rerun unchanged compression/crypto or claim new decrypt results. Preserve original failed forms and generate24 null current-build checks, including backlog.84 regressions, native fault/corrected-path replay, source-only projection and real paired staging pass offline; runtime acceptance and bulk translation remain gated.

## 2026-10-25 — Complete backlog entries must not inherit retired queue ordinals

Preserve the seven23:32–23:36 screenshots/logs and83c58c0f/c4898391 pair. Gameplay reaches HEND with complete whole-word pages/visible descenders, but backlog shows only the first N01 clause and a blank icon. Record eight scoped old-build passes and backlog=false, not a new crash-free/navigation/UI/save pass.

Latest-record scanner6A284 requests ordinal reveal inheritance. Native constructor6DAFC/6DD30..6DD94 reads the current gameplay queue, whose prefixes pagination has retired/rebased; missing/mismatched ordinals leave zero or partial progress. Mode1 does not increment reveal, and common draw stops at an unfinished span. Select the existing completed-record behavior with `li7,0` at6A284 instead of inventing a second queue-progress protocol. Tradeoff: backlog fully shows the current recorded logical entry, including its as-yet-unshown pages; no future/unrecorded entry is added, and gameplay read/checkpoint/progress state is unchanged.

Stage a distinct `build/backlog-render-probe/` (62bdc049... ELF/c4898391... unchanged archive) and24-null `backlog-render-results-to-fill.json`; retain all earlier artifacts/forms. Native constructor, glyph generation, nonzero cached opacity and backend queue must be exercised, not merely stored strings/span counts. Replay permits native fade-in; full-paragraph updates isolate spans before complete-list draw traversal. Font/allocator fixtures, memoized native metrics, limited unused-VMX-lane handling and lack of GPU/full-scheduler proof remain explicit.

Inter consideration is canceled; the selected GenInterfaceJP-0.8.1 comparison remains offline under the original-font boundary. Font choice is not the backlog correction or authorization to alter protected atlases. Full translation/production still requires genuine exact-build acceptance.

## 2026-10-26 — Approved Latin font cutover and complete backlog viewport

Preserve the62bdc049/c4898391 screenshots/logs and scoped failures. Original g row46 is sampled; no source evidence justifies another arbitrary quad/baseline correction. The user's explicit **Use GenInterfaceJP for Latin** supersedes the original-font/comparison-only boundary for62 letters/digits and their shared full-width aliases. Use the supplied Regular font at48px em/baseline37, quantize to native R4, derive a/b from actual ink and bind font/OFL/TPL hashes. Preserve Japanese/punctuation/private cells and metrics, encoding/control bytes, full meaning and immutable sources. Native help/options/dialogue use b+6; save/music retain b+2. Redraw complete English UI words from the same masks/advances, never squeeze/truncate.

Full-record reveal is not viewport access. Source69FE8 changes whole records, so consume source older/newer controls within a tall entry first. Store scroll only in owned`+0x554` padding inside the existing`0x560` context. Reconstruct cached short Y from float span origin, clip full text/icon cells toY52–680, then preserve native record navigation and reset/reopen behavior. Do not split history, drop text, advance gameplay or alter progress/voice/metadata.

The cached consumer must patch59450's Y load, not5944C's colour load; collector checks actual submitted RGBA. Far conditional icon branches need local conditional/unconditional trampolines with signed displacement guards.70E40's displaced clrldi must be replayed, not a duplicate store. Preserve those ABI contracts and non-writable R-X ownership.

Stage a distinct66786e63... ELF/a660c827... SDAT under `build/gen-latin-backlog-probe/`.85 regressions, supplied-TPL native sampling, all1,286 viewport glyphs/navigation, source-only1,884-payload projection and complete new archive authentication/decryption pass offline.20 native-size UI previews and the native-sampling sheet were inspected. Signed-coordinate cases use explicit adapted fixtures, long updates isolate spans, and no GPU/full-scheduler/controller or long-memory acceptance is claimed. New24-field form remains null; old passes/failures retain original hashes. Full translation/production/publication remain gated.

## 2026-10-26 — Corrected reload, selector and readable-UI pair

The authorized same-version reload of66786e63/a660c827 faulted in native decoder28D9C at reads5DAA/20A3. Preserve that pair, its save snapshot, logs and scoped gameplay successes. The source caller44928–44934 is authority: R4 receives the output size and R5 the compressed pointer, the reverse of the former replay helper. Correct the helper's two loads and guard the immutable caller; do not alter the native decoder, save contents or already-corrupted state. The save is read-only evidence, and the replay must enter the decoder through both the injected call path and direct edge fixtures.

The two-state selector at8F730 is dynamic rather than a static label site. Keep the native `.7`/`.5` scales and centered measure ABI, but place expanded values at origin+653/+919, end the selected panel at+1099 and put arrows at measured half-width+33 so the48px pulse keeps at least8px clearance. Change only the source-guarded instruction words; no new buffer, data table or ABI.

Gen Regular masks already carry the intended stroke, so applying the source font's `MaxFilter(3)` dilation again closed counters and emboldened map/footer labels. Use the supplied stroke for Gen mappings only; keep original-font behavior. Re-letter Next at17px with3px padding inside its unchanged frame (source ink147,59–182,77 inside erase rectangle145,57–190,78). Rasterize at47px em/baseline37 so i/j dots and g/j/p/q/y retain a transparent border. The six `()[]{}` aliases are the explicit scoped punctuation exception: replace them from the same face on a common source-derived optical axis (+1px); other punctuation, Japanese/private cells and unrelated packed bits remain untouched.68 metric pairs (62 letters/digits + six brackets) are guarded.

Stage the distincta15f4f08... ELF/be72aa94... SDAT under `build/gen-latin-reload-probe/`.88 synthetic tests, all six native replays,200 instruction sites/240 data patches/68 pairs, all1,884 payloads,3,505 preserved archive entries and complete DAT authentication/decryption pass offline. The new24-field form starts null; old scoped passes are not transferred. `gates.py check` exits1 with production cutover and genuine manual evidence still blocked. No runtime, GPU, save-format, branch or full-game-memory acceptance is claimed.


## 2026-10-26 — User-supplied translation reference and line fidelity

The translation prompt is retained in full in `docs/ittaku-reference.md#user-supplied-translation-reference`. Resolve subjects, predicates and pronouns from surrounding context; use natural, vivid colloquial English unless the source voice requires another register. Preserve details, intensity and readable sounds/interjections without sanitizing or embellishing them. Translate natural language only; leave variables, escapes, tags, IDs, paths and other non-language tokens intact.

One original native editable text item requires one corresponding English fragment. Preserve item count/order, incomplete continuations, inline controls and original suffixes; never merge neighboring lines or add script breaks to imitate PC wrapping. Context informs meaning, not permission to move whole utterances between records. The rule does not authorize PC-exclusive content, guessed edition correspondence or a runtime-gate bypass.

The user reports that another model solved the engine/UI issues. Resume private editorial translation without reopening those fixes. This report is not silently expanded into24 individual exact-build observations: production acceptance remains governed by the existing evidence contract.


## 2026-10-26 — Explicit bulk editorial authorization

Asked whether to override the pre-bulk runtime gate for private drafting only; the user selected **Proceed with bulk editorial translation**. Continue every source-bound base-game message and native choice, including PS3 base content without a verified PC counterpart. This explicitly permits bulk editorial work before runtime acceptance; it does not turn the blank24-field form into evidence or authorize production insertion/builds. Preserve the prior exact-build failures and runtime/production guards. AnotherDays and separately owned stories remain deferred; absent PC matches do not prove exclusivity or permit dropping PS3 text.

## 2026-10-27 — Focus private-draft checks on changed inputs

The user requested trimming checks that delay progress without protecting correctness. Private draft assembly now checks only its actual selected script or parent/choice pair, not a copied full editable workspace. Replace parent validation-receipt dependence with direct source, text/control, metadata and native reconstruction checks. Keep substantive source/revision binding, base scope, complete per-item meaning and boundaries, CP932, controls/private glyphs, non-text preservation, relocation and codec round trips.

Do not automatically repeat whole-corpus reviews, unchanged native/UI/crypto diagnostics or progress/hash bookkeeping for each batch. Optional wording/cultural-gloss questions and absent administrative receipts do not invalidate valid output or block unrelated private drafting. Known definite defects still need targeted correction; this does not relax semantic fidelity, exact-text review, production/runtime gates or actual insertion/build checks. Translation remains in the current Sol6.1 session with no added workers.

## 2026-10-27 — Self-contained installer for the user's own installation

The user chose to ship an installer that works from the installed game folder alone, with the required decryption material built in. `dist/th2dxp_patch_gui.exe` therefore decrypts the folder's own retail `EBOOT.BIN` with the single BLJM60381 application keyset, applies a hash-pinned executable diff, decrypts `data.sdat`, appends the eleven compressed replacement chunks, and re-encrypts the archive. No pre-decrypted `EBOOT.elf`, no build directory and no Python installation are required of the player. This supersedes the earlier `dist/th2dxp_patch.exe` contract, which installed a locally produced pair.

The keyset is Sony platform data. It is taken from public PS3 research (`RPCS3`, GPL-2.0, `Crypto/key_vault.cpp`), carries no Sony code, is used only on the operator's own lawfully obtained copy, and is disclosed in `NOTICE.md`; the `data.sdat` path needs no key beyond what the pinned GPL `make_npdata` already contains. Both `make_npdata` helpers are embedded but invoked as separate child processes under pinned SHA-256 (`662fd552…`, `81c2cd3a…`), remain GPL-3.0 with corresponding source published here, and travel with their license text. No game data, no decrypted executable and no keyed material of another title is distributed.

A rebuilt archive **cannot** be hash-pinned. `make_npdata-pack`'s `forge_npd_title_hash` CMACs the `content_id` together with the input DAT path string as typed and the block keys derive from that `dev_hash`, so identical DAT bytes re-encrypt to different archives on different machines. The installer therefore authenticates the new archive (`--verify`), checks its NPD/SDAT header fields and size, then decrypts it back and requires the pinned DAT `0438c3af…`. `output_sdat_sha256` in the patch manifest documents the build machine's archive only; the journal records the archive actually installed, and that journal — not a container hash — is what recognises a previous install.

Patch data (`build/patch-data-v0.1/`) is the authoritative shipped payload: 255 merged executable edit runs (38,865 bytes) plus the appended 4,091,272-byte segment, and 19,485,820 bytes of pre-compressed archive chunks with their eleven table rows. Everything is verified against the pristine input before a single byte is written, work files live in `USRDIR/.th2dxp-work`, and both originals are copied byte-exactly into `USRDIR/.th2dxp-backup` with their hashes journaled first. Offline success here still proves nothing about rendering, pagination, saves or memory; the 24 manual checks stay unwritten.

The player is asked for exactly one thing: the installed game folder. The patch-data folder those files live in is embedded in the executable (`_MEIPASS/patch-data`, with the two helpers under `_MEIPASS/tools`), located by `patch_engine.default_patch_dir()`/`search_roots()`, and is never requested, remembered or browsed for. The former "Patch data" row, its Browse button, the `build_dir` setting and the writable override were removed rather than merely defaulted, so a stale path from an older release cannot redirect an install; a legacy `build_dir` value in the existing settings file is dropped on load. If the embedded data is missing or damaged the program now fails closed and tells the player to download the executable again. Frozen builds still recognise an unpacked `patch-data` folder beside the program for development, but no shipped path depends on it.
