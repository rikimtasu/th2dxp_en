# Fonts and graphics text

## Compound punctuation, map rasters and music bounds — 2026-11-02

The user approved the three targeted rendering corrections. `tools/native_compound_punct_patch.py` overlays exactly U+E000/F040 (`!?`), U+E001/F041 (`!!`) and U+E00E/F04E (`??`) after the established Latin/punctuation/Japanese layers. Complete GenInterfaceJP masks share Latin baseline37, component ink-width+6 spacing and one final native4-bit quantization; the compound keeps a transparent border without scaling/clipping. Main native metrics match actual quantized ink. Codepoints, lookups, controls and every other private/unselected packed bit remain unchanged. The base generators' preservation proofs are layer-relative, not a claim that these three approved cells remain original in the final font.

Map labels now use `ui_graphics.MapFace`, reusing the existing whole-word layout but drawing from the approved face directly at the final UI em with8-bit coverage and same-face punctuation. No native4-bit-mask intermediate, dilation or downsampling. Fresh retained inputs are under `work/ui/ui-rendering-fixes-20261102/`; `ui_probe.graphics_inputs()` rejects old raster provenance or mismatched wording/geometry/hashes. All135 labels fit their source170×52 cells; all five source record headers/other payloads and the five non-map UI TPLs remain byte-identical. Native-size atlas/long-label previews were inspected. This does not prove native GPU filtering or map reveal appearance.

The music correction migrates the row panel, selected-row extent and scrollbar together; titles, role bindings, font sizes and vertical spacing are retained. The encoded replay executes all51 complete records plus settled/fractional scroll and selected/locked cases, checking real title/theme/artist calls and complete role rectangles against the actual panel and scrollbar. `stage_english_build.py` freshly assembles current native UI code rather than copying stale geometry from the retained template. A genuine small UI image is replayed; code/data/main-metric correspondence binds it to the final scenario-growth image without truncation or bypassing the fixture's address-overlap guard. GPU submissions/tessellation and input-driven transitions remain manual.

Actual compound glyphs/retained controls and packed-map proofs are under `work/qa/ui-rendering-fixes-20261102/`. New diagnostic staging targets `build/ui-rendering-fixes-20261102/`; published v0.4 and all earlier evidence remain unchanged. No rendering, save or production acceptance transfers.

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

**Original font inputs remain immutable; the user later approved a staged GenInterfaceJP Latin cutover.** The initial VWF correction retained every glyph. After source sampling failed to establish an additional g geometry defect, the user explicitly selected GenInterfaceJP for Latin letters/digits. That initial authorization excluded Japanese/punctuation/private glyphs; later punctuation work and the explicit Japanese request below supersede those respective exclusions. Installed-file edits and private-icon replacement remain unauthorized. Preserve CP932 semantics; the incompatible PC font patch remains irrelevant.

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

## Punctuation cells — 2026-10-27

`tools/native_latin_punct_patch.py` extends the same mapping to the punctuation the shipped English actually draws. The 62 letters/digits and six brackets were only part of the story: `. , ' " ? ! : ; - ~ * < > % & + / = # @ ^ _ \`` still came out of the original aliases, which are full-width cells with an em-wide advance, so an English sentence read as narrow Latin words with wide Japanese marks.

- **23 extra cells** are redrawn from GenInterfaceJP Regular at the same 47 px em/baseline 37 as the letters, each with a transparent 1 px sampling border and the reviewed metric rule (**advance = quantized ink width + 6**, so `b = advance - 6`). The module is chained *on top of* `geninterface_latin.replacement()` rather than widening its `REPLACED` tuple, so the 68 reviewed cells, their pixels and the pinned `output_tpl_sha256` keep identifying exactly the same atlas.
- **Three exclusions are measured, not stylistic.** `$` ink is 45 px tall and starts 3 px above the native cell at this baseline. `|` ink is 57 px, taller than the 48 px cell. `\` shares its cell with the full-width yen sign `￥`, which the shipped text uses 8 times, while ASCII `\` appears 6,411 times and every one of them introduces an inline control (`\k…`, `\n…`) — a redrawn cell would corrupt the yen sign to buy nothing.
- **Full-width counterparts change too.** A CP932 alias cell carries both the ASCII character and its full-width form, so `！ ？ ’ ” ～ ＞ ＝ ＋ － ／ ＊ ％ ＆ ＃ ＠ ： ； ， ．` become Latin-narrow as well. That is the same mechanism that already makes `Ａ`-class aliases carry the new letters; the manifest now records `shared_fullwidth_character` per cell so the side effect is explicit. Measured shipped usage of the ASCII forms: `.` 87,604, `,` 49,176, `'` 20,205, `-` 11,239, `?` 5,331, `*` 2,950, `!` 2,126, `"` 1,903, `<`/`>` 1,104 each, `~` 440, `:` 219, `;` 88, with `#`, `$`, `@`, `|` absent from the English text.
- `verify()` compares the 23 cells byte-by-byte first and only then the whole-TPL digest, so a single moved pixel names the character instead of reporting "TPL differs"; a broken metric pair or a re-based manifest still fails closed. 16 synthetic tests.

