# Fonts and graphics text

## Recovered original assets

`python -X utf8 tools/assets.py prepare` decrypts the user's installed `data.sdat` into ignored `work/assets/data.dat`, using pinned standalone `VelocityRa/make_npdata` (Hykem, GPL-3.0). It does not run RPCS3, require a game-specific key for this SDAT, or change the installation. The wrapper requires upstream integrity/decryption completion messages, exact NPD-declared length, source hash preservation and a valid DAT index before promoting the output.

Observed archive: 2,180,935,968 bytes, **3,516 entries**, SHA-256 `dffdd141be62540669057a5db3eaf71b561c0b993683ee1c86d96d851088c7a2`. Full provenance: `work/assets/decryption.json`; upstream log: `work/assets/decryption.log`.

`python -X utf8 tools/assets.py inspect` enumerates the archive with TH2DXP_KIT, extracts only font candidates through read-only mmap access, and decodes the original swizzled textures with the kit's dedicated TPL implementation. Catalog: `work/assets/catalog.json`; font details/hashes/images: `work/assets/font-report.json`.

| Asset | Texture dimensions | Storage |
| --- | --- | --- |
| `_initial/font.tpl` | Two 1536 × 1536 textures | A4R4G4B4, swizzled; separate RGBA glyph planes exported |
| `_initial/font1.tpl` | 1536 × 96 | Same format |
| `_initial/font2.tpl` | 1536 × 48 | Same format |
| `_initial/font3.tpl` | 1536 × 96 | Same format |

The main `font.0.R.png` was visually inspected. It contains Latin uppercase/lowercase letters, digits and punctuation alongside Japanese glyphs. A crop is preserved as `work/assets/latin-atlas-evidence.png`. Auxiliary font images contain Japanese/special glyph subsets; do not assume all fonts have the same coverage.

## What this clears

The decrypted-archive and stored-Latin-glyph prerequisites are no longer missing. No replacement font is presently needed merely to obtain Latin glyph pixels. The original font remains unchanged and local; no font redistribution permission is implied.

## What remains runtime-dependent

User runtime screenshots now prove uppercase A–Z, lowercase a–z, digits 0–9 and mixed `IiLl` / `WwMm` render through the existing font in the opening narration window. The logged `TH2_EN_QA.elf` file hash matches the old raw probe. Evidence: `work/qa/probe-observations/opening-flow-failure.json`.

**Earlier probes failed**, but user screenshots support the targeted VWF correction: complete F01–F16, clear F02/F08 flowers and legible F09/F11 Japanese continuations. The capacity build shows the complete English sentence across two lines, then following Japanese; the user reports spare-save loading worked. Yellow English text is backlog. The old fixed-advance save caption overflow is now corrected in **`build/save-preview-probe/EBOOT.elf`**: the user's `16_56_54` DataLoad screenshot shows proportional Latin spacing and the excerpt/ellipsis inside slot005, with Japanese rows legible. Original fonts, dialogue and serialized saves are unchanged. This accepts the shown preview, not arbitrary captions or all other windows. No repeat or rebuild is needed; see [`pretranslation-gates.md`](pretranslation-gates.md) for remaining checks.

**Original font inputs remain immutable; the user later approved a staged GenInterfaceJP Latin cutover.** The initial VWF correction retained every glyph. After source sampling failed to establish an additional g geometry defect, the user explicitly selected GenInterfaceJP for Latin letters/digits. This permits generated Latin pixels/metrics, not installed-file edits or replacement of Japanese/punctuation/private glyphs. Preserve CP932 semantics; the incompatible PC font patch remains irrelevant.

## Original glyph measurement

The original main atlas was checked against all 95 printable ASCII metric pairs: space is blank and the other 94 ink bounds match. If the metric pair is `(a,b)`, the original drawing transforms make the pen advance `b+6` and visible right ink edge `b+3`. Bounds retain at least a full cell and include wider ink: underscore has advance 53 / right ink 50, exceeding the original 48-unit cell.

