# v0.1 — English base-game build and installer

The base game is translated: **885 scenario files / 102,062 text items**, with a
Latin letter + punctuation atlas, an English default player name (`Kouno
Takaaki`, short form `Taka`) and native growth so long English lines fit. This
release publishes the **installer** that applies that work to your own dump.
No game data is redistributed: no executable, no archive, no extracted or
translated text, no save.

Runtime acceptance is still the outstanding step: the 24 observation slots for
this engine build (`work/qa/gen-latin-reload-results-to-fill.json`) are empty, so
`project.py check`, `build --engine-growth` and `gates.py check` continue to fail
closed by design, and rendering, pagination, branching, save compatibility and
full-game memory fit are unverified. See *What this release does not claim*
below.

## What is in this release

| File | Size | SHA-256 |
| --- | ---: | --- |
| `th2dxp_patch_gui.exe` | 38,051,439 | `1471584620770e8e6624034764bd93551088148b4f42ce8f61d32582a8c997eb` |
| `th2dxp_en-v0.1-installer.zip` | see the release page | see the release page |

`th2dxp_patch_gui.exe` is a PyInstaller one-file **windowed** build of
`tools/patch_gui.py` (MIT). It needs no Python installation and no
pre-decrypted `EBOOT.elf`: the game's own encrypted `EBOOT.BIN` is decrypted in
place with the single BLJM60381 application keyset, and `data.sdat` is decrypted,
patched and re-encrypted with two GPL-3.0 `make_npdata` builds that travel inside
the program as separate child processes. Source for all of it is in the
repository, so the binary can be rebuilt and compared.

The zip carries the program together with `README.md`, `NOTICE.md`, the project
documentation and the license texts that must accompany the bundled binaries:
`licenses/make_npdata-GPL-3.0.txt` (the two `make_npdata` executables),
`licenses/GenInterfaceJP-OFL-1.1.txt` (the re-drawn Latin atlas) and
`licenses/th2dxp_en-MIT.txt` (this project's own code).

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

What the program does carry is its **data patch** (23,375,611 bytes in 14 files,
built by `tools/patch_data.py`): 255 merged executable edit runs (38,865 bytes),
the appended 4,091,272-byte segment, and eleven pre-compressed archive chunks
(19,485,820 bytes) with their table rows. Nothing in it is decryptable on its
own; it is only meaningful applied to the matching pristine files.

## How to use it

You need your own lawful BLJM60381 dump installed in RPCS3. Then:

1. Run `th2dxp_patch_gui.exe`. No arguments, no console window.
2. Point it at the folder you installed in RPCS3 (the one containing
   `PS3_GAME`), or at `PS3_GAME\USRDIR` directly.
3. Press *Check*: it hashes `EBOOT.BIN` and `data.sdat` and accepts only the
   supported source archives or a previous recorded install of this patch.
4. Press *Install* and confirm. It copies both originals byte-exactly into
   `USRDIR\.th2dxp-backup\`, journaling their hashes first, then decrypts,
   patches, re-encrypts, authenticates the new archive and reads it back.
   The first run takes several minutes: `data.sdat` is 2.2 GB.
5. Start the game normally in RPCS3. The patched executable is written **as
   `EBOOT.BIN`**, which RPCS3 boots directly, so no separate ELF selection is
   needed.
6. *Restore original* puts the SELF and the archive back and verifies both
   hashes.

Command-line equivalents for scripts: `--self-test` (exit code 0 when the
program found its bundled patch data and both pinned helpers) and `--version`.

The program never launches RPCS3, never writes save data, never deletes a
backup, and refuses to run while `rpcs3.exe` is active. Its journal is
`USRDIR\.th2dxp-en-patch.json`; intermediates live in `USRDIR\.th2dxp-work` and
are removed on success or failure, so a failure at any step leaves your
installation untouched. Budget about **7 GiB** free on the game's volume for the
first install.

If your `USRDIR` currently holds an older test archive (for example
`be72aa94…`), the installer refuses to replace it rather than overwrite unknown
data: restore your own pristine `data.sdat` (SHA-256 `4509a4e9…`,
2,185,195,888 bytes) first.

### Why the rebuilt archive is not byte-identical to the build machine's

`make_npdata-pack` forges the NPD header hashes from the **path string of the
input DAT as typed** (`forge_npd_title_hash`), and the block keys derive from
that `dev_hash`. Two machines re-encrypting identical data therefore produce
different archives. The installer does not compare the container hash; it
authenticates every ciphertext block, checks the NPD/SDAT header fields and
size, then **decrypts the archive back** and requires the pinned DAT
`0438c3af…`. The journal records the archive actually installed, and that is
what recognises a previous install. `output_sdat_sha256` in the patch manifest
documents this build machine's archive only.

## What this release does not claim

- No runtime acceptance yet: the 24 observation slots for the current engine
  build are still empty, so the production gates stay closed by design. Anything
  you read here is verified offline.
- Rendering, pagination, branch reachability, save compatibility and full-game
  memory fit are unverified.
- Only the base game is covered; AnotherDays is out of scope for v0.1.
- The GenInterfaceJP font is used under the SIL OFL 1.1 shipped in
  `fonts/GenInterfaceJP-0.8.1/OFL.txt`; keep the notice with any redistribution.
- The installer contains Sony's single BLJM60381 application keyset, taken from
  public PS3 research (`RPCS3`, GPL-2.0, `Crypto/key_vault.cpp`), used only to
  decrypt your own copy in place. See `NOTICE.md`.
- No rights to the game's data, the original script or any translation are
  granted or implied.
