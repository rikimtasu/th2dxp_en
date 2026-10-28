# ToHeart2 DX PLUS — English patch

Unofficial English localization of **ToHeart2 DX PLUS** (PS3, `BLJM60381`).

The English base-game installer is a **preview, not a finished patch**.
**v0.2** includes QC/spacing corrections and 85% dialogue size. The player tested
this game payload and supplied three positive screenshots; comprehensive runtime,
save and route acceptance is still incomplete. Project tools never launch an
emulator and never touch your saves.

## Install (players)

1. Download `th2dxp_en-v0.2-installer.zip` from
   [Releases](https://github.com/rikimtasu/th2dxp_en/releases/tag/v0.2), unpack it
   and run `th2dxp_patch_gui.exe` — Windows, no Python.
2. Point it at the folder holding `PS3_GAME/USRDIR`.
3. If upgrading an older patch, press **Restore original** first, then **Install**.
4. Start a **fresh ToHeart2 New Game** yourself in RPCS3. Older builds' execution-position
   saves are not supported; preserve personal saves and use disposable same-build slots.

It decrypts *your* `EBOOT.BIN` and `data.sdat`, applies the hash-pinned patch,
verifies both files and keeps byte-exact backups in `USRDIR/.th2dxp-backup/`.
**Restore original** undoes it. Close RPCS3 while doing either; you need ~7 GB
free and a pristine retail `data.sdat` — the app refuses anything it does not
recognise. Do not replace `EBOOT.BIN` by hand.

## Setup (only for translation work)

Python 3.10+, Git, `pylzma`, Pillow:

```console
python -X utf8 tools/bootstrap.py
python -m pip install -r requirements.txt
python -X utf8 -m unittest discover -s tests -q
```

## Translate it yourself

The full walkthrough is in [`TRANSLATING.md`](TRANSLATING.md); the short version,
run from the repository root with your own dump:

```console
python -X utf8 tools/ps3_self.py "<your game>/PS3_GAME/USRDIR/EBOOT.BIN" -o EBOOT.elf
python -X utf8 tools/project.py extract   # once
# edit only translated_text in script/*.json
python -X utf8 tools/project.py check
python -X utf8 tools/project.py build     # build/english/EBOOT.elf
python -X utf8 tools/patch_game.py apply --build build/english --game-dir "<…>/PS3_GAME/USRDIR"
```

One native fragment per row, controls and blanks untouched, no shortening to fit,
CP932 must round-trip. Those are load-bearing rules, not style preferences.

## What is in here

| Path | What it is |
| --- | --- |
| `script/` | Your editable text (created by `extract`, ignored by Git) |
| `tools/` | Extraction, validation, build, installer and QA helpers |
| `docs/` | Decisions, status, fonts, reverse-engineering, manual QA |
| `glossary.md` | Character names and honorifics, with provenance |
| `build/`, `vendor/` | Local outputs and pinned upstream tools |

This repository is **source only**: no game files, decrypted executable,
extracted Japanese, built ELF/SDAT or saves are tracked or published.

## Status

- **Translated:** 885 base-game scenarios, 102,062 text items, the
  Latin/punctuation font atlas and the English default name `Kouno Takaaki`.
- **v0.2:** 1,928 text-item corrections across 311 files, including 457 spacing
  fixes, plus 85% normal-dialogue size without changing character tracking.
- **Observed:** the player reports the combined build looks good; screenshots show
  corrected spacing/name spelling and readable text in the shown opening/classroom scenes.
- **Still unverified:** full-game rendering/pagination, voice timing, save compatibility
  and route reachability. The older template's manual form is not repinned or filled
  from these limited observations.
- **Not started:** AnotherDays.
- `tools/project.py check` fails closed here on purpose: shipped lines exceed the
  original Japanese slots, and the growth path stays gated on manual acceptance.
- Offline proofs (hashes, round-trips, synthetic tests) say the files are
  well-formed. They do not say the game plays correctly.

## Documentation

[`TRANSLATING.md`](TRANSLATING.md) ·
[`docs/status.md`](docs/status.md) ·
[`docs/decisions.md`](docs/decisions.md) ·
[`docs/manual-testing.md`](docs/manual-testing.md) ·
[`docs/pretranslation-gates.md`](docs/pretranslation-gates.md) ·
[`docs/ittaku-reference.md`](docs/ittaku-reference.md) ·
[`docs/fonts.md`](docs/fonts.md) ·
[`docs/rebuild-capacity.md`](docs/rebuild-capacity.md) ·
[`docs/re/README.md`](docs/re/README.md)

## Credits and licence

Built on [TH2DXP_KIT](https://github.com/hiroshil/TH2DXP_KIT) with conventions from
[fan-translation-template](https://github.com/minhnhattonthat/fan-translation-template)
and [translate-retro-game](https://github.com/minhnhattonthat/translate-retro-game);
revisions are pinned in [`upstreams.json`](upstreams.json). Font: GenInterfaceJP
(SIL OFL).

Project Python tools and docs are MIT; `tools/pc_reference_dump.cpp` is GPL-2.0.
Game data, PC reference translation and VNDB-derived names carry their own rights
— see [`NOTICE.md`](NOTICE.md). No redistribution permission is implied. Tooling
was built with AI assistance.
