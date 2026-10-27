# Pre-translation gates

Bulk translation remains blocked until `python -X utf8 tools/gates.py check` exits zero. No tool launches RPCS3 or modifies an installed game.

## Confirmed failure, not a timing question

The user's screenshots and explicit report establish that the old Q02 record was skipped when advancing Q01 → Q03. Q01/Q05/Q07/Q09 also lose or overflow long text at the right edge. The old probe proves uppercase/lowercase Latin, digits and mixed `IiLl` / `WwMm` glyphs work; it does **not** pass layout/page handling. Do not ask the user to reproduce that failure again merely to confirm it.

Evidence: `work/qa/probe-observations/opening-flow-failure.json` (six screenshot hashes). The previous raw ELF and old results form remain historical failure evidence, not the active acceptance target.

The replacement explicit-break probe also **failed**, confirmed by seven later screenshots: F01/F05/F07 lose their post-newline tails, F02/F08 disappear, and short unsuffixed F09/F11 are absent while suffixed F10/F12 render. Evidence: `work/qa/probe-observations/flow-break-failure.json`; `work/qa/flow-results-to-fill.json` preserves failed checks. Do not rerun either failed build merely to reconfirm these observations.

The later pagination-only build **also failed**. Ten23:30–23:35 screenshots show faded/missing N01/P01 glyphs, H07 truncation and AnotherDays branding; the user reports a black screen after skip. Authorized save inspection finds base program IDs but English bytes in date/story flags. Evidence: `work/qa/probe-observations/pagination-runtime-failure.json`. Preserve41508616... and corrupted slots006/007; neither is a corrected-build test input.

The first UI pair **also failed**: five18:22–18:23 captures show gray sprite rectangles and internal-word glyph gaps. Read-only boot/screenshot logs and current installed hashes bind them tocb786434... /9a5fe46e... . TTY reports EDGE LZMA output size-1. Exact evidence: `work/qa/probe-observations/ui-runtime-failure.json`. Do not repeat that pair; its crypto/desktop-preview passes did not validate native decompression or the composed dialogue caller.

## Current manual target — corrected GenInterfaceJP UI, selector and reload pair

Earlier acceptance retains its original hashes. The current diagnostic is `build/gen-latin-reload-probe/`: the user-approved GenInterfaceJP letters/digits plus six bracket aliases, matching native metrics, readable English UI, separated option values and the corrected saved-literal decoder. Original other Japanese/punctuation/private pixels, native history grouping and all1,884 diagnostic payloads remain intact. The06:46–06:47 captures reject62bdc049 for incomplete g appearance and bottom overflow; the13:56–14:05 captures reject66786e63/a660c827 for a save-reload crash and UI defects. Preserve their scoped passes/failed fields without transferring them.

| Run | Staged ELF | SHA-256 |
| --- | --- | --- |
| VWF opening A/B | `build/vwf-probe/EBOOT.elf` | `98160309175568d4c98136003371dfaab396be1a848d9f1324be5519ef9b693e` |
| Same full-text growth + save-preview correction | `build/save-preview-probe/EBOOT.elf` | `6027c7c9221cd79522167218a4bc433a710152db1c7bf83704470a4cc4ff3eed` |
| Failed pagination-only target; retain, do not repeat | `build/pagination-probe/EBOOT.elf` | `41508616beb8394ccd664a62e05c4b3aa79853fc77640a1512bddd939bd5814d` |
| Previous long-text target; typography issues reported | `build/runtime-text-probe/EBOOT.elf` | `6da9f08969688de1faa9fc8f0566122105e92065d01f324ab85dbf5089006206` |
| Retained typography input | `build/typography-probe/EBOOT.elf` | `ce9da83e005d999e33966e45d449ac04d574cec867219fbb5176873826bb0f4c` |
| Failed first UI pair; retain, do not repeat | `build/ui-readable-probe/EBOOT.elf` | `cb7864346118666f977d0f7793d9edb990de9cab65609669977b8b5ff70849cd` |
| Previous UI target; backlog crash/too-tight tracking reported | `build/ui-native-probe/EBOOT.elf` | `90046ed1a110e6f13a3d3fd99829b54d9bdc03f12b9cde30908292ab6f9752ab` |
| Previous target; gameplay pages shown, backlog text incomplete | `build/ui-backlog-probe/EBOOT.elf` | `83c58c0f01029c8643a01272af457ac036335b2d25c0c3997a4a84c6aea9f7be` |
| Previous reveal-only target; g appearance/bottom overflow reported | `build/backlog-render-probe/EBOOT.elf` | `62bdc049a5c46888460a0cb488e6b3a62e5d7eb149761ae6191a45870c18bd7a` |
| GenInterfaceJP Latin and whole-record viewport target; reload/UI failures retained | `build/gen-latin-backlog-probe/EBOOT.elf` | `66786e6314959ef59e01e4bdfde87cab98a8c6b50ce65bc544f0dc6a8a32a108` |
| Corrected reload/UI/selector target | `build/gen-latin-reload-probe/EBOOT.elf` | `a15f4f08499d7bbc07a5ce19eda0c8a9fccac0274ae4541a8a3acd479765c806` |