The paired `data.sdat` must be repacked whenever these pixels change: `build/english-v0.1/assets/data.sdat` (`bbb932bf…`) carries font TPL `fa17b5ad…`, and neither `c4898391…` nor `a660c827…` nor the `be72aa94…` diagnostic archive may be paired with this ELF.

## Approved Japanese extension — 2026-10-30

The user requested Japanese replacement with the same **GenInterfaceJP Regular** face. `tools/native_japanese_font_patch.py` chains onto the retained Latin/punctuation atlas and generates **7,261 replacement cells**: main font6,915; font1=134; font2=22; font3=190. Every selected kana/CJK/Japanese-punctuation character has actual Unicode cmap coverage, not a .notdef fallback. Existing Latin/punctuation cells, private icons, other symbols, native indices and every unselected packed bit are preserved. Original assets remain immutable.

- Rasterization keeps47px em but uses one Japanese origin **X=1, baseline40**, not Latin baseline37, which clips dakuten and many kanji. Full raster bounds must fit inside the48px cell with a1px transparent border; no per-character scaling/cropping/placement adjustment. The same placement is used in all four fonts. Main-font bearing/ink-width pairs match the new quantized ink at all6,915 selected sites.
- Native banks follow **R,G,B,A**: packed `(byte, shift)` = `(0,0), (1,4), (1,0), (0,4)`, with eight banks in the main atlas. TPL records are20 bytes and store **height before width**, important for the rectangular auxiliary atlases. The native auxiliary constructor receives its real source table-byte length, not zero.
- Preserve caller-specific advances, not a global metric substitution: scanner/dialogue Japanese use48 design units; save captions and raw options keep fallback46 and existing special-cell behavior. Proportional name help uses the new Japanese ink width with native+2 spacing; its extra+4 Latin tracking applies only to ASCII. Music keeps its+2 protocol. Thus proportional Japanese UI widths can change while fixed-cell geometry remains unchanged.

Private outputs: `work/ui/geninterface-japanese-20261030/` contains four generated TPLs, `font-manifest.json`, the OFL notice, `offline-proof.json`, `geometry-proof.json` and the inspected `native-mixed-preview.png`. Encoded replay passed **16 bank-selection cases**, four mixed-text sampled consumers (help/options/music/dialogue), **three bounded caption comparisons**, **nine unchanged scanner/wrap/control/progress comparisons** (including all four font selections), and three caller-specific mixed UI advance comparisons. Identical NaNs in inactive vector trace lanes required serialized trace comparison; no game code was altered to make that comparison pass. The font-only replay input is retained v0.3 (`cc9708fc…`), producing in-memory candidate `44a0b0bb…`; it does not include the69 later translation corrections.

Full live-script assembly also passes `python -X utf8 tools/stage_english_build.py --verify-only --japanese-font --dialogue-scale 0.75`:183,446 text rows /1,884 scenario payloads checked, candidate ELF **`0213e0367a456a775376b3a3cdf5b1f9e9dd307d54072ed2224e36c78929577c`** (10,758,904 bytes), main font TPL **`178d36458f1b23a252c788a7cc38255a47f89659550010d5cc38387dbbf61331`**. This command writes no build files. All267 synthetic tests and `git diff --check` pass.

**The initial missing-original blocker now has separately authorized variant support.** The recorded original backup is absent; its SDAT identity remains **`4509a4e93e7e630e09971326d3e5f78e4c48a05e588e8c1ab9f0a88b174a9e3a`**. The supplied QA backup instead hashes to **`389bf3cabdb9cdf3044b5be1dd4789c43be351f24bfa70a22e0d2e2fca5aa0f1`**, paired only with DAT **`324d93e49a620c3b2d0dab8451aba0106ce2b36762d4ecd42287d5ca8dc230c7`**. `ui_archive.py` recognizes this additional exact pair without editing the earlier provenance. Source recovery happens under the new build directory. Comparison covers all3,516 entries:3,483 identical,33 differing `n/8000.bin`–`n/8200.bin` entries retained from the variant. All UI/font source entries match the original assets. Unknown hashes, mismatched decrypted DATs, unexpected entry differences and replacement of variant-specific entries fail closed.

Source recovery permits only the two exact known legacy header/metadata warnings and **does not authenticate the source**; the completed recovery reported only the metadata warning. The generated output passed strict warning-free authentication and complete decrypt/DAT equality. The earlier archives cannot carry the changed Japanese pixels. Completed staging command (output is retained; use a different new directory for future changed artifacts):

```console
python -X utf8 tools/stage_english_build.py --output build/english-geninterface-jp-20261030 --japanese-font --dialogue-scale 0.75 --source-sdat "work/installer-fresh-qa/game/PS3_GAME/USRDIR/.th2dxp-backup/data.sdat"
```

