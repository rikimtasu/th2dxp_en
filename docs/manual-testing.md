# Manual RPCS3 testing

**Only the user launches RPCS3.** No command here starts it or edits its configuration. All generated files remain under `build/` until manually selected.

## v0.5 UI/script-fix pair

New pair: `build/ui-rendering-fixes-20261102/EBOOT.elf` (`cd2bc463…`) with its own `assets/data.sdat` (`25753e92…`). It includes the previous live translation-script fixes and all three targeted rendering changes. Exact full hashes and blank observations are in `work/qa/ui-rendering-fixes-20261102-results-to-fill.json`:24 general/eight targeted fields, all unobserved. See `release-v0.5.md`; v0.4 and its evidence remain historical.

Only the user tests a disposable copy and launches RPCS3. Upgrade through **Restore original → Install**, start a fresh New Game, preserve personal saves/backups and use new disposable same-build slots. Inspect compound `!?`/`!!`/`??` beside standalone marks and unrelated private icons; read long map labels/apostrophes during reveal and when stationary; inspect music titles/themes/credit roles/artists through locked, selected and scrolled rows with no panel/scrollbar overlap. Continue existing control/backlog/same-build save checks, recording only actual observations. Encoded pixel/geometry proofs do not establish final GPU sampling, full-game execution or compatibility with older saves.

## v0.4 glossary-corrected replacement — 2026-11-01

Current pair: `build/english-glossary-v04-fresh-20261101/EBOOT.elf` and its own `assets/data.sdat`. Exact identities and blank observations are in `work/qa/english-glossary-v04-20261101-results-to-fill.json`. This includes 4,633 additional glossary-name corrections across 388 files and supersedes the original v0.4 package, not its retained evidence.

**No runtime test report exists for this replacement.** The earlier user's general confirmation applies only to the `53d1b3be…`/`646e64f9…` pair below. Do not copy its report or any old observations into the new form. All 24 general and four targeted fields start null.

Upgrade through **Restore original → Install**, even from the original v0.4. Start a fresh New Game and create only new disposable same-build execution-position saves; preserve older/personal saves and exact original backups. Spot-check glossary spellings, contextual nicknames, honorifics, full-name order and split-name joins, then use the existing rendering/control/backlog/save observations below. Only the user launches RPCS3.

## Contraction/ruby and Ikuno-size correction — 2026-11-01

The earlier retained-review candidate is `build/english-retained-review-fresh-20261101/`. Its `EBOOT.elf` and its own `assets/data.sdat` remain one preserved pair; exact hashes and observations belong to `work/qa/english-retained-review-20261101-results-to-fill.json`. It is not the glossary-corrected v0.4 replacement.

This pair includes 4,754 additional editorial record edits from the retained findings, not an exhaustive whole-script review. Spot-check corrected names, source honorifics, fragment joins and dialogue in normal play. Preserve the earlier `build/english-text-review-fresh-20261101/` pair and its independent form.

The user subsequently reported “current build tested” and selected this exact pair for the v0.4 GitHub preview. This is a general test confirmation, not a substitute for the still-null 24 general and four targeted observations; no per-case results, version, scenes or screenshots were supplied. See `docs/release-v0.4.md` for the packaged release scope.

Only the user launches RPCS3 and tests a disposable copy. Start fresh; lexical apostrophe canonicalization, zero-length ruby readings and editorial changes alter scenario/checkpoint offsets. Preserve personal saves and use a new disposable spare slot on this exact pair.

- In the supplied `script_0967` street scene, check `It's`, `can't` and `that's` for normal internal spacing, and check the subsequent continuous quotation.
- In Ikuno's story, compare ordinary text before/after a source `F10`/`F20` span: intentional half-size text may remain half-size, but returning to normal must restore the staged 75% scale rather than source 100%.
- Check the `script_0966` unit47 hospital sentence for no stray reading row or missing join space. Check the emphasized base words in `0966:54` and `0999:517`: the words must remain complete without dot-ruby or added internal spaces.
- Exercise advance/auto/skip, whole-record backlog scrolling/return, choices, story/date state and a disposable same-build save/reload. Record only actual observations and screenshots; encoded scanner/codec proofs are not GPU or runtime acceptance.

## Full-translation Japanese-font diagnostic — 2026-10-30

**2026-10-31 follow-up:** the user reported testing finished and selected this exact pair for the planned v0.3 release. Record that general report without requesting repeat tests merely to reconfirm it. Individual case results/version/scenes were not supplied, so the24-case form and separate production evidence remain unchanged. See `docs/release-v0.3.md` for the locally prepared package; no public release is claimed.

The completed Japanese-font candidate is `build/english-geninterface-jp-20261030/`; `EBOOT.report.json` and `assets/report.json` record successful staging/authentication/decrypt equality. Its exact `EBOOT.elf` (**`0213e036…`**) and `assets/data.sdat` (**`d387124f…`**) form one pair; full hashes are in `docs/fonts.md` and the independent blank form `work/qa/geninterface-japanese-20261030-results-to-fill.json`. Do not use older Latin-only archives or transfer their runtime results. The33 differing `n/` entries belong to the separately validated source variant and remain unchanged. Source recovery's legacy metadata warning does not authenticate the original; the newly generated output passed complete authentication/decrypt proof without warnings.

This candidate contains live translated scenarios, the69 targeted editorial corrections, GenInterfaceJP Japanese in all four fonts and75% normal-dialogue scale. It does **not** contain the old H01–H08 diagnostic paragraph or branch markers, so the historical marker procedures below are not a claim about this build. Formal production acceptance remains separate.