Only68 cells and their exact source-derived native metric pairs change: the62 letter/digit aliases plus the six shared `()[]{}` aliases. Full-width Latin and bracket aliases share those cells. Other Japanese/punctuation/private glyphs remain unchanged; those six bracket aliases are the explicit punctuation exception. The existing complete-cell endpoint, word-lookahead, opacity, full-u16 scratch and bounded-checkpoint corrections remain included. Tagged saves still require the corrected reader and the same scenario build.

The corrected ELF pairs with **`build/gen-latin-reload-probe/assets/data.sdat`**, SHA-256 **`be72aa943b397ce1d033666b629cdaaf603f1665c3b821ae57897b6a1c0fc1f8`**, in **`work/qa/gen-latin-reload-results-to-fill.json`**. This is a newly rebuilt/authenticated archive:10 UI TPLs plus the main font TPL. All11 replacements re-extract exactly,3,505 other entries/original bytes remain intact, and original-tool decryption matches the complete2,200,458,952-byte staged DAT. The a660c827 and c4898391 archives are incompatible with this font/metric pair. Keep the supplied staged OFL notice; no release is authorized.

The corrected pair changes only source-derived/code-bound material. The saved-literal helper passes decoder28D28 R4=size and R5=pointer (the failed model reversed them); authorized slots005/010 replay their recorded references without modifying saves. Selector8F730 separates expanded values at origin+653/+919, ends the selected panel at+1099 and clears the48px pulse by at least8px; collapsed values stay .5 scale. Gen Regular mappings keep their supplied stroke (no synthetic dilation), Next is17px/3px padding inside its unchanged frame, and the six bracket aliases share a +1px optical axis at47px em. Map/footer labels remain24/20px. Offline replays cover the native selector/timer path, Latin pixels/68 pairs, history/backlog/view and the saved decoder; none of this is runtime acceptance.

The historical save-preview growth target preserves all1,884 of its input payloads and the complete reviewed66-byte English sentence versus62 source bytes; its change was limited to save-caption code/RX mapping. The previous capacity target (`d7d9c1decc82b9fa05d5bc3f317c6d0741363c7c53cca5bff22940782b017d86`) and failed preview evidence remain intact. This does not describe the larger current UI/native correction or enable production cutover.

### Accepted opening procedure — reference only

These steps document the already observed marker run. They are not a request to repeat it for the new diagnostic.


1. Stop the current game; do not resume an old savestate.
2. Manually copy `build/vwf-probe/EBOOT.elf` into a disposable copy of the game's `PS3_GAME/USRDIR/` as **`TH2_EN_VWF.elf`**. Do not replace `EBOOT.BIN`, source `EBOOT.elf` or previous diagnostic files. Project tools do not deploy anything.
3. Use **File → Boot (S)Elf → Boot SELF/ELF**, selecting that exact new file—not normal game-list launch. The decrypted ELF needs no SELF signing/conversion. Retain the boot-log path and build hash.
4. Select **ToHeart2**, then New Game, not AnotherDays. The observed opening is native `010301000` / `script_0000.json`.
5. Capture F01/F02, F07/F08 and F09 with its following Japanese before advancing; report any crash or layout difference immediately.

Expected visible first-page text:

```text
[F01] ABCDEFGHIJKLMNOPQR
STUVWXYZ
[F02] abcdefgh
```

Acceptance:

- Full F01/F07 alphabets and the F02/F08 fragments remain visible.
- F02/F08 flowers follow the visible text instead of covering letters.
- F09/F11 no longer overlap their untouched Japanese continuations.
- F03 digits, F04 mixed-width letters and the complete F05/F06 sentence/fragments remain intact.
- F09–F16, page/wait, skip/auto, backlog and navigation retain their content. Unobserved punctuation/name/choice/save checks remain unpassed.

Observed success and screenshot/log fingerprints are recorded in `work/qa/probe-observations/vwf-opening-visual-success.json`. Full page/wait/auto/skip, comprehensive punctuation, backlog navigation, English name/choice layouts and save/load are not proved by those still images.

### Save-preview correction — observed pass; continue remaining checks

The user's `16_56_54` DataLoad screenshot shows slot005's English caption and ellipsis inside the border, with proportional Latin spacing. Japanese slots003/004, thumbnails, dates, selection border and NoData rows remain legible. The log identifies **`TH2_EN_SAVE_UI.elf`** and the screenshot; current installed/staged hashes match the target above. No full ELF SHA-256 was recorded at boot. Evidence: `work/qa/probe-observations/save-preview-visual-success.json`.

The user's subsequent **“all ok.”** accepts the requested same-build existing-spare-save load, page advance, auto/skip and backlog return. These are recorded by **user report**, separately from the menu image, in `work/qa/probe-observations/save-preview-controls-success.json`. The current case matrix retains all five growth/control/menu passes; missing English surfaces and long-page behavior are assigned to the new diagnostic instead of requiring another run of the accepted one.

The correction affects only the temporary preview. Full dialogue/backlog and serialized save text are unchanged. Unusually wide preview excerpts receive the game's existing CP932 ellipsis at a whole-character boundary; this is not a shortened translation.

The earlier yellow capture is backlog, not a restored gameplay image; the later explicit report now supplies the requested backlog-return result. English name/choice/punctuation and arbitrary-length page-height behavior remain open. Record only observed/reported results on their attributed builds; never treat a short confirmation as full-game acceptance or transfer old passes silently.

### Remaining runtime observations — paired UI/long-text candidate

Use a **disposable copy of your own dump**, user-run only. Boot the exact new ELF under a distinct name such as **`TH2_EN_GEN_LATIN_BACKLOG.elf`** with its new a660c827... archive. Preserve originals, personal saves and all failed candidates. Fresh ToHeart2 New Game only; never corrupted006/007 or a frozen old session. Do not repeat failed4150/cb7864/90046ed1/83c58c0f/62bdc049 or accepted F01–F16 merely to reconfirm.

1. Inspect name help, dialogue and Options at native720p: GenInterfaceJP letters/digits, complete `g/j/p/q/y`, whole words, original Japanese/private symbols and label/value clearance. Inspect the redrawn titles, name-entry controls/grid, calendar/maps and music/save surfaces; font changes do not inherit old acceptance.
2. Open backlog during/after the unshortened **1,286-byte H01–H08 paragraph**. Use the existing older/newer backlog controls repeatedly: they now move through a tall logical record before changing records. Read every section through HEND without drawing below/above the viewport; verify voice icons track their lines. Return to older/newer records, close/reopen and resume unchanged gameplay. The entire current recorded entry remains available without advancing gameplay or marking it read; it is never split into fake history records.

The user's11:29:40 screenshot now shows H08/HEND plus the complete Japanese continuation, and the explicit report confirms scroll-to-end. Evidence: `work/qa/probe-observations/gen-latin-backlog-runtime.json`, exact66786e63/a660c827 pair. **Do not repeat confirmed scrolling or the shown whole-word pages merely to reconfirm.** Older/newer entry navigation, close/reopen and return to unchanged gameplay are separate unshown subcases; skip/save/story/choices and new-font UI checks below remain outstanding.

3. During a later paragraph page, use only a **disposable new spare slot** and reload it on this exact build. The saved page/unread remainder must survive through HEND (`long_text_save_load`). This tests new checkpoint semantics, not a repeat of the accepted old short-run save.
4. Exercise skip past this paragraph into an unchanged scene: no black screen or loss of normal progression (`skip_after_long_text`). Check ToHeart2 branding and legitimate March1 date/state before advancing days (`story_state`). Do not force or repair date/story values.
5. Only after height passes, continue to **March2 after school**: all three complete English amusement-park/sports/home choices must fit. Choose one; its original **B01/B02/B03** branch marker must appear, then ordinary Japanese must remain legible in an unchanged scene.

