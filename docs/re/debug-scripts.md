# Retained developer test scripts — BLJM60381

## Finding

**Developer test scripts are present in the supplied retail PS3 executable.**
This is not evidence of an accessible native debug console or a controller cheat
code. No verified stock-game button combination was found. The method below is
an experimental, source-specific startup redirect to the existing scripts.

All findings bind to the immutable `EBOOT.elf`:

`8d8bc60d2b02d12f509a9a3ee9c126876ac8524d4f02c7871206aca9bd66e828`

| Native scenario | Extracted correspondence | Actual source content |
| --- | --- | --- |
| `999999999` | `script_1018.json` | Two-page “Execute Script!” selector |
| `999999001`–`005`, `007`–`010`, `020`, `030`, `040` | `script_1006.json`–`script_1017.json` | Character/event selector submenus |
| `700000000` | `script_0817.json` | Map, calendar, and clock tests |
| `600000001` | `script_0816.json` | Japanese line-start prohibition/text-layout test |

The root scene selector has Konomi, Manaka, Tamaki, Karin, Sango/Ruri, Yuma,
Lucy, Yuuki, Yuji, morning, before-bed, and Sunday/holiday categories. Its
12 literal command `0x1F` submenu destinations all exist and their original
payloads decode successfully. This appears to be a legacy base-game selector:
do not assume it covers Sasara, Mio, AnotherDays, or every packaged scene.
Names, menu presence, and payload decoding do not prove runtime reachability or
correct story-state initialization.

The existing source-bound scenario graph shows submenu returns to the root.
Normal-title story ownership classifies these programs as inactive. Neither
fact establishes that every possible native shortcut has been ruled out.
Web searches did not supply a reliable PS3 activation code.

## Prepared activation candidates

For selectable RPCS3 cheats instead of prepatched executables, see
[`patches/README.md`](../../patches/README.md) and
`patches/BLJM60381_debug_patch.yml`. Enable one mode on its matching original or
English-diagnostic executable and restart; do not combine this with an already
patched debug ELF. On 2026-10-29 the user confirmed both RPCS3 patch options work
on the original executable. The English-diagnostic variants remain runtime-unverified.

These are separate **original-Japanese diagnostic ELFs**, not English builds.
They retain the original fonts, strings, scenario bytes and scenario index.

| Purpose | File | SHA-256 |
| --- | --- | --- |
| Scene/event selector | `build/debug-scene-menu-probe/EBOOT.elf` | `25a7d18225fc07b2c3d485ff80936cf9bbdae1d3e186802f9a992ca73d7d74a5` |
| Map/calendar/clock tests | `build/debug-system-tests-probe/EBOOT.elf` | `9d208fcb65c078c025c68358b3fae329ecc92810a1785481ddcae218d500ccdd` |

### Manual test procedure

1. Use your own BLJM60381 dump with its **original matching `data.sdat`**.
   Do not mix these original-font ELFs with any localized/font-modified archive.
   If the installed copy currently has a localized archive, use a separate
   original-asset copy for this test rather than overwriting the installed files.
2. In RPCS3, manually select **File → Boot (S)Elf → Boot SELF/ELF** and choose
   the exact scene-selector ELF above. This is the existing project's direct-ELF
   diagnostic workflow. Do not double-click the normal game-list entry and
   assume it loaded this probe. Check the log for the chosen ELF path.
3. Start a **new base-game story** (ToHeart2), completing any normal name/start
   screens. Do not use Continue or an existing save. The first named script
   startup should be redirected to `999999999` instead of the normal opening.
4. Expected first screen: `スクリプト実行！（ページ１）` (“Execute Script! (Page 1)”),
   followed by character categories. `次へ` is Next and `戻る` is Back. Use the
   game's usual menu controls. First confirm that the root appears, then test
   one category; report those observations separately.
5. **Do not save**, overwrite existing saves, or use this build for normal play.
   Developer scene jumps may skip required flags/resources. Named calendar
   transitions can return to the selector. A hang or crash is possible.
6. To leave, stop the test and boot your usual verified executable/archive pair.
   No installation or source replacement is needed for the direct-ELF test.

For map/calendar/clock tests, repeat with the system-tests ELF. The expected
choices include `マップテスト`, `カレンダーテスト`, and `時計テスト`.

