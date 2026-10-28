# v0.2 — QC corrections and smaller dialogue

This preview release contains the **same gameplay payload the player tested** in
the combined QC/85% test patch. Only installer branding/version metadata changes
for v0.2; no new scenario, engine, font or archive-content changes were introduced
after that test.

## Changes from v0.1

- **85% normal-dialogue size**, retaining the original character-spacing rules.
  Shared font metrics, UI graphics and the separate backlog constructor are unchanged.
- **1,928 text-item corrections across311 editable files**, including **457 spacing
  fixes**, source-bound name corrections, selected meaning/grammar repairs,
  native-fragment re-cuts, restored honorifics and paired quotation marks.
- Preserves intentional word splits, the explicit Manaka/Aika pronunciation joke,
  source-present alternate names and relevant kanji discussions.
- Installer completion now reports the verified executable/archive hashes correctly.
- Still self-contained: **one game-folder selection, no Python, no separate patch data**.
  Both previously supported original archive variants remain supported.

## Player testing and limits

The player reported “tested, look good” and supplied three1280×720 screenshots:
the classroom scene showing Yuuji's keeping-her-company line on the displayed page,
the following apology scene with readable spacing, and the opening Konomi visit.
These support the shown text/layout and the player's general positive report.
The RPCS3 version, boot-time hashes, audio timing, save/load and other routes were
not separately documented in this report.

**No dedicated page/voice synchronization fix is included**, and the screenshots
alone do not establish audio timing. Most joined-word-boundary candidates still
need contextual review. This is not a whole-game bilingual sign-off or completion
of the full runtime gate. AnotherDays is not covered.

The exact tested/released decrypted-game output is10,687,672 bytes, SHA-256:

`0a9c3afb553058443305799cd389600ca665e55aa956be7a77ddf1f62177ead9`

That full game executable is **not** a release asset. The archive recipe and all11
font/UI replacement chunks are unchanged from the previous installer; encrypted
container hashes may vary by local rebuild path, so the installer authenticates
the archive and verifies its decrypted DAT content.

## Install or upgrade

1. Close RPCS3 and keep personal saves backed up. Prefer a disposable copy of your
   own lawful **BLJM60381** dump for this preview.
2. Download `th2dxp_en-v0.2-installer.zip`, extract it and run
   **`th2dxp_patch_gui.exe`**. The standalone executable asset is the same program.
3. Select the game folder (or `PS3_GAME/USRDIR`). If an older patch is installed,
   select **Restore original**, then **Install**. Keep `.th2dxp-backup` intact;
   manually modified folders without original backups require a fresh copy of your dump.
4. Start a **fresh ToHeart2 New Game**. Changed scenario offsets make older builds'
   execution-position saves unsafe; use disposable same-build save slots only.

The program verifies rebuilt files, preserves original backups and never starts
RPCS3 or edits saves. Allow about7GiB free for an initial install. No complete
EBOOT, SDAT, extracted script, PC reference or save is distributed as an asset.

## Attribution and packaging

The ZIP includes the installer, these instructions, `NOTICE.md`, the project MIT
license, GenInterfaceJP's OFL and the standalone archive helpers' GPL-3.0 notice.
Corresponding GPL helper source is identified in `NOTICE.md` and `upstreams.json`,
with the packer repair in `tools/sdat_pack.c` and `tools/build_sdat_tool.py`.
The installer ships only patch payloads, not complete game files; original
game-content rights remain with their owners. No Ittaku reuse permission is
claimed, and no new PC-reference import is included in this QC release.

## Release assets

| File | Size | SHA-256 |
| --- | ---: | --- |
| `th2dxp_patch_gui.exe` | 38,068,631 bytes | `72ca43b71577dcd8425012e1be7dea47f0b77ef10f9a888d41340cc4df96f8ed` |
| `th2dxp_en-v0.2-installer.zip` | See the release page | See the release page |

The installer was rebuilt only for v0.2 branding/version metadata; its embedded
executable patch and all11 archive chunks are byte-identical to the player-tested
version. Its extracted executable payload reproduces the tested ELF exactly;
frozen `--self-test` and234 synthetic tests passed. These checks are not additional
gameplay observations.