Earlier preview/short-run controls retain their own hashes. They do **not** accept the newly reported long-text skip/state failures or the new checkpoint codec. Never overwrite personal saves; preserve corrupted006/007 as evidence.

Inspect the new English UI at native720p before dialogue acceptance: title selections, every Options label/help message, save/load headings/story tags, name-entry help, active calendar dates, map locations and Visual/Music screens. All words, punctuation, controller hints and credits must be legible with normal-width glyphs, intact descenders, good contrast and no overlap (`ui_readability`). Music titles/role labels/complete credited names must stay distinct (`ui_credits`); compare the private source-bound credit reference rather than replacing PS3 roles with album-only arrangements. The original kana grid, personal name defaults and bilingual brand logos are intentionally retained. Each UI surface has its own exact-build field; none is pre-accepted.

## Offline evidence already cleared

- Complete native index: 1,884 entries. The original 1,009 message files / 182,111 records are preserved. New immutable choice companions add 115 files / 1,335 captions: **1,124 editable files / 183,446 records**, all unchanged in translation work.
- SDAT recovery: 3,516 assets; original TPL fonts recovered; Latin pixels and later runtime glyphs observed.
- `tools/scene_catalog.py`: complete native-name/label/source catalog, 750 exact-name PC entry candidates, scoped first-New-Game observation; no guessed story routes.
- Native-flow build: all 1,884 output payloads checked, all 16 compiled markers re-extracted, visible characters and original wait/page/opcode items preserved. Whole-image comparison proves only the reviewed native instruction differs from the failed flow image.
- Container/layout, growth/encoding/control, choice-label and expression-boundary regressions have passing results. New scope regressions reject computed ingress/dynamic calendar writes and retain deferred/shared ownership correctly. The graph has **13,647 transfer sites /9,474 state effects /zero unmatched supported-command frames**; clean census alone is not route-feasibility proof. Source and production remain byte-identical; no work translation is claimed.
- Current encoded VWF smoke passed **44 scanner fixtures, 14 source-metric comparisons and eight flower-block states**. Actual injected PPC bytes were interpreted in bounded synthetic RAM; three flower blocks stored C520 and repositioning produced its F4 drawing argument. All 1,884 payloads in **each** new ELF matched their retained input. Report: `build/vwf-probe/encoded-smoke.json`. This is software instruction evidence, not native FP/GPU/VM/emulator execution.
- `python -X utf8 tools/save_preview_probe.py` passed **21 source/encoded caption cases and six original measurement probes**, including narrow/wide ASCII, Japanese/PUA punctuation, mixed text, the exact row edge, overflow and split-CP932 boundaries. Actual `1BCB8` CPU glyph records are checked. The reported caption's quad envelope changes from `[420,1147)` to `[408,772)` against source inner-right X=1010. All 1,884 scenario payloads remain identical. Report: `build/save-preview-probe/encoded-smoke.json`. GPU/menu/native-FP execution remains manual.
- `project.py smoke` rebuilt and re-extracted both message and native choice markers. Its first original-slot attempt correctly rejected a **2,768-byte chunk against 2,764 bytes**; the diagnostic now uses real appended capacity, not shorter text. The final window/height builder verified all 1,884 payloads, complete English choices, unchanged selection expressions and byte-identical branch bodies at relocated A/B/C labels.
- Continued offline height replay preserved every byte of the actual 1,286-byte diagnostic paragraph: 36 spans reached logical Y=1,680 without wait/page/end flags at both synthetic height144 and source-default height628. Report: `work/qa/window-height-source-audit.json`. Construction/drawing remain modeled boundaries; this does not record runtime clipping or a manual pass. Native queue clearing deletes all spans, so an automatic-pagination correction must preserve unread content rather than merely call the existing clear routine.
- The earlier `tools/pagination_probe.py` staged the now-failed4150 hash without changing any of1,884 payloads. Seven helper/native wait/resume/unlink cases plus saved-page/clear/backlog and44 layout fixtures passed. Those models excluded the VM literal clamp, opacity consumer and bounded live save-text area; their scoped success did not establish runtime safety. Historical reports remain under `build/pagination-probe/`.
- `tools/runtime_text_probe.stage(...)` staged the corrected hash using completed exact-image replay. `runtime-smoke.json` executes the native literal handler, opacity copy/consumer/constructor, full skip renderer, waits/resume and reference restoration. All1,286 bytes survive;256 opacity entries, u16 boundaries1,023/1,024/65,535, later-page restoration, legacy/repeated references and seven invalid-boundary cases pass. Immediate skip may intentionally advance before glyph opacity settles; held-page replay proves full opacity at its modeled draw boundary.
- `build/runtime-text-probe/projection-smoke.json` exercises the real native-only production rebuild: all1,884 original payloads remain unchanged, diagnostic English is excluded, and an actual42-byte Japanese literal is parsed/checkpointed/replayed from the projected image. No production image is written. Native history-ring behavior, GPU/native FP/full VM and full-game memory remain unproved.
- `build/typography-probe/typography-smoke.json` covers11 word/control/scale/CP932 cases and21 glyphs at three scales. Actual glyph queue construction and vertex conversion prove complete requested cell/texel edges. All1,286 paragraph bytes survive40 modeled rows/four pages; full native skip and later-page checkpoint replay retain raw progress/flags. The production projection retains all1,884 source payloads without diagnostic English. These are software/source results, not GPU acceptance.
- `build/ui-native-probe/` passes142 raw/centered string cases plus nine composed dialogue glyph cases,46 literal loads/220 pointers/20 geometry words,13 footer cells, two role quads and51 music rows. All1,286 literal bytes/02 terminator/four modeled pages survive. Native-only source projection and real temporary paired-archive copying succeed. All2,148 replacement chunks satisfy the native header/stride contract and each TPL re-extracts exactly;134,139-block authentication/full DAT decrypt-SHA proof and all83 regressions pass. Earlier `ui-readable-probe` model/crypto passes remain scoped historical evidence, not acceptance of its subsequently failed rendering.
- `tools/scenario_membership.py` resolves normal-title routing ownership using all four original title choices, closed month effects and the May20 terminal/title-return barrier. Base scope includes1,272 scenarios /102,062 editable records; unresolved membership is zero. Individual route feasibility, replay/debug/custom-save ingress and translation completeness are not implied.

