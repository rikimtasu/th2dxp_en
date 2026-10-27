# ToHeart2 DX PLUS — English patch

Unofficial English localization of **ToHeart2 DX PLUS** (PS3, `BLJM60381`).

The base-game dialogue is translated and an installer is published. It is a
**preview, not a finished patch**: the current build has no runtime acceptance
yet — the 24 manual observation slots are still empty — so boot behaviour,
pagination, saves and route coverage are unproven. Project tools never launch an
emulator and never touch your saves.

## Install (players)

1. Download `th2dxp_en-v0.1-installer.zip` from
   [Releases](https://github.com/rikimtasu/th2dxp_en/releases/tag/v0.1) and
   unpack it.
2. Run `th2dxp_patch_gui.exe`. Windows, no Python needed.
3. Point it at the folder where your copy is installed — the one holding
   `PS3_GAME/USRDIR`.
4. Press **Install**, then start the game yourself in RPCS3.

The installer decrypts *your* `EBOOT.BIN` and `data.sdat` in place, applies the
hash-pinned patch, verifies both files, and writes byte-exact backups to
`USRDIR/.th2dxp-backup/`. **Restore original** puts them back at any time. Close
RPCS3 while installing or restoring; you need roughly 7 GB free, and your
`data.sdat` must be the pristine retail archive — the app refuses anything it
does not recognise instead of overwriting it.

Do not replace `EBOOT.BIN` by hand. No game data is redistributed: the download
contains the installer and documentation only.

## Translate it yourself

You need your own dump. The full walkthrough is in
[`TRANSLATING.md`](TRANSLATING.md); the short version:

```console
python -X utf8 tools/ps3_self.py "<your game>/PS3_GAME/USRDIR/EBOOT.BIN" -o EBOOT.elf
python -X utf8 tools/project.py extract   # once
# edit only translated_text in script/*.json
python -X utf8 tools/project.py check
python -X utf8 tools/project.py build     # build/english/EBOOT.elf
```

Then install your own build with `tools/patch_game.py` (dry run first):

```console
python -X utf8 tools/patch_game.py apply --build build/english --game-dir "<…>/PS3_GAME/USRDIR"
```

One native fragment per row, controls and blanks untouched, no shortening to fit,
and CP932 must round-trip. Those rules are not style preferences — they are what
keeps the file loadable.

## What is in here

| Path | What it is |
| --- | --- |
| `script/` | Your editable text (created by `extract`, ignored by Git) |
| `tools/` | Extraction, validation, build, installer and QA helpers |
| `docs/` | Decisions, status, fonts, reverse-engineering and manual QA |
| `glossary.md` | Character names and honorifics, with provenance |
| `build/` | Local staged outputs and reports; never deployed automatically |
| `vendor/` | Pinned upstream tools, reproducible with `bootstrap.py` |

This repository is **source only**: no game files, decrypted executable,
extracted Japanese, built ELF/SDAT or saves are tracked or published.

Setup: Python 3.10+, Git, `pylzma`, Pillow.

```console
python -X utf8 tools/bootstrap.py
python -m pip install -r requirements.txt
python -X utf8 -m unittest discover -s tests -q
```

## Status

- **Translated:** 885 base-game scenario files, 102,062 text items, plus the
  Latin/punctuation font atlas and the English default name `Kouno Takaaki`.
- **Not verified:** runtime rendering, long-line pagination, save compatibility
  and route reachability. The 24 manual checks in
  `work/qa/gen-latin-reload-results-to-fill.json` are deliberately unwritten
  until someone observes the real build.
- **Not started:** AnotherDays.
- `tools/project.py check` fails closed on this checkout on purpose: the shipped
  lines are longer than the original Japanese slots, and the growth path stays
  gated until manual acceptance exists.
- Offline proofs — hashes, round-trips, synthetic tests — say the files are
  well-formed. They do not say the game plays correctly.

## Documentation

| Guide | Contents |
| --- | --- |
| [`TRANSLATING.md`](TRANSLATING.md) | Step-by-step translation workflow |
| [`docs/status.md`](docs/status.md) | What is done, what is blocked, evidence |
| [`docs/decisions.md`](docs/decisions.md) | Why the pipeline works this way |
| [`docs/manual-testing.md`](docs/manual-testing.md) | How runtime evidence is recorded |
| [`docs/pretranslation-gates.md`](docs/pretranslation-gates.md) | Current diagnostic build and remaining cases |
| [`docs/ittaku-reference.md`](docs/ittaku-reference.md) | PC reference text for context |
| [`docs/fonts.md`](docs/fonts.md), [`docs/rebuild-capacity.md`](docs/rebuild-capacity.md) | Font and capacity findings |
| [`docs/re/README.md`](docs/re/README.md) | Native format notes |

## Credits and licence

Built on [TH2DXP_KIT](https://github.com/hiroshil/TH2DXP_KIT), with workspace
conventions from
[fan-translation-template](https://github.com/minhnhattonthat/fan-translation-template)
and the workflow from
[translate-retro-game](https://github.com/minhnhattonthat/translate-retro-game);
exact revisions are in [`upstreams.json`](upstreams.json). Font: GenInterfaceJP
(SIL OFL), notice staged in the release.

Project Python tools and docs are MIT. `tools/pc_reference_dump.cpp` is
GPL-2.0. Game data, PC reference translation and VNDB-derived names carry their
own rights. See [`NOTICE.md`](NOTICE.md). No redistribution permission is
implied.
