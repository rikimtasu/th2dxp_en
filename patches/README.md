# RPCS3 debug startup cheats — ToHeart2 DX PLUS

Import **[BLJM60381_debug_patch.yml](BLJM60381_debug_patch.yml)**. It provides:

- **Debug - Scene Selector** — the existing character/event-selection menu.
- **Debug - System Tests (Map, Calendar, Clock)** — the existing system-test menu.

## Use

1. Stop the game. Open RPCS3's **Manage → Game Patches**.
2. Drag `BLJM60381_debug_patch.yml` into the Patch Manager window and choose
   **Import**. This merges patches through RPCS3; do not replace your existing
   `patch.yml` or patch configuration file.
3. Expand **ToHeart2 DX PLUS**, select the matching executable entry, and enable
   **only one** of the two debug patches. They share an exclusive patch group.
   Save/apply the selection and close Patch Manager.
4. Boot the **original game executable**, or the exact supported English
   diagnostic below, and start a **new ToHeart2 story**. Complete the normal
   name/start screens. Do not use Continue or load an existing save.
5. Disable the patch and stop/restart the game to return to normal startup.
   These are startup code patches, not live controller toggles.

**Do not boot the prepatched debug-probe ELF when using these cheats.** Its PPU
hash is different, and its debug redirect is already built in.

Keep your executable paired with its appropriate `data.sdat`: original retail
assets for the original executable, or the diagnostic's paired archive for the
English diagnostic. The cheat changes neither the archive nor translation data.
**Do not save progress while testing developer scene jumps.** Use an isolated
profile if ordinary completion/system-data writes must also be avoided.

## Exact supported executables

| Executable | RPCS3 patch hash |
| --- | --- |
| Original Japanese BLJM60381 (`EBOOT.elf` source SHA-256 `8d8bc60d2b02d12f509a9a3ee9c126876ac8524d4f02c7871206aca9bd66e828`) | `PPU-632efe7e535a8406c75c289308b61a5ad6653918` |
| `build/english-progress-diagnostic-20261029/EBOOT.elf` (SHA-256 `2ad4f9a2a538240336831bd1ab1db2faadc8885f7119faa1b8b04cfd08d22e39`) | `PPU-3c761fee9609f87cd41cfce7a5dfb32a2ffd4aa9` |

`All` in the game's app-version field does **not** make these universal cheats:
the exact executable PPU hash must still match. A different release or rebuilt
English ELF needs its own validated entry. If no patch applies, compare the
loaded executable's `PPU-...` hash in RPCS3's log; do not remove the hash binding.

## Verification and limits

The YAML was parsed offline, and all four hash/mode variants were applied in
memory and checked against their manifests. The two original-executable
variants reproduce the previously staged debug ELFs byte-for-byte. Only the
five instructions at VA `0x8BC9C`–`0x8BCAC` are written; these are **virtual
addresses**, not ELF file offsets. The original scene-selector ELF's menu,
submenus and scene jumps were confirmed by the user in the same session.

On **2026-10-29**, the user confirmed that **both Scene Selector and System
Tests RPCS3 patches work on the original executable**. This accepts the original
executable's Patch Manager delivery and both debug modes. The earlier confirmation
also covers scene-selector submenus and scene jumps. Individual system-test cases,
loaded hashes and emulator version were not separately supplied; exhaustive test
coverage, save compatibility and production acceptance are not inferred.

The **English-build variants remain runtime-unverified**. No RPCS3 configuration,
installed game file, archive or save was modified by the agent.

Evidence: `work/qa/rpcs3-debug-patch-manifest.json`,
`work/qa/rpcs3-debug-patch-verification.json`, and the user observation at
`work/qa/observations/rpcs3-debug-patches-original-20261029.json`.
All nine focused debug tests pass and the regenerated YAML matches this file
exactly. The earlier full run passed 243 tests; the confirmation-time rerun hit
seven errors and three failures in unrelated installer tests because RPCS3 was
running. No process was stopped or process guard bypassed.

## Regenerate for these workspace images

The generator refuses existing output files; choose new names when preserving
earlier patches and reports:

```console
python -X utf8 tools/rpcs3_debug_patch.py --additional-elf build/english-progress-diagnostic-20261029/EBOOT.elf --output patches/BLJM60381_debug_NEW_patch.yml --report work/qa/rpcs3-debug-patch-NEW.json
```

It verifies the original hook and target-name pointers before emitting entries.
It never installs them. RPCS3's PPU hash is computed from big-endian program-header
type/flags plus nonempty LOAD virtual address, memory size and file data, not
from whole-file SHA-1. The implementation and YAML schema were checked against
[RPCS3 revision cd0c200b](https://github.com/RPCS3/rpcs3/tree/cd0c200b9f45427a2a55dc50c99993f2b100a987):
`rpcs3/Emu/Cell/PPUModule.cpp`, `Utilities/bin_patch.cpp`/`.h`, and
`rpcs3/rpcs3qt/patch_manager_dialog.cpp` (drag-and-drop import).

Further reverse-engineering details: [debug-scripts.md](../docs/re/debug-scripts.md).