The earlier eight-record fixed-slot flow attempt exceeded its compressed slot and was rejected. Production still enforces original slots; the separate-segment diagnostic removes that arena ceiling experimentally, without shortening real English. Native automatic pagination now has offline execution evidence; runtime page visibility, name/choice layouts and full-game memory requirements remain unproved.

## Record actual manual results

Use **`work/qa/gen-latin-reload-results-to-fill.json`** for thea15f4f08... ELF/be72aa94... SDAT pair. All24 window fields start null; the earlier scoped passes stay with their original forms and are not transferred. Record both hashes and tester/version/scene/notes/screenshots; never infer unshown controls/UI/save/skip checks. The previous66786e63/a660c827 form remains `gen-latin-backlog-results-to-fill.json`.

```console
# A fresh exact-hash form has already been generated; do not replace it.
# After actual manual checks and screenshots:
python -X utf8 tools/gates.py record work/qa/gen-latin-reload-results-to-fill.json
python -X utf8 tools/gates.py check
```

Record tester, RPCS3 version, date, observed scene, actual results, notes and screenshots for each exact build. Stale build hashes and incomplete checks are rejected. Offline success never manufactures a runtime pass.

The production gate requires200 source instruction sites,240 existing data words/pointers,68 exact Latin/bracket metric pairs, complete helpers, the non-writable R-X mapping, exact paired SDAT and all1,884 scenarios at64-byte starts. Font-derived pairs and supplemental-code hashes are guarded; writable/partial/unrelated copies fail closed. Dialogue59488 remains original; production/bulk stay disabled without all24 genuine current-build observations.

**Production-cutover readiness (offline):** an empty-change `production_engine.rebuild_image` projection already preserves all1,884 original payloads byte-for-byte, uses64-byte appended starts, excludes diagnostic text and passes the cutover guard; deterministic SHA-256 **`3ea90c070ac9348f48d1f09625ef4a988723e4f552fe717daa9026d1ba4e7eca`**, 10,464,504 bytes. Evidence: `work/qa/production-readiness-2026-10-26.json` (zero payload differences). The reported gate stays blocked by design until `build/english` is rebuilt with `manual-evidence.json`; do not copy the diagnostic or this projection into production to force it.

`tools/production_engine.py` defaults to the paired UI template and copies approved native/UI code, data and strings, never diagnostic dialogue. Accepted growth `build/smoke` also stage `data.sdat`; an original-slot ELF must not share an output directory with a localized archive. Older builders retain explicit historical hashes. UI localization does not enable bulk scenario insertion or manufacture acceptance.