**Scene-selector root confirmed by the user on 2026-10-29.** The attached
1280×720 screenshot shows `スクリプト実行！（ページ１）` and all expected page-1
categories, with Next highlighted. This follows the provided scene-selector
probe procedure; the loaded ELF hash and emulator version were not independently
reported or verified. Evidence is recorded in
`work/qa/observations/debug-scene-menu-root-20261029.json`; the screenshot itself
is retained in this conversation, not copied to an invented local path.
The user subsequently confirmed that submenus and scene jumps also all worked
in the same session. Accept this as user-reported runtime verification of those
functions; no individual scene IDs or exhaustive test matrix were supplied, so
do not infer coverage of every selectable scene. The user additionally confirmed
that both Scene Selector and System Tests work as RPCS3 patches on the original
executable. That report verifies system-test mode entry/functionality through the
cheat, not an enumerated test of every system-test case or the separate direct-ELF
probe. The follow-up is recorded in
`work/qa/observations/rpcs3-debug-patches-original-20261029.json`.
There is no need to repeat these established results. Existing saves can
remain untouched, but the game may still maintain ordinary system data; use an
isolated test profile/copy if preserving completion data is essential.

## Native mechanism and exact patch

The normal calendar entry at VA `0x81164`–`0x81170` schedules native mode 6
with a script-name argument. The mode's initializer is `0x8BA6C`, which retains
the name pointer in `r31`. At `0x8BC50` it distinguishes named startup from
numeric startup and save resume. The original named path at `0x8BC9C` loads
the VM context from `0x652614`, passes `r31` in `r4`, and calls `0x5E0E0`.

The probe changes only five words, file `0x7BC9C`–`0x7BCB0` (end exclusive):

| VA | Original word | Scene-selector word |
| --- | --- | --- |
| `0x8BC9C` | `3c600065` | `3c80000f` |
| `0x8BCA0` | `63e40000` | `6084a62c` |
| `0x8BCA4` | `80632614` | `3c600065` |
| `0x8BCA8` | `4bfd2439` | `80632614` |
| `0x8BCAC` | `60000000` | `4bfd2435` |

This passes VA `0xFA62C`, the verified native table's `999999999` name, to the
same loader with the same VM context. The call moves into the original nop
slot and returns directly to the original common continuation `0x8BCB0`.
Numeric transfers (including script command `0x1F` at `0x728C8` → `0x5E16C`)
and the save-resume branch are not patched. Do not apply this table to a
different executable revision or a relocated/patched native build.

For system tests only the second replacement word changes to `6084999c`,
selecting the source's `700000000` name at VA `0xF999C`.

## Verification and reproduction

`tools/debug_script_probe.py` validates the pinned source via `project`, checks
the original five instructions, reads the target pointer from the native index,
decodes the menu, resolves/decompresses literal transfer targets, and checks
that **every byte outside the 20-byte code block remains unchanged**. No scenario
recompression, translation insertion, production-growth gate change or SDAT
rebuild is involved. Staging refuses an existing output directory.

```console
python -X utf8 tools/debug_script_probe.py
python -X utf8 tools/debug_script_probe.py --scalar-smoke
python -X utf8 tools/debug_script_probe.py --stage build/debug-scene-menu-probe-NEW
python -X utf8 tools/debug_script_probe.py --target graphics-test --stage build/debug-system-tests-probe-NEW
python -X utf8 -m unittest discover -s tests -q
```

Optional native dependencies are the existing `capstone==5.0.7` and, for scalar
replay, `unicorn==2.1.4`; the task did not download or install them.

Evidence:

- `build/debug-scene-menu-probe/debug-probe-report.json`: initial stage report.
- `work/qa/debug-scene-menu-full-audit.json`: expanded source/menu audit and
  scalar replay for the identical scene-selector ELF hash.
- `build/debug-system-tests-probe/debug-probe-report.json`: expanded system-test
  stage report and scalar replay.
- 238 synthetic unit tests pass, including four tests of the new patch helper.

The scalar replay executes only the original four or replacement five startup
instructions in scratch RAM and stops at the loader. It confirms context/name
arguments, preserved `r30/r31`, and return address. It does **not** execute the
loader, scenario VM, menu renderer, input handling or game. It is not RPCS3
testing or runtime acceptance.
