# Ittaku PC main-game reference

## What is actually supplied

`[ittaku-subs]th2/` is the Ittaku-subs **ToHeart2 Xrated PC translation patch**, not a subtitle collection or a PS3 patch. Its README and installation instructions are dated 24 September 2017. Conman is credited as translator/team leader, with programmers, editors, proofreaders, graphics staff and translation helpers listed in the supplied `README.TXT`. Preserve those credits. No permission to reuse or redistribute the translation in this project has been established; a public download or a patch README is not a reuse licence.

Both supplied batch files decode `sdt.vcdiff` against an existing original PC `SDT.PAK`. They also patch graphics/fonts, move originals into `BACKUP`, and rename an executable. **Do not run either batch file.** The other supplied assets are `grpfull.vcdiff` (graphics including decensoring), `grpui.vcdiff` (UI-only alternative), `fnt.vcdiff`, the patched PC executable `ToHeart2New.exe`, and `xdelta3.exe`. None is a source subtitle file. The reference tool never runs the game executable or either batch file, never touches an installed game, and never starts RPCS3.

## Evidence and current limitation

Read-only inspection with the bundled xdelta `printhdr` and `printdelta` produced:

| Property | Observed value |
| --- | --- |
| `sdt.vcdiff` size | 3,009,587 bytes |
| SHA-256 | `bea532026ba8301b037820b8d24a85b981f399c2487e29baef62ddd7eb9db2d1` |
| VCDIFF version | 0; default code table; no secondary compression |
| Application header | `sdt.pak//sdt_orig.pak/` |
| Windows | One; `VCD_SOURCE` and xdelta `VCD_ADLER32` |
| Original source segment | Offset 0, length 3,109,610 bytes |
| Target archive length | 3,299,331 bytes |
| ADD/RUN data section | Offset 57, length 2,786,479 bytes |
| Instruction section | 105,905 bytes |
| Address section | 117,146 bytes |
| Target bytes emitted by ADD / COPY / RUN | 2,786,478 / 512,845 / 8 |
| Expected target Adler-32 | `9C1D5E5E` |
| Bundled `xdelta3.exe` SHA-256 | `2f1010a42dc3a99849fd2a4516d58e74df7c37e268e0718c9040b464c170a075` |

The application header's source filename is descriptive, not a requirement to rename the input. The 3,109,610-byte value is the referenced **source segment length**, not a verified exact source-file size or a base-file hash.

The VCDIFF literal section is accessible without the original, but its bytes are **compressed PC archive payload**, not a plain English script. Observed directory changes recur at 36-byte intervals; payloads contain the flag/token structure and `LF` prefixes consistent with Leaf KCAP/LZSS resources. The original archive header, filenames, and numerous compressed-stream/control bytes are copied from the missing original. For example, the target starts with a 40-byte source COPY, so its signature cannot be verified from the patch alone. A partial reconstruction leaves 289,971 target bytes unknown even after propagating known target-to-target copies. Filling those bytes with zeroes would fabricate data and does not produce a valid archive.

The patch **alone** does not yield a verified complete English script or dialogue-line extraction. Some exact ASCII byte fragments can be indexed; most contain compression tokens or chopped words. Failure to find a name or phrase in the raw fragment index says nothing about translation coverage.

### Verified local reference discovered during setup

A bounded search found the supplied `SDT.PAK`, already patched. Its **3,299,331-byte size** and **Adler-32 `9C1D5E5E`** match this VCDIFF's target. Its SHA-256 is `e709dd30f4ff82b83fec30ed9378f1162b3b5a1ec51537beecdffe27a36028f4`. The tool verifies target length/checksums before reading it as KCAP, leaving the installed PC game untouched.

The actual archive decoder recovered **48,424 printable-ASCII text candidates across 775 archive entries**, including readable English dialogue and engine `\\k` / `\\n` sequences. This is a usable reading/search reference, **not** a claim that candidates are complete dialogue lines or aligned to PS3. No original PC archive is needed for this already-patched route. A matching unmodified PC `SDT.PAK` is needed only for the alternative xdelta reconstruction route.

