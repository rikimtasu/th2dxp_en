# Manual RPCS3 testing

**Only the user launches RPCS3.** No command here starts it or edits its configuration. All generated files remain under `build/` until manually selected.

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