The staged correction retains source font selection, per-span scale and original first-use fallback ordering. All four source font setups supply fallback width 46; the read-only predictor does not initialize the original drawing cache early. Full source contracts, cave mapping and software proof limits: [`re/README.md`](re/README.md#original-font-vwf-diagnostic--2026-10-24).

## Opacity capacity is independent of width

The later pagination-only runtime failure includes faded/missing glyphs at valid X positions. Native font copy59178 handles only32 opacity bytes; consumer59878 then aliases raw byte length/reveal fields for glyph32 onward. Narrow English exceeds that count without exceeding the original256 glyph-record capacity.

`tools/native_runtime_text_patch.py` moves all opacity producers/consumers to256 owned entries and initializes a dedicated predecessor for native tail fill. Font pixels, metrics and requested text remain unchanged. Encoded copy/consumer checks cover all256 entries; held-page renderer replay reaches full opacity at its modeled draw boundary. Current target/evidence: `build/runtime-text-probe/`, not the failed4150 pagination-only build. Actual GPU rendering remains unobserved.

## Full glyph-cell edges and word-aware wrapping

The user's five newer images reach HEND but report the `g` appearance and show word splits. The atlas and enlarged capture contain a descender; that comparison alone does not establish the exact missing pixels. Native queue1BCB8 stores inclusive screen/UV endpoints, while backend1B47C..1B69C used them as quad edges, reducing requested extents by one unit. `native_typography_patch.py` converts both endpoint pairs before the original transform; font assets, glyph origins and colors remain unchanged.

Encoded queue/vertex replay checks `gjpqyAあ` at three scales. Word-aware geometry preserves original metrics/raw controls and retains character fallback for overlong tokens.83c58c0f gameplay screenshots now show visible descenders and whole-word pages through HEND; that is scoped visual evidence, not all-surface acceptance. Current paired target/form: `build/backlog-render-probe/` and `work/qa/backlog-render-results-to-fill.json`. No replacement font is needed for the native cell-edge correction.

## Readable UI redraw and native string layout

`tools/ui_graphics.py` uses the original48px Latin atlas at a **uniform scale**, not a replacement face or horizontal condensation. It wraps complete words and rejects cells below the readability floor instead of truncating English. The final source-size previews contain247 labels in10 TPLs/17 records,70 with whole-word wrapping and none horizontally squeezed. Main labels are at least14px; only rotated calendar captions may use12px (the current minimum is13px). Inspect `work/ui/final-graphics/previews/` at native size.

Footer legends are20px in13 repacked cells of the unchanged256×128 L8 record; their source rectangles move with the native table. Complete music roles are16px in96×44 source banks, drawn atX752/1000. Native artist names use the existing0.35 scale (16.8px) atX852/1100; titles keep the original24px font. Map locations use whole-word lines, and save story tags use high-contrast pale panels. No font TPL, glyph plane, music audio or scenario text is redrawn.

`native_ui_patch.py` binds142 static English strings to148 source records, retaining six personal defaults/dictionary values. It preserves printf order, `%d0`, CP932 round trips and private glyphs; longer labels/help use full pointers. Only raw option-value consumers8E80C/8E840 use the proportional clone. Dialogue594E8 already positions single-character records by bearing, so59488 keeps its original1BE28 call. Other fonts/kana grids remain unchanged. Name help uses actual centered1C8B8 measurement1C5B8/drawing1C178; it never used59488.

## Soundtrack credit provenance

The user supplied [ToHeart2 Original Soundtrack — VGMdb1938](https://vgmdb.net/album/1938) and [ToHeart2 Complete Soundtrack — VGMdb26275](https://vgmdb.net/album/26275). Direct album access returned403/Cloudflare; no CAPTCHA was bypassed. Cached MusicBrainz releases carry the exact VGMdb URL relationships; the complete release has four discs/63 tracks. `work/ui/music-credit-reference.json` retains Japanese correspondence for all51 PS3 music rows and documents edition/arrangement differences.

Keep all204 original PS3 composer/arranger/vocal/lyric field bindings. The CD's vocalist/arrangement is not automatically the game's credit: PS3 `Heart To Heart` credits Rena Uehara. 豆田将 is **Susumu Mameda**, corroborated by indexed Japanese/English credits; retain the source's **Michio Kinugasa** alias where credited rather than silently merging display names. Original music and proper-name ownership are unchanged; this reference work grants no redistribution permission.

## Paired SDAT proof and limits

`ui_archive.py` copies the immutable DAT, appends only10 recompressed TPL entries, verifies every replacement and every original byte except the authorized table rows, then encrypts a separate staged SDAT. The first `build/ui-probe/` attempt exposed upstream packer defects and remains failed evidence: write-only forging, plaintext rather than ciphertext block authentication, header hashing before its metadata CMAC, and uninitialized final padding.

`python -X utf8 tools/build_sdat_tool.py` uses existing GCC to build a **separate GPL-3.0 derivative** from exact source hashes under `work/make_npdata-pack/`; it never changes `vendor/` or the original decryptor. The repaired tool authenticates the header, complete metadata and every ciphertext block. Staging also decrypts with the original pinned executable and compares the complete DAT SHA; warning/error output fails closed. Original flags are0100003C; the packer's contiguous-CMAC output is0100000C. This format difference, actual loader acceptance, original-font GPU appearance and full-game memory fit remain runtime requirements. ELF and SDAT hashes are a single acceptance pair.

## Runtime gray sprites and internal-word gaps

Five user screenshots from18:22:02–18:23:10 and the logged `EBOOT_TH2_UI.elf` boot establish the failed `ui-readable-probe` pair. Current installed ELF/SDAT hashes match its recorded pair; no full hash was recorded at boot. Exact snapshots: `work/qa/probe-observations/ui-runtime-failure.json`. Native English help renders, but UI sprites are gray and prose has bearing-dependent gaps. Preserve that pair/form; do not request a repeat to reconfirm.

The TTY log reports `EDGE LZMA ERROR: Size of uncompressed data is -1. Maximum is65536.` All10 original first-chunk headers are `5d002000000080000000000000` (dictionary8192/output32768); failed replacements use `5d00008000ffffffffffffffff` (8-MiB/unknown size). Python ALONE decompression accepts the latter, but native28D28 passes its declared size/properties to EDGE. Its destination stride remains32768, not the logged65536 ceiling. Archive replacements now reuse the pinned EOS-free `scenario_source.pack` codec and validate properties, explicit sizes, flags, decoded lengths, total bounds and four-byte padding. TPL pixels/fonts are not changed to hide a container failure.

The UI hook at59488 incorrectly sent already-bearing-adjusted dialogue records through the raw caption clone, subtracting bearings twice. Restore that one consumer, not the word wrapper or complete-cell edge correction. Encoded producer-body598DC..59AD0 →59338 →1BCB8 →vertex replay distinguishes the old/new ink positions: adjacent `i/c` gap16→6 at unit scale. Three texts/three scales include the full66-byte opening, mixed Japanese and descenders. Producer prologue/tokenization inputs remain explicit fixture boundaries, not a full-VM claim.

Archive reconstruction through `ui_archive.stage(..., source_sdat=Path(...))` may use an original read-only backup whose full SHA matches immutable decryption provenance. The current native-only `ui_probe.py` instead copies the already authenticated, unchanged c4898391... archive from `build/ui-native-probe/assets/`, matching every graphic hash and final copy SHA. It does not rerun compression/crypto or restore installed files.


## Native UI tracking after the22:16 runtime report

The90046ed1 screenshots show working textures but tight native help/options. Keep the original font: ASCII draw1C3D0 and measure1C71C now add four design pixels before native scaling/rounding, guarded by metric pointer257038. Raw option callers choose a private widened ASCII helper by their saved return address; Japanese fixed-cell paths and accepted caption metrics remain unchanged. Music retains its measured original two-column renderer rather than squeezing complete titles/credits.

Name help is checked at actual0.5833333, not synthetic0.5; option help uses0.4 within160..624, with native60-pixel design line pitch. Four messages reflow only at whole words; no wording is removed. All18 labels clear their slider origins by13px or more. Original-font approximation: `work/qa/probe-observations/ui-tracking-native-preview.png`. The83c58c0f form remains historical: later captures show gameplay text but do not show these UI panels. New runtime acceptance belongs to `backlog-render-results-to-fill.json`.

## Selected GenInterfaceJP offline comparison — 2026-10-25

Inter was canceled by the user in favor of `fonts/GenInterfaceJP-0.8.1/`. Compared static Regular/Medium faces in both standard and Display families against original atlas pixels, matching the original H cap height rather than nominal point size. Opened `work/qa/geninterfacejp-comparison/original-vs-geninterfacejp.png`; complete English words and sampled Japanese are readable without condensation. `comparison.json` retains exact TTF/OFL hashes, metadata, cmap samples, measured lines and descender bounds.

At952px width/48px native cell, the complete H01 sample takes five lines in the original, standard Regular and standard Medium, four in Display Regular, and five in Display Medium. At464px/19.2px, the complete options-help sample takes three lines in the original/standard faces and two in Display faces. These are desktop measurements, not native fitting guarantees. Standard Regular is the initial body candidate; Medium is a UI comparison, and Display Regular merits large-text comparison. No face is inserted into a game font/TPL or paired SDAT.

All four cover the tested Japanese and g/j/p/q/y; the tested private-use codepoint's cmap presence does not establish its game-specific meaning. Matching the original cap origin requires three extra design pixels for descenders beyond the original48px cell. Any separately authorized cutover must synchronize glyph indexing/CP932 controls, fallback/private glyph semantics, bearings/advances, measure/draw/lookahead, baseline/cell/UV padding, all UI scales and accepted save/music geometry. Merely loading the TTF cannot fix native queue/reveal defects.

The bundle's `OFL.txt` states SIL OFL1.1 with author/license and Reserved Font Name conditions (including Source). Preserve them for derivatives. This earlier comparison granted no publication/rights approval; its comparison-only boundary was later superseded by the explicit Latin choice below.

## Approved GenInterfaceJP Latin cutover — 2026-10-26

The two06:46–06:47 screenshots bind62bdc049/c4898391 via one BootElf session and current read-only hashes, not hashes captured at boot. Name-help spacing/Next sprite and expanded backlog text are visible; user-reported incomplete g and bottom overflow remain failures. Evidence: `work/qa/probe-observations/glyph-backlog-viewport-runtime.json`.

The original g is CP9328287/index190, R cell1440,240–1488,288, ink10,12–36,47. Actual help/dialogue queue/UV replay samples its last ink row; row47 is blank. Source plane/remap5655 and packed nibbles are independently checked. This does not establish acceptable tail appearance or actual RSX sampling. The sampling/preview report explicitly says no new geometry fix was established. The user then selected **Use GenInterfaceJP for Latin**.

`geninterface_latin.py` replaces68 existing R-plane cells — the62 letter/digit ASCII aliases plus the six shared `()[]{}` aliases — using GenInterfaceJP Regular at47px em/baseline37, full quantized ink centered in native48px cells. Bracket envelopes share one source-derived optical axis between the face's cap and x-height centers (uniform +1px shift), stay taller than the replaced source shapes and retain the transparent sampling border; no per-bracket scaling. No new glyph-cache/lookup ABI is introduced. Other Japanese glyphs, punctuation, private symbols and every unrelated packed bit remain source-identical; full-width Latin and the six bracket aliases share the original ASCII cells and therefore change too. Generated native metric pairs at257038 match actual ink-left/width; exact source/font-derived copy guards exclude arbitrary data writes. Original files are never overwritten. Candidate-cell measurements keep the border transparent: i ink rows2–37, j/g/p/q/y 11–47 (exclusive bottom), brackets1–44 within the48px cell.

Help/options/dialogue retain b+6 advances; saved captions and pristine music clones retain b+2. The font smoke consumes the **supplied candidate TPL**, checks its hash against native metadata, samples descender tails at real caller scales, and independently derives caption prefix/ellipsis/slot bounds. GPU shader/filter/LOD and runtime appearance remain manual limits.

English UI redraws use the same mapping at `work/ui/gen-latin-reload-graphics/`:247 labels/10 TPLs/17 records,20 native-size channel previews inspected, no condensed or shortened text. Only small rotated calendar captions reach12px; main labels retain14px minimum. Gen Regular mappings use the supplied stroke without the source-font `MaxFilter(3)` dilation; original-font mappings keep it, so map/footer labels are no longer artificially emboldened. The Next button is re-lettered inside its unchanged rounded frame at17px with3px fitting padding; original Japanese ink147,59–182,77 lies inside the erase/label rectangle145,57–190,78, which is verified clean. Native source/destination crops are otherwise unchanged. Main font.tpl is an additional archive replacement, so neither c4898391 nor a660c827 can be reused. The staged bundle includes the supplied OFL notice; no release/redistribution approval is claimed.

The exact offline stage passes for `build/gen-latin-reload-probe/`:a15f4f08... ELF/be72aa94... SDAT. The actual sampled-alpha sheet for i/j/g/p/q/y and all six brackets at help0.5833333/options0.4/music0.35/dialogue1 is `work/qa/probe-observations/gen-latin-reload-runtime/gen-latin-reload-native-sampling.png`; the newer47px-em/Next/stroke UI path is previewed under `work/ui/gen-latin-reload-graphics/previews/`. All11 archive replacements and full crypto/decrypt match. The later11:28–11:29 gameplay/backlog captures belong to the failed66786e63 pair and are **not** transferred; the corrected pair's24 fields remain unobserved. Re-run actual help/dialogue/UI surfaces rather than inferring them from CPU samples.