```console
python -X utf8 tools/ittaku_reference.py index --patched-sdt "<path-to-your-SDT.PAK>"
python -X utf8 tools/ittaku_reference.py search "Konomi" --kind decoded --format json --limit 5
```

`--patched-sdt` and `--source-sdt` are mutually exclusive. The pre-patched route does not run xdelta, copy into the installation, or execute any game; it verifies the supplied archive against every target window's Adler-32 before decompression and records its path/hash in the local manifest. Adler-32 is format-integrity evidence, not a cryptographic authenticity guarantee. Retain the observed SHA-256 as a provenance identifier.

## Commands

Use Python 3.10 or newer. Commands below are shown from the project root; the script derives the root from `__file__`, so invoking it by its absolute path from another working directory works too. Relative option paths are resolved against the project root, not the current directory.

### Index only the raw patch (no PC reference archive)

```console
python -X utf8 tools/ittaku_reference.py index
```

This is a pure-stdlib, read-only parse of the patch; it does **not** run xdelta or require an original archive. It writes only ignored `reference/ittaku/index.jsonl` and `reference/ittaku/manifest.json`. Each raw candidate is a strict printable-ASCII run of at least six bytes, containing at least four ASCII letters, wholly within one verified VCDIFF ADD instruction. It does not concatenate adjacent instructions, resolve missing source COPYs, guess compression flags, invent punctuation, or manufacture sentences. RUNs and COPYs contribute format statistics, not misleading raw-text records.

Optional controls:

```console
python -X utf8 tools/ittaku_reference.py index --min-length 8
python -X utf8 tools/ittaku_reference.py index --patch-dir "[ittaku-subs]th2"
```

The current index command rebuilds the index deterministically for the chosen input/options. A raw-only rebuild removes decoded records from the index, but does not delete an earlier local `reference/ittaku/SDT.PAK`; the manifest records whether the **current index** used an original. Temporary files are removed automatically. Outputs are never intended for distribution.

### Search exact fragments

```console
python -X utf8 tools/ittaku_reference.py search "thank"
python -X utf8 tools/ittaku_reference.py search "thank" --format json --limit 50
python -X utf8 tools/ittaku_reference.py search "thank" --kind literal
```

Search is a case-insensitive exact substring scan, not fuzzy matching, machine translation, sentence alignment or a Japanese-to-English lookup. Results preserve original spelling and punctuation. `--limit` limits displayed records; the reported total still counts all matches. `--kind` accepts `all`, `literal`, or `decoded`.

Raw results are visibly labelled `literal/fragment`. Their bytes are verified against the patch, **not verified as dialogue**. Query shorter words when compression splits a phrase. Treat token-containing results as byte-recovery leads, not text to paste into a PS3 translation.

### Optional decode with your original PC archive

```console
python -X utf8 tools/ittaku_reference.py index --source-sdt "<your-PC-dump>/SDT.PAK"
python -X utf8 tools/ittaku_reference.py search "Konomi" --kind decoded --format json
```

Only this option runs the supplied Windows `xdelta3.exe`, as a direct subprocess equivalent to:

```console
"[ittaku-subs]th2/xdelta3.exe" -d -s "<your-PC-dump>/SDT.PAK" "[ittaku-subs]th2/sdt.vcdiff" "reference/ittaku/decode-<temporary>/SDT.PAK"
```

The source is read-only input; the batch files are not involved. A failed xdelta decode is an error, not an invitation to disable checksums. After xdelta succeeds, the tool checks the declared target length, detects supported KCAP directory layouts, decompresses packed entries using Leaf's 4 KiB LZSS ring format, and collects printable ASCII runs. Unsupported/truncated archive structures fail explicitly. Decoded and cumulative packed-entry expansion are limited to 256 MiB. Once processing succeeds, the patched archive is stored at ignored `reference/ittaku/SDT.PAK`; the index contains both raw fragments and decompressed text candidates. Repeating the operation replaces only local generated outputs. Hashes of the original, patch, decoder, and decoded archive are retained in the manifest; the source hash is checked again before publication.