Ittaku permission and patch-only packaging remain publication requirements. Safe runtime widths/page visibility, English name/choice layouts, individual route feasibility and full-game growth support are not inferred from a short accepted opening.

## Backlog crash and tight tracking — 2026-10-25

The logged90046ed1/c4898391 session includes both22:16 screenshots and a user-reported backlog crash. Backlog `6A20C` copied1,286 bytes into the1,024-byte global scratch at6669C0; paragraph bytes1024–1027 (`. Ad`) overwrote object-list head666DC0 with2E204164. Native6B9E8 then read2E204178, exactly matching the fatal log. Independently each original history payload held only840 bytes and append had no bound. Preserve `work/qa/probe-observations/backlog-ui-runtime-failure.json`; do not rerun that pair.

`native-history-smoke.json` executes old/corrected append/read and reproduces that exact original fault. Corrected cases cover inline/1,024/u16 boundaries, two65,535-byte strings in one logical record, explicit metadata, repeated saved-reference appends,205 ring appends/two wraps and both reset/destroy ownership. Scanner submission, allocation/libc and unrelated context/vector cleanup remain explicit boundaries, not full-VM/GPU proof.

Native UI ASCII tracking increases before scale/rounding from b+2 to b+6; draw/measure match. Name help uses actual0.5833333 scale and options help0.4. Four complete help strings reflow only at words; all18 labels retain at least13px slider clearance. Fixed Japanese, three accepted save-caption controls and51 music-row layouts remain unchanged. Original-font approximation: `work/qa/probe-observations/ui-tracking-native-preview.png`.

## Latest-record backlog display — distinct acceptance target

The83c58c0f screenshots reach HEND in gameplay but leave the newest backlog entry partial/blank. Preserve its form and seven archived captures; do not repeat that failure.6A284 now selects native full-record reveal instead of inheriting ordinals from a retired/rebased gameplay queue. This intentionally makes the entire current recorded logical entry available in backlog, without advancing gameplay or introducing future entries.

The historical62bdc049... ELF used unchanged c4898391... SDAT. Its form began null; later two screenshots report g/bottom-overflow failures while showing expanded backlog text. Its constructor/cache proof did not establish viewport access. The current distinct target above adds source-control within-record scrolling, actual position/colour submission checks, signed-coordinate boundary fixtures and close/reopen replay. These remain bounded CPU proofs, not GPU/controller/full-scheduler acceptance.

Inter is canceled. The user subsequently approved GenInterfaceJP **Latin letters/digits**, superseding the comparison-only boundary;48px em/baseline37 keeps complete quantized ink inside the existing cells. Original Japanese/punctuation/private data remain intact. Font choice does not fix history navigation; the separate viewport correction does. See `docs/fonts.md` and the new smoke-report limitations.

## The shipped v0.1 pair is not the gates-bound diagnostic pair — 2026-10-27

The diagnostic artifact this page describes (`a15f4f08...` ELF with the
`be72aa94...` archive) is still what `gates.py` binds through
`ARTIFACTS["windows"]` and what `work/qa/gen-latin-reload-results-to-fill.json`
collects 24 observations for. The deliverable pair is different and newer:
`build/english-v0.1/EBOOT.elf` (`a31bdd83...`, 10,687,608 bytes) with
`build/english-v0.1/assets/data.sdat` (`bbb932bf...`, 2,202,570,928 bytes).

It differs in exactly two ways that matter on screen: 23 ASCII punctuation
aliases are redrawn as narrow Latin cells (with their full-width counterparts
following the same cells), and the six native default-name strings now read
`Kouno Takaaki` / `Taka`. Everything else — engine template, wrapping, pagination,
history, backlog scrolling, UI geometry — is the same code as the diagnostic
pair, but the pixels differ, so **the 24 window fields for the diagnostic pair do
not transfer to v0.1** and observations must be made on the artifact you intend
to ship.

Nothing here re-points the gate: making v0.1 the accepted pair means deliberately
changing `gates.ARTIFACTS` and the evidence form, which this workspace has not
done. Until then v0.1 stays an offline artifact with `manual_acceptance: null`
and `runtime_verified: false`, and the installer refuses nothing on that basis —
it only verifies that the files match the report they came with.