Only the user places the matched files in a **disposable test copy** and launches RPCS3. Start a fresh New Game; changed scenario offsets make old execution-position saves unsafe. Preserve personal/corrupted saves and use only a new disposable spare slot on this exact build. At native720p inspect mixed Japanese/Latin, kana including dakuten/handakuten/small kana, kanji and Japanese punctuation; check name-entry auxiliary fonts, help/options/music and save captions as well as normal dialogue. Then exercise page/auto/skip, choices, story/date progression, full-record backlog scrolling/return and same-build spare-save reload. Record actual scene, emulator version, tester, exact pair hashes and screenshots; no observation is prefilled as a pass.

## Retained Latin-only native acceptance target

Current hashes/procedure: **`docs/pretranslation-gates.md`**. Use **`build/gen-latin-reload-probe/EBOOT.elf`** (`TH2_EN_GEN_LATIN_RELOAD.elf`) with **`build/gen-latin-reload-probe/assets/data.sdat`** and **`work/qa/gen-latin-reload-results-to-fill.json`**. ELFa15f4f08... requires new SDATbe72aa94...; never reuse a660c827/c4898391 with it. GenInterfaceJP replaces Latin letters/digits and six `()[]{}` aliases; other Japanese/punctuation/private glyphs stay intact. Check complete g/j/p/q/y in help/dialogue, whole words and every UI surface, plus separated Normal/Whole Page values, the Next button, map/footer weight and bracket/i-dot centering. Load save slots005/010 (or a fresh save on this exact build) and confirm reload no longer faults, then scroll within a tall backlog entry and close/reopen/resume unchanged gameplay. Preserve all failed pairs/forms, including66786e63 and62bdc049; do not repeat them. No offline/GPU equivalence or runtime acceptance is inferred.

## Inputs and outputs

- `EBOOT.elf`: immutable decrypted baseline; SHA-256 pinned in `project.json`.
- `build/identity/EBOOT.elf`: must be byte-identical to the baseline.
- `build/english/EBOOT.elf`: current editable-script build; initially still Japanese.
- `build/smoke/EBOOT.elf`: diagnostic build with one `[EN TEST] Hello.` marker; **not an English patch**.
- `build/smoke/marker.json`: exact script filename and zero-based unit/item indices for that marker. Scene-to-script mapping has not been proved; do not assume the marker is on the title screen or first visible line.
- Sibling `.report.json` files record input/output hashes, modified record counts and payload verification; `emulator_tested` remains false.
- `build/gen-latin-reload-probe/assets/report.json`: new11-replacement DAT/authentication/complete original-tool decrypt proof, exact archive hash and verified read-only original backup provenance. Crypto proof is not rendering acceptance.
- `build/gen-latin-reload-probe/{native-latin-font-smoke,native-backlog-view-smoke,native-backlog-smoke,native-save-reload-smoke}.json`: actual candidate font pixels/metrics (68 pairs), bounded native viewport/reveal/navigation, signed coordinates and the corrected saved-literal decoder against authorized slots005/010. Long updates/selected caller boundaries are adapted; no full scheduler/controller/GPU/save-format claim.
- `work/ui/gen-latin-reload-graphics/previews/*-after.png`:20 native-size source-bound UI channel previews. Full words/proportions/contrast/descenders must also hold at actual caller scales. `GenInterfaceJP-OFL.txt` preserves the supplied font notice in the bundle.

## Procedure for the current distinct candidates

1. Close RPCS3 before manipulating a test installation. Back up your game and saves; preferably use a separate disposable test copy of your own dump. Project scripts do not deploy anything into the installed game.
2. Retain the established baseline evidence, RPCS3 version, game/configuration details and source hash. Do not reboot an unchanged control merely to repeat known results.
3. Use the candidate's documented new filename and hash; do not replace originals or previous diagnostics. Select **File → Boot (S)Elf → Boot SELF/ELF** and that exact file; normal game-list double-click still selects `EBOOT.BIN`. This decrypted-ELF loader was successfully used for prior probes; no signing/conversion is needed. Verify the log names the intended test ELF.
   For the UI pair, only the user places the paired archive as `data.sdat` in the **disposable dump's** `USRDIR`, keeping its original separately. Leave the original installation untouched. Retain both ELF and SDAT hashes with the observation; the evidence recorder rejects a changed asset even when the ELF matches.
4. Cold boot and use fresh ToHeart2 New Game rather than an old savestate or corrupted slots006/007. If checking the new checkpoint codec, use only a disposable new spare slot on this exact build and preserve all personal saves. Changed text/label offsets make cross-build execution-position saves unsafe; the corrected reader supports legacy inline entries but does not repair already corrupted state.
5. Reach the marker's script in normal play or a manually verified debug method. Record the scene and route mapping. Check Latin glyphs, punctuation, name box, choices, page/wait controls, skip/auto mode and backlog. Capture screenshots before/after advancing and check following Japanese lines are intact. Offline preservation checks cannot prove runtime display or choice logic.
6. Repeat a second, unrelated route and save/load transition to catch collateral script damage. Record missing glyphs, clipping, wrong names, crashes or altered choices with script IDs and reproduction steps.

Record results in `docs/status.md`: exact ELF/SDAT hashes, scene/route, RPCS3 version, expected/actual behavior and ignored screenshot paths. All24 window fields include UI surfaces/readability and backlog. Keep old-build failures attributed to their original pair. Never infer rendering, full-game memory or save compatibility from offline proofs.