The KCAP/LZSS decoder has been exercised against the real, checksum-matching **already-patched** local archive described above. The alternative original-input/xdelta branch has not been exercised because a matching unmodified original was not identified. The original-source option is not needed to use the verified patched reference.

## Record provenance and completeness

The JSONL file is UTF-8 with one independently readable JSON object per result. The manifest records input path/hash, VCDIFF sections, source requirements, options, credits and record counts.

- All records contain an ID, the patch SHA-256, exact text, byte length, classification, and a short hexadecimal context.
- `literal` records contain absolute patch-file offsets, global target offsets, VCDIFF window number, opcode offset, ADD start/length, and run boundaries. These offsets are byte coordinates, never PS3 script IDs. `status=fragment` and `line_complete=false` are deliberate: an ADD instruction boundary is not a dialogue boundary, and compressed data is not a complete line.
- Optional `decoded` records contain the archive entry name/index, entry archive offset/size, and the uncompressed entry-relative byte offset. `status=bounded_text_run` means a maximal printable-ASCII run, **not a verified complete dialogue line**. `line_complete=null` means script-level boundaries are unknown. A quote or apparent full stop does not promote a record to a full sentence.
- ASCII-only extraction omits CP932 punctuation, Japanese text and non-ASCII names. Script control codes may split runs. Compressed bytes may coincidentally resemble words. The index is reference material requiring human review, not a translation source format or an exhaustive text extractor.

## Source-backed PC bytecode reference — 2026-10-24