Completed pair:

| File under `build/english-geninterface-jp-20261030/` | Bytes | SHA-256 |
| --- | ---: | --- |
| `EBOOT.elf` / identical `EBOOT_EN.elf` | 10,758,904 | `0213e0367a456a775376b3a3cdf5b1f9e9dd307d54072ed2224e36c78929577c` |
| `assets/data.sdat` | 2,202,589,216 | `d387124f55517ba8873c430c5f6bed081ec62d8ed9b650e3bb542d7e3260b352` |

All14 replacements re-extract exactly;3,502 other table rows and all source bytes outside the14 authorized rows remain intact. Complete decrypt matches the2,200,440,056-byte DAT (`ecde4fbf…`); header/metadata/every-block authentication passes. Both ELF copies and SDAT were independently hashed after staging; the OFL notice is present. This pair includes the69 targeted translation corrections and75% normal-dialogue scale. All275 unit tests pass.

On2026-10-31 the user reported testing finished and selected this pair for the **planned v0.3** release. `work/qa/geninterface-japanese-20261030-results-to-fill.json` retains24 unfilled checks because no individual case outcomes/version/scenes accompanied that general report. Do not request repeats merely to reconfirm the reported testing. See `docs/release-v0.3.md` for local patch-only packaging. No comprehensive RSX/live-game acceptance, save compatibility, production enablement or public release is inferred; retained pairs and forms remain unchanged.

## Auxiliary-font Latin aliases — 2026-10-31

The three small atlases are not only Japanese. `G1` selects `font1.tpl` for story/letter text, `G2` `font2.tpl` (name card, exchange diary) and `G3` `font3.tpl` (food labels, letter body). Each carries its own ordered CP932 range list; ASCII resolves through the global alias table to a full-width code, and a code missing from that font's list returns glyph index 0 — a blank cell. English inside any `G2`/`G3` span therefore rendered as nothing, the same failure that blanked the `font1` intro.

`tools/native_auxiliary_latin_patch.py` now handles all three fonts through one `FONTS` spec. For each it appends the missing alias cells after every native cell, rewrites the font's lookup-allocation word (`0x24702C`/`0x247030`/`0x247034`), and installs a 108-byte helper at that constructor's return (`0x118D4`/`0x11968`/`0x119FC`) which copies the appended range pairs after the native ones and points `0x7c(3)` at owned ink metrics. Caller GPRs, CR and CTR are preserved, and every unselected packed bit, native index and advance is unchanged.

| Font | Native cells | Bank capacity | Appended aliases | Ranges | Lookup bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| `font1.tpl` | 137 | 256 | 94 | 18 | 1,248 |
| `font2.tpl` | 27 | 128 | 93 | 16 | 352 |
| `font3.tpl` | 203 | 256 | 46 | 13 | 1,736 |

Each lookup allocation is enlarged from the native range-table byte count before the hook appends its ranges. The `0x100` argument at `0x1D43C` does not establish lookup-allocation capacity; the texture-bank capacity is checked separately. Fonts 1 and 2 hold the complete 93-alias set, but font3 cannot (203 + 93 > 256), so `stage_english_build.py` derives the exact alias codes its `G3` spans draw from the scripts being built and passes them as a subset — complete for that build by construction, and an overflow raises instead of blanking. Offline replay of every `G2`/`G3` run in the current scripts (`work/qa/ikuno-text-20261031/scan_spans.py`) resolves **22 runs with 0 blank characters**; this is model replay, not RSX output.

## English default player name — 2026-10-27

The game's default protagonist name lived in one 40-byte read-only window (`0xF73D8..0xF7400`, VA `0x1073D8`): `貴明` / `たかあき` (given name and reading), `河野` / `こうの` (family name and reading), `たか` / `タカ` (short and katakana nickname). `tools/native_default_name_patch.py` repacks those six null-terminated strings in place as `Takaaki`/`Takaaki`/`Kouno`/`Kouno`/`Taka`/`Taka` — 38 of the 40 bytes — and repoints the **32** inventoried load sites by rewriting only the low 16-bit immediate of their `lis rX,0x10` + `addic/addi rY,rX,0x73xx` pair. The 12 `ori rZ,rY,0` inventory entries copy an already-loaded register and need no change. 63 bytes differ in the whole executable.

The initialisation path copies with fixed `strncpy` lengths (13 bytes for each of the five 16-byte fields, 32 for the nickname), and those lengths are read back out of the executable's own `li r5,n` instructions, so a future longer name is rejected rather than silently truncated. A save that still holds the Japanese default simply compares unequal at `0x8631C`/`0x8AB58` and reads as a custom name — the same path a player-typed name takes, with no save migration and no new gameplay. `verify()` re-reads the window, both kana/kanji slots and every repointed instruction, and the completeness scan refuses to run if any materialised window address is missing from the inventory or any inventory immediate is not a real `addic/addi`. 17 synthetic tests.
