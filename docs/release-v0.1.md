# v0.1 — English base-game build and installer

The base game is translated: **885 scenario files / 102,062 text items**, with a
Latin letter + punctuation atlas, an English default player name (`Kouno
Takaaki`, short form `Taka`) and native growth so long English lines fit. The
build is assembled locally from your own dump; this release publishes the
installer and the documentation that produce and install it, and redistributes
no game data.

Runtime acceptance is still the outstanding step: the 24 observation slots for
this engine build (`work/qa/gen-latin-reload-results-to-fill.json`) are empty, so
`project.py check`, `build --engine-growth` and `gates.py check` continue to fail
closed by design, and rendering, pagination, branching, save compatibility and
full-game memory fit are unverified. See *What this release does not claim*
below.

## What is in this release

| File | Size | SHA-256 |
| --- | ---: | --- |
| `th2dxp_patch.exe` | 7,730,680 | `726b467219a198c0680e25d47a57b13254730e4dd7d4601ff2b89d8ae4959eb6` |
| `README.md`, `NOTICE.md`, `OFL.txt` | — | see the repository |
| `docs/` (`status.md`, `fonts.md`, `linguagacha.md`, `manual-testing.md`, …) | — | see the repository |

`th2dxp_patch.exe` is a PyInstaller one-file build of `tools/patch_game.py`
(MIT). It needs no Python installation. Source and tests are in the repository,
so the binary can be rebuilt and compared.

## What is deliberately *not* published

- the patched `EBOOT` (10,687,608 bytes, `a31bdd83…`),
- the repacked `assets/data.sdat` (2,202,570,928 bytes, `bbb932bf…`),
- the decrypted original `EBOOT.elf`, any extracted Japanese text, any
  translated text export, and any save data.

Those contain or derive from the game's copyrighted data, and the archive is
larger than GitHub's 2 GB per-asset limit anyway. A patch that is only a
checksum-verified full copy of a game archive cannot be published as a delta
either: the staged archive shares **zero** identical 16 KiB ciphertext blocks
with the pristine one (the container chains block hashes), so an xdelta payload
is the entire 2,100.5 MiB file.

## How to use it

You need your own lawful BLJM60381 dump, a decrypted `EBOOT.elf`, and a locally
produced build directory (see the repository README and
`docs/linguagacha.md`). Then:

```console
th2dxp_patch.exe status        --game-dir "...\PS3_GAME\USRDIR"
th2dxp_patch.exe apply  --build build\english-v0.1 --game-dir "...\PS3_GAME\USRDIR"          # dry run
th2dxp_patch.exe apply  --build build\english-v0.1 --game-dir "...\PS3_GAME\USRDIR" --apply  # write
th2dxp_patch.exe restore --game-dir "...\PS3_GAME\USRDIR" --apply
```

The tool backs the original `EBOOT.BIN` (SELF) up byte-exactly to
`USRDIR\.th2dxp-backup\EBOOT.BIN`, writes the patched ELF **as `EBOOT.BIN`**
(the form RPCS3 boots directly), backs `data.sdat` up before replacing it,
records everything in `USRDIR\.th2dxp-en-patch.json`, and refuses to touch an
unrecognized archive or a file whose SHA-256 does not match its build report. It
never launches RPCS3 and never writes saves.

## What this release does not claim

- No runtime acceptance yet: the 24 observation slots for the current engine
  build are still empty, so the production gates stay closed by design.
- Rendering, pagination, branch reachability, save compatibility and full-game
  memory fit are unverified.
- Only the base game is covered; AnotherDays is out of scope for v0.1.
- The GenInterfaceJP font is used under the SIL OFL 1.1 shipped in
  `fonts/GenInterfaceJP-0.8.1/OFL.txt`; keep the notice with any redistribution.
- No rights to the game's data, the original script or any translation are
  granted or implied.