The user supplied [ripdog/th2xr-portable](https://github.com/ripdog/th2xr-portable), a C++20/SDL3 rewrite referencing Aquaplus's published GPL engine. The inspected revision is **`14e8521ca999dfa9787b090c1c965ef3c6227530`**. Its GPL-2.0 implementation stays separate from the independent MIT Python wrapper. The linked helper `tools/pc_reference_dump.cpp` is explicitly GPL-2.0; see `NOTICE.md`. The engine itself was not launched.

Relevant pinned sources:

- [`scenario.hpp`](https://github.com/ripdog/th2xr-portable/blob/14e8521ca999dfa9787b090c1c965ef3c6227530/src/scenario.hpp) / [`scenario.cpp`](https://github.com/ripdog/th2xr-portable/blob/14e8521ca999dfa9787b090c1c965ef3c6227530/src/scenario.cpp): little-endian `L`, `F`, declared size, 256 block addresses; bytecode begins at entry offset **1,032**. Block addresses are one-based within bytecode.
- [`bytecode.cpp`](https://github.com/ripdog/th2xr-portable/blob/14e8521ca999dfa9787b090c1c965ef3c6227530/src/bytecode.cpp) and legacy [`Escr.h`](https://github.com/ripdog/th2xr-portable/blob/14e8521ca999dfa9787b090c1c965ef3c6227530/legacy/ToHeart2/ScriptEngine/mes/Escr.h): instruction boundaries and length-prefixed event operands, rather than printable-run guesses.
- [`bytecode_info.cpp`](https://github.com/ripdog/th2xr-portable/blob/14e8521ca999dfa9787b090c1c965ef3c6227530/src/bytecode_info.cpp) / [`event.cpp`](https://github.com/ripdog/th2xr-portable/blob/14e8521ca999dfa9787b090c1c965ef3c6227530/src/event.cpp): standalone archive/bytecode inspection and event operand decoding, including CP932-to-UTF-8 conversion.

The standalone bytecode inspector was compiled with the available UCRT64 GCC, without SDL or game execution. Source URLs/hashes and the full upstream license are retained in `work/upstream/th2xr-parser/source-manifest.json` and `LICENSE.txt`; the legacy header is in the adjacent `legacy/ToHeart2/ScriptEngine/mes/` path required by upstream.

```console
g++ -std=c++20 -O2 -static -I work/upstream/th2xr-parser work/upstream/th2xr-parser/archive.cpp work/upstream/th2xr-parser/scenario.cpp work/upstream/th2xr-parser/bytecode.cpp work/upstream/th2xr-parser/event.cpp work/upstream/th2xr-parser/expression.cpp work/upstream/th2xr-parser/event_metadata.c work/upstream/th2xr-parser/bytecode_info.cpp -liconv -o work/upstream/th2xr-parser/th2-bytecode-info.exe
work/upstream/th2xr-parser/th2-bytecode-info.exe "<path-to-your-SDT.PAK>" SetMessage2
```

Observed exit **0**, empty stderr: **21,915 `SetMessage2` instruction records in 788 entries**. Complete captured operands remain private at `work/pc-reference/SetMessage2.txt`; command, source/archive provenance and output SHA-256 are in `work/pc-reference/portable-parser-report.json`. These records supersede ASCII-fragment boundaries for this opcode only. They do **not** constitute all PC dialogue opcodes, verified PS3 sentence alignment, route membership or runtime coverage.

Opening PC record `010301000.SDT`, bytecode offset 122, corresponds to entry text offset `0x486`. Its full English sentence was checked against PS3 unit 0 Japanese and recorded at `work/alignment/opening-reviewed.json`, without editing `script/`. Removing the PC hard wrap yields 66 CP932 bytes versus 62 original PS3 text bytes across the two fragments. No text was shortened; growth remains required and unvalidated.

The first filtered Git checkout failed to retrieve promised blobs; the successful inspection used only commit-pinned raw source downloads with recorded hashes. The initial inspector compiled legacy metadata as C++, producing upstream string-literal-to-`char*` warnings. The complete extractor below instead compiles that metadata as **C** (`g++ -x c -c`) and links the resulting object with C++20; warnings are not suppressed.

The PC sources do not supply a PS3 native renderer correction. Legacy text layout uses half/full fixed font widths, whereas the PS3 drawing path uses proportional ASCII metrics and different angle-command state. GPL engine licensing also does not grant Ittaku translation reuse rights.

### Complete encoded-string extraction

The current reference command walks **every instruction and every encoded string operand**, rather than selecting one message opcode:

```console
python -X utf8 tools/pc_reference.py extract --upstream work/upstream/th2xr-parser --compiler "<path-to-g++>"
```

The successful output is preserved at `work/pc-reference/full-reference/`; the command refuses to overwrite it. `manifest.json` records source/compiler/helper/archive hashes, commands, license, coverage and output hashes. `text-operands.jsonl` retains strict CP932 text, original raw bytes, typed operands, filename/instruction/argument identity and byte coordinates. The independent Python archive/operand reader checked **all decoded entry bytes**, instruction bounds, block targets and text bytes against the C++ helper.

| Observed extraction | Count |
| --- | ---: |
| Archive entries | 1,275 |
| Valid scenario entries | 1,273 |
| Instructions | 123,413 |
| Encoded string operands | 53,448 |
| `SetMessage2` operands | 21,915 |
| `AddMessage2` operands | 28,222 |
| `SetSelectMes` choice operands | 1,324 |

Two non-scenario entries remain inventoried, including a zero-stored-size metadata marker at EOF; neither is fabricated dialogue or silently parsed as a scenario. All encoded strings are covered, **not runtime-generated strings, external graphical/native text, visibility, translation quality or PS3 correspondence**. No game, VM, renderer or emulator was executed.

### PS3 structural candidates, not automatic alignments

The earlier full-source run is preserved at private `work/alignment/normalized-page-candidates/`:182,111 PS3 message records in32,937 marker groups, excluding native choice companions. It used exact native filenames plus unique, contiguous, equally sized marker sequences to propose constant read-ID offsets; PS3 IDs are global while PC IDs restart per file.

That historical output has718 structurally comparable files/16,172 unverified structural candidates and291 structurally unresolved files. It is not the current base-only review queue and does not establish edition ownership. Following `AddMessage2` operands remain source-order neighbors rather than asserted runtime ownership across branches/resets.

### Current base-only message review queue

`python -X utf8 tools/alignment_candidates.py` now writes **`work/alignment/base-game-message-candidates/`** and refuses overwrites. It requires complete source/payload-bound normal-title membership from `work/scenes/scenario-membership.json`, rejects unresolved/partial/contradictory scope, and verifies selected immutable JSON hashes. AnotherDays, separate stories and inactive programs are excluded independently of PC availability.

The actual command exited0. Its18,961 groups contain **all101,829 base-message records exactly once**, verified against the complete coverage inventory with no other-story leakage. **233 base native choice captions are explicitly outside this queue**; together they account for the102,062-record base denominator. The manifest binds source, membership, baseline and PC-reference hashes. Scope ownership never promotes a candidate to Japanese-context or import approval.

| Message-group review state | Groups |
| --- | ---: |
| Unique structural candidate, context unverified | 15,997 |
| Nonisomorphic marker sequences | 1,934 |
| No exact PC filename | 1,026 |
| No PS3 read marker | 4 |

Missing PC filenames/marker correspondence do not prove PS3-exclusive content; search/context review remains required. Every candidate retains `context_verified:false` and `automatic_import_allowed:false`; originals, controls and reference operands stay separate. The three new scope regressions pass. No translation, reference input or runtime gate changed.

### Bounded context findings — 2026-10-26

`work/alignment/ittaku-context-review-2026-10-26.json` checks three groups/22 Japanese PS3 fragments against five actual structured PC operands, with recomputed candidate/reference/archive/baseline hashes and exact raw-byte verification. Opening waking/curtain actions and the cafeteria/Tonami scene correspond at the quoted scope. It does not approve import, source-order AddMessage2 ownership, other pages or coverage.

The cafeteria passage exposes a concrete **PS3 meaning conflict**: `雄二でも誘うかと思ったが` has the narrator consider inviting Yuuji; PC English reverses that to Yuuji inviting him. `外で食べるらしく` does not supply eagerness, and `四人でなければダメなんだ` requires four people rather than merely preferring everyone together. Adapt against PS3 Japanese; do not blindly copy structurally aligned English. Without the original Japanese PC archive, this does not establish whether the discrepancy came from edition changes or the fan translation.

The review stays private/preparatory: scripts/candidates/baselines remain unchanged, completeness credit is zero, and bulk insertion still requires the genuine runtime gate. Native choices retain their separate diagnostic-only review in the paired manifest; this does not align all233 base choices.


## Use in the PS3 project

Use Ittaku as the preferred **main-game reading/reference source**, once a candidate passage can actually be read. Xrated PC and DX PLUS PS3 differ in engine, script layout, scenes/content, routes, voice timing, and edition-specific additions/removals. PC adult content cannot simply be carried into the console release. The supplied PC README explicitly disclaims work on Another Days; it is not evidence of translated DX PLUS/Another Days material.

There is no automatic import, sentence alignment, guessed speaker/route mapping, or unreviewed copying. Do not assign a PS3 line solely because the English fragment resembles nearby Japanese. Confirm the Japanese passage, scene and edition first; keep reviewed PS3 translation separate from these ignored reference assets. Credits must be preserved and reuse permission resolved before redistribution of borrowed translation material.

## Format research

- [RFC 3284](https://www.rfc-editor.org/rfc/rfc3284): VCDIFF integer encoding, default opcode table, ADD/COPY/RUN and source requirements. The parser also recognizes xdelta's application-header and Adler-32 extension bits observed in this patch.
- [GARbro Leaf KCAP format reader](https://github.com/morkt/GARbro/blob/master/ArcFormats/Leaf/ArcPAK.cs): evidence for directory layouts and packed-entry headers/LZSS, not a source of game text. The local tool implements the format independently; no GARbro dependency is required.
- Supplied `[ittaku-subs]th2/README.TXT`, `INSTALLATION_INSTRUCTIONS.TXT` and both batch files: patch purpose, credits and original-input requirements.
- [Development thread linked by the supplied README](https://forums.fuwanovel.net/topic/10250-to-heart-2-for-pc-translation-project/): attribution pointer, not a reuse-permission claim.
