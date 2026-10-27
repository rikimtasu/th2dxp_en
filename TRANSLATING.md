# Translating ToHeart2 DX PLUS

A short guide for translators: take the Japanese out of **your own** copy of the
game, put your translation in, and hear it in the game.

You need your own lawful **BLJM60381** dump, Python 3.10+, and Git. Nothing here
downloads a game, a BIOS or someone else's translation, and nothing here starts
an emulator for you.

## 1. Dump the script from your own copy

Point the tool at the executable *inside your installed copy*. It only reads it.

```console
python -X utf8 tools/ps3_self.py "D:/Games/…/PS3_GAME/USRDIR/EBOOT.BIN" -o EBOOT.elf
```

That writes `EBOOT.elf` into the repository root, where extraction looks for it.
It refuses to overwrite an existing file unless you pass `--force`. The game
ships one encrypted executable, and this step decrypts it with the single retail
key set the disc uses — the same result on every machine.

Then extract:

```console
python -X utf8 tools/bootstrap.py
python -m pip install -r requirements.txt
python -X utf8 tools/project.py extract
```

You now have `script/`: **1,124 editable JSON files** — 1,009 dialogue scenarios
plus 115 `script_####_choices.json` caption files — holding 154,838 records and
183,446 text items. The base game is 885 of those scenarios; the rest are
AnotherDays and inactive programs, extracted so nothing is silently dropped.
Extraction checks the executable against the hash pinned in `project.json`, so a
different revision or an already-patched image is refused instead of half-read.

Two notes:

- `extract` refuses to run if `script/` already exists. Delete it (or start from
  a fresh clone) if you want to re-dump.
- Never edit `work/original-script/` or `work/original-choice-text/`. They are
  the frozen "before" copy every check compares against.

## 2. What the files look like

One file per scenario, one record per line of dialogue:

```json
{
  "end_reason": "terminal_control_plus_gap",
  "items": [
    {
      "kind": "text",
      "length": 42,
      "original_text": "　布団の中から手を伸ばし、目覚まし時計のス",
      "translated_text": "I reach out from under the futon and turn the alarm clock's ",
      "control_suffix": "",
      "editable": true
    },
    {
      "kind": "control_text",
      "control": "\\p0001",
      "editable": false
    }
  ]
}
```

**Change `translated_text`, and nothing else.** That is the whole editing task.

| Rule | Why |
| --- | --- |
| One `translated_text` = one native fragment | The engine stores one string per item; merging or splitting breaks the record. |
| Never reorder, add or delete items or files | `check` compares structure against the baseline and fails closed. |
| Keep every control code | `\k`, `\n`, `\p0001`, name substitutions and `<…>` tags are engine commands. Move them to where they belong in your sentence; never invent a literal newline. |
| Blank stays blank | An empty item is a carrier the game needs. |
| Plain CP932 only | The validator rejects anything the Japanese font cannot encode: accents, curly quotes, emoji, CJK punctuation the font lacks. Strict round-trip, not "encodable". |
| Choices live in the `_choices.json` file | Edit `translated_text` there. The same bytes inside the parent file are immutable. |

## 3. Check and build

```console
python -X utf8 tools/project.py check
python -X utf8 tools/project.py build
```

`check` validates structure, controls, encoding and the size available in the
game. `build` then writes `build/english/EBOOT.elf` plus `EBOOT.report.json`,
and re-reads every changed scenario out of the assembled image to prove it holds
what your JSON says.

If you see:

```text
script_0000.json:0:0: 60 bytes exceeds original 42; complete manual engine acceptance is required
```

your line is longer than the space the original Japanese occupied. **Do not
shorten the meaning to fit** — that is a hard rule of this project. You have two
honest options: rephrase to a complete sentence that fits, or use the
engine-growth path (`--engine-growth`), which removes the original budgets but
requires accepted runtime evidence and the project's staged native template. See
[`docs/decisions.md`](docs/decisions.md).

## 4. Put it in the game

Dry run first (writes nothing), then apply:

```console
python -X utf8 tools/patch_game.py apply --build build/english --game-dir "D:/Games/…/PS3_GAME/USRDIR"
python -X utf8 tools/patch_game.py apply --build build/english --game-dir "D:/Games/…/PS3_GAME/USRDIR" --apply
```

- Close RPCS3 during the write. The tool checks and refuses otherwise.
- `EBOOT.BIN` is replaced by your rebuilt ELF, byte-exact backups go to
  `USRDIR/.th2dxp-backup/`, and what happened is recorded in
  `USRDIR/.th2dxp-en-patch.json`.
- Undo any time: `python -X utf8 tools/patch_game.py restore --game-dir "…" --apply`
- **You** start the game. No tool here launches an emulator, and saves are
  never touched.

A build produced this way replaces only the executable, so the game keeps its
retail `data.sdat`: menus stay Japanese and Latin letters use the game's original
ASCII cells. The published v0.1 installer also ships a rebuilt archive for the
redrawn Latin/punctuation font — see the main [`README.md`](README.md).

## 5. Optional: work in LinguaGacha

Export the Japanese as `name`/`message` rows, translate them in any tool you
like, then let the importer write only valid text back:

```console
python -X utf8 tools/linguagacha_export.py --output work/linguagacha-mine
python -X utf8 tools/import_gt_output.py --export work/linguagacha-mine --check
python -X utf8 tools/import_gt_output.py --export work/linguagacha-mine --write
```

`--check` reports defects (row count, control, encoding, blank carrier) and
`--write` refuses the whole file if any row fails. Speaker names stay empty until
native bindings are verified; never fill them by guessing. Details:
[`docs/linguagacha.md`](docs/linguagacha.md).

## 6. Useful references

| Need | Where |
| --- | --- |
| Character names and honorifics | [`glossary.md`](glossary.md) |
| Project rules and history | [`docs/decisions.md`](docs/decisions.md) |
| PC reference text for context | [`docs/ittaku-reference.md`](docs/ittaku-reference.md) — search with `python -X utf8 tools/ittaku_reference.py search "Konomi" --kind decoded` |
| What is finished and what is not | [`docs/status.md`](docs/status.md) |
| Manual testing procedure | [`docs/manual-testing.md`](docs/manual-testing.md) |

Reference material is for context only. It is a different platform and edition:
never paste PC text in as if it were the PS3 line, and do not assume the same
script IDs.

## 7. Before you share anything

Run the tests, then read [`NOTICE.md`](NOTICE.md):

```console
python -X utf8 -m unittest discover -s tests -q
```

Game text, extracted Japanese, your translation, builds and saves stay out of
version control and out of releases. Only patch-only packaging may be published,
and only after a rights review.
