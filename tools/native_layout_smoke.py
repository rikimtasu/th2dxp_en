"""Replay supplied encoded layout bytes; never launch a game, VM, GPU or emulator.

The public smoke(image, patch_report) has no file writes or patch-text semantics.
Callers apply native_layout_patch themselves and supply that actual ELF image.
A failed invariant raises ValueError; unsupported instructions/boundaries also
fail hard. This is software PPC/VMX/FP evidence, not native runtime acceptance.
"""
from __future__ import annotations

import struct

import project
from native_scanner_model import EXTERNAL_BOUNDARIES, Scanner, f32, fused, source_font_facts

BYTE_FIELDS = ("text_hex", "length", "newline", "wait", "page", "end",
               "selected_font_index", "scale_x", "scale_y")
MARKERS = (("F09", b"[F09] OK", 231), ("F02", b"[F02] abcdefgh", 399),
           ("F08", b"[F08] END", 264), ("F11", b"[F11] OK", 195))


def require(condition, message):
    if not condition:
        raise ValueError("Encoded native layout smoke: " + message)


class SourceMetrics:
    """Independent source-data glyph sum: no patch instructions/helper outputs."""
    def __init__(self, source):
        self.source = source
        self.facts, self.ranges = source_font_facts(source)

    def main_pair(self, byte):
        code = struct.unpack_from(">H", self.source, 0x2514B0 + 2 * (byte - 0x20))[0]
        index, found = 0, False
        for first, last in self.ranges:
            if first <= code <= last:
                index += code - first
                found = True
                break
            index += last - first + 1
        if not found:
            index = 0
        return tuple(self.source[0x247038 + 2 * index:0x24703A + 2 * index])

    def width(self, text, font=0, *, fallback_width=None, defaults=None):
        total, offset = 0, 0
        while offset < len(text):
            byte = text[offset]
            if not byte:
                offset += 1
                continue
            if 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC:
                require(offset + 1 < len(text), "independent glyph sum ended in CP932 lead byte")
                total += 48
                offset += 2
            else:
                require(0x20 <= byte <= 0x7E, f"glyph-sum fixture has unsupported byte {byte:#x}")
                if font == 0:
                    total += self.main_pair(byte)[1] + 6
                else:
                    value = self.facts[font]["fields"][0x8C]
                    value = (defaults or {}).get(font, {}).get(0x8C, value)
                    total += (value & 255 if fallback_width is None else fallback_width) + 6
                offset += 1
        return float(total)


def byte_records(result):
    return [{key: span[key] for key in BYTE_FIELDS} for span in result["spans"]]


def byte_attributes(result):
    return [(byte, span["selected_font_index"], span["scale_x"], span["scale_y"])
            for span in result["spans"] for byte in bytes.fromhex(span["text_hex"])]


def control_records(result):
    return [(span["wait"], span["page"], span["end"])
            for span in result["spans"] if any(span[key] for key in ("wait", "page", "end"))]


def serial_options(options):
    return {key: ({str(offset): value.hex() for offset, value in item.items()}
                  if key == "substitutions" else item)
            for key, item in options.items()}


def compare_case(source, image, patch_report, metrics, name, text, options=None,
                 *, wrapping=False, same_geometry=False, glyph_sum=True,
                 restored_terminal_text=None):
    options = options or {}
    original_model = Scanner(source, text, **options)
    encoded_model = Scanner(source, text, image=image, patch_report=patch_report, **options)
    original, encoded = original_model.run(), encoded_model.run()
    same_records = byte_records(original) == byte_records(encoded)
    if restored_terminal_text is not None:
        require(not original["spans"], f"{name}: baseline no longer reproduces terminal span loss")
        expected = [{"text_hex": restored_terminal_text.hex(), "length": len(restored_terminal_text),
                     "newline": 0, "wait": 0, "page": 0, "end": 0,
                     "selected_font_index": 0, "scale_x": 1.0, "scale_y": 1.0}]
        require(byte_records(encoded) == expected,
                f"{name}: literal terminal span was not restored intact")
    elif not wrapping:
        require(same_records, f"{name}: raw span bytes/flags/font/scale changed")
    else:
        require(byte_attributes(original) == byte_attributes(encoded),
                f"{name}: automatic wrapping changed bytes or captured font/scale")
        require(control_records(original) == control_records(encoded),
                f"{name}: automatic wrapping changed explicit wait/page/end flags")
    if same_geometry:
        require(original["final_cursor"] == encoded["final_cursor"],
                f"{name}: Japanese/control-only source cursor changed: "
                f"{original['final_cursor']} -> {encoded['final_cursor']}")
        require([(s["x"], s["y"]) for s in original["spans"]] ==
                [(s["x"], s["y"]) for s in encoded["spans"]],
                f"{name}: Japanese/control-only span origins changed")
    for span in encoded["spans"]:
        source_strlen = len(bytes.fromhex(span["text_hex"]).partition(b"\0")[0])
        require(span["original_byte_progress"] == float(source_strlen),
                f"{name}: original +14BC raw byte progress changed")
        if glyph_sum:
            expected = metrics.width(bytes.fromhex(span["text_hex"]), span["selected_font_index"],
                                     fallback_width=options.get("fallback_width") if options.get("fallback_initialized") else None,
                                     defaults=options.get("auxiliary_defaults"))
            require(span["design_pixel_width"] == expected,
                    f"{name}: cached design width {span['design_pixel_width']} != independent glyph sum {expected}")
            span["independent_source_glyph_sum"] = expected
        span["physical_advance"] = fused(fused(span["design_pixel_width"], span["scale_x"], 0),
                                         encoded_model.scalar(encoded_model.CTX + 0x84), 0)
    return {"name": name, "input_hex": text.hex(), "options": serial_options(options),
            "automatic_wrap_may_change_boundaries": wrapping,
            "same_native_span_records_except_geometry": same_records,
            "span_bytes_and_explicit_controls_verified": True,
            "known_terminal_span_restored": restored_terminal_text is not None,
            "source_geometry_required_unchanged": same_geometry,
            "original": original, "encoded": encoded}, encoded_model


def metric_reference(source, image):
    """Original instructions with the candidate's main-font metric data only."""
    _, ranges = source_font_facts(source)
    begin = 0x247038
    end = begin + 2 * sum(last - first + 1 for first, last in ranges)
    reference = bytearray(source)
    reference[begin:end] = image[begin:end]
    return bytes(reference)


def metric_probe(source, image, patch_report, *, font, initialized, cache_width,
                 defaults=None, text=b"A"):
    """Compare actual encoded helper against original 1D538's returned pair."""
    options = {"selected_font": font, "fallback_initialized": initialized,
               "fallback_width": cache_width, "auxiliary_defaults": defaults}
    original = Scanner(source, text, image=metric_reference(source, image), **options)
    encoded = Scanner(source, text, image=image, patch_report=patch_report, **options)
    stop = 0x6F17C
    original.r[3] = original.get(original.FONTS + font * 4, 4)
    original.r[4], original.pc, original.lr = original.TEXT, 0x1D538, stop
    original.execute_until(stop)
    pair = list(original.read(original.r[3], 2))
    metric = next(block for block in patch_report["injected_blocks"]
                  if block["name"] == "selected_font_read_only_metric")
    encoded.r[27], encoded.r[28] = encoded.CTX, encoded.TEXT
    encoded.pc, encoded.lr = int(metric["va"], 0), stop
    encoded.r[3:13] = [0xA01000 + i * 0x100 for i in range(10)]
    encoded.cr = [bool(i & 1) for i in range(32)]
    saved_gprs, saved_cr = encoded.r[3:13], encoded.cr[:]
    encoded.f[0], encoded.f[1] = -17.25, 123.5
    encoded.execute_until(stop)
    actual = encoded.vu(28)[0]
    expected = pair[1] + 6
    reserve = max(48, pair[1] + 3)
    if font:
        source_font = original.get(original.FONTS + font * 4, 4)
        reserve = max(reserve, original.get(source_font + 0x88, 4) + 3 - pair[0])
    require(actual == expected,
            f"metric font{font} initialized={initialized}: {actual} != source1D538 {expected}")
    require(encoded.scalar(encoded.STACK + 0x4CC) == float(reserve),
            f"metric font{font}: candidate reservation differs from independent source bearing bound")
    require(encoded.r[3:13] == saved_gprs and encoded.cr == saved_cr and
            encoded.f[0:2] == [-17.25, 123.5] and encoded.r[1] == encoded.STACK and encoded.lr == stop,
            "encoded metric helper clobbered live GPR/CR/FPR/SP/LR state")
    require(encoded.get(0x657EB0, 1) == int(initialized) and
            encoded.get(0x26157D, 1) == cache_width,
            "read-only metric helper changed source fallback globals")
    return {"font": font, "initialized": initialized, "initial_cached_width": cache_width,
            "auxiliary_defaults": defaults, "source_returned_pair": pair,
            "source_fallback_width_after": original.get(0x26157D, 1),
            "source_fallback_initialized_after": original.get(0x657EB0, 1),
            "encoded_design_pixel_width": actual, "expected_design_pixel_width": expected,
            "candidate_reservation": reserve, "steps": encoded.steps,
            "live_registers_preserved": True, "source_fallback_globals_unchanged": True}


def deferred_fallback_probe(source, image, patch_report):
    """Expose unsupported differently-defaulted first-use object configurations.

    All four actual source1D504 calls supply+8C46. These deliberately different
    values are negative configurations, not evidence of a native-game bug.
    The source1D538 side effects and read-only predictions remain observable.
    """
    defaults = {1: {0x8C: 17}, 2: {0x8C: 29}, 3: {0x8C: 61}}
    metric = next(block for block in patch_report["injected_blocks"]
                  if block["name"] == "selected_font_read_only_metric")
    results = []
    for order in ((1, 2, 3), (0, 2, 1)):
        source_model = Scanner(source, b"A", image=metric_reference(source, image), auxiliary_defaults=defaults)
        encoded = Scanner(source, b"A", image=image, patch_report=patch_report,
                          auxiliary_defaults=defaults)
        predicted, drawing = [], []
        for font in order:
            encoded.put(encoded.CTX + 0xDC, font, 4)
            encoded.r[27], encoded.r[28] = encoded.CTX, encoded.TEXT
            encoded.pc, encoded.lr = int(metric["va"], 0), 0x6F17C
            encoded.execute_until(0x6F17C)
            predicted.append(encoded.vu(28)[0])
        for font in order:
            source_model.r[3] = source_model.get(source_model.FONTS + font * 4, 4)
            source_model.r[4] = source_model.TEXT
            source_model.pc, source_model.lr = 0x1D538, 0x6F17C
            source_model.execute_until(0x6F17C)
            drawing.append(source_model.get(source_model.r[3] + 1, 1) + 6)
        results.append({"font_order": list(order), "auxiliary_defaults": defaults,
                        "encoded_read_only_measurements_before_drawing": predicted,
                        "source_1d538_drawing_order_widths": drawing,
                        "equal": predicted == drawing,
                        "supported_source_constructor_configuration": False,
                        "scope": "unsupported negative configuration: differing defaults, unlike the four source1D504 calls"})
    return results


def flower_probes(source, image, patch_report):
    """Execute actual patched branch sites through their source continuation."""
    cases = []
    abc_width = SourceMetrics(image).width(b"ABC")
    for site, stop, name in ((0x70534, 0x7054C, "wait"),
                             (0x70630, 0x7064C, "final"),
                             (0x706CC, 0x706E4, "completed"),
                             (0x6F988, 0x6F9BC, "reposition_all")):
        for captured_scale, position_scale, current_scale in ((1.5, 0.8, 0.375), (0.625, 1.25, 2.75)):
            model = Scanner(source, b"ABC", image=image, patch_report=patch_report,
                            x=17.25, scale=captured_scale, position_scale=position_scale)
            result = model.run()
            require(len(result["spans"]) == 1, "flower ABC fixture did not yield one span")
            span = int(result["spans"][0]["address"], 0)
            require(model.scalar(span + 0x14CC) == abc_width, "flower fixture cached width differs from ABC metric sum")
            captured_s = model.scalar(span + 0x84)
            t = model.scalar(model.CTX + 0x84)
            origin = model.scalar(span + 0x64)
            model.setfloat(model.CTX + 0xA4, current_scale)
            model.setfloat(model.CTX + 0x520, 91.25)
            model.put(model.CTX + 0x530, span, 4)
            model.r[30], model.r[31], model.r[3] = span, model.CTX, span
            model.f[4] = origin
            model.f[1], model.f[7], model.f[8], model.f[9], model.f[30], model.f[31] = 3.0, 48.0, current_scale, t, 0.5, 0.5
            model.pc = site
            previous_steps = model.steps
            model.execute_until(stop)
            # Deliberately independent of the encoded helper's live FP outputs.
            physical = f32(f32(abc_width * captured_s) * t)
            base = 91.25 if name == "wait" else origin
            expected = f32(base + physical)
            c520 = model.scalar(model.CTX + 0x520)
            endpoint = model.f[4] if name == "reposition_all" else c520
            require(endpoint == expected,
                    f"flower {name} S={captured_s} T={t}: {endpoint} != independent {expected}")
            if name == "reposition_all":
                require(c520 == 91.25, "reposition source block unexpectedly wrote C520")
            require(model.scalar(span + 0x14BC) == 3.0 and model.scalar(span + 0x14CC) == abc_width,
                    "flower block modified raw progress or cached design width")
            cases.append({"block": name, "branch_site": hex(site), "continuation": hex(stop),
                          "captured_span_scale": captured_s, "current_context_scale": current_scale,
                          "position_scale": t, "design_pixel_width": abc_width,
                          "span_origin": origin, "initial_C520": 91.25, "observed_C520": c520,
                          "endpoint": endpoint, "independent_endpoint": expected,
                          "endpoint_storage": "F4 source drawing-call argument; source block never stores C520"
                          if name == "reposition_all" else "C520 actual encoded stfs",
                          "steps": model.steps - previous_steps})
    return cases


def smoke(image: bytes, patch_report: dict) -> dict:
    """Replay original terminal-fixed vs supplied encoded diagnostic in RAM."""
    source = project.source_bytes()
    require(project.digest(source) == patch_report["source_sha256"], "source/report identity mismatch")
    require(project.digest(image) == patch_report["output_sha256"], "image/report identity mismatch")
    metrics = SourceMetrics(image)
    require(SourceMetrics(source).width(b"ABC") == 119, "independent source ABC glyph sum changed")
    require([fact["fields"][0x8C] for fact in metrics.facts] == [46] * 4,
            "source constructor first-use default constraint changed")
    samples = [
        ("ascii", b"ABC", {}, False, False, True),
        ("literal_right_angle_terminal", b"AB>", {}, False, False, True),
        ("literal_right_angle_internal", b"AB>CD", {}, False, False, True),
        ("literal_star_right_angle_terminal", b"AB*>", {}, False, False, False),
        ("literal_star_right_angle_internal", b"AB*>CD", {}, False, False, False),
        ("newline", b"AB\\nCD", {}, False, False, True),
        ("wait", b"AB\\kCD", {}, False, False, True),
        ("page", b"AB\\p00ffCD", {"existing_span": True}, False, False, True),
        ("end", b"AB\\eCD", {}, False, False, True),
        ("font_scale", b"AB<F 40>CD<F 20>EF", {}, False, False, True),
        ("restore", b"AB<R 12>CD<R 0>EF", {}, False, False, True),
        ("font_selected", b"AB<G 1>CD<G 2>EF<G 3>GH<G 0>IJ", {}, False, False, True),
        ("other_tags", b"AB<S 2><C 1><W 3><A 4>CD", {}, False, False, True),
        ("substitution", b"AB*nfCD", {"substitutions": {0: b"XYZ"}}, False, False, True),
        ("substitution_suffix", b"AB*nf2CD", {"substitutions": {0: b"ABCDEFGH"}}, False, False, True),
        ("substitution_kana", b"AB*nfkCD", {"substitutions": {0x10: b"XYZ"}}, False, False, True),
        ("substitution_last", b"AB*nlCD", {"substitutions": {0x20: b"XYZ"}}, False, False, True),
        ("substitution_nickname", b"AB*nnCD", {"substitutions": {0x40: b"XYZ"}}, False, False, True),
        ("unknown_asterisk", b"AB*qqCD", {}, False, False, False),
        ("unknown_escape", b"AB\\zCD", {}, False, False, False),
        ("japanese", "あいうえお".encode("cp932"), {"width": 96}, True, True, True),
        ("japanese_control", "あい\\nうえ\\kお".encode("cp932"), {"width": 192}, True, True, True),
        ("japanese_scale", "あい<F 40>うえ<F 20>お".encode("cp932"), {"width": 192}, True, True, True),
        ("japanese_restore", "あい<R 12>うえ<R 0>お".encode("cp932"), {"width": 192}, True, True, True),
        ("japanese_kinsoku", "あ、いうえ".encode("cp932"), {"width": 96}, True, True, True),
        ("japanese_nonunit_T", "あいうえお".encode("cp932"), {"width": 192, "position_scale": 0.8}, True, True, True),
        ("japanese_tildes", "〜〜あ〜".encode("cp932"), {}, False, True, True),
        ("mixed", "ABあCDいうEF".encode("cp932"), {"width": 192}, True, False, True),
        ("underscores", b"AB__CD__EF__GH", {"width": 192}, True, False, True),
        ("ascii_nonunit_T", b"ABCDEFGH", {"width": 192, "position_scale": 0.8}, True, False, True),
        ("empty_newline", b"\\nAB", {}, False, False, True),
        ("edge_tag", b"<F 20>AB", {"x": 72, "width": 96}, True, False, True),
        ("scale_automatic_wrap", b"AB<F 40>CDEFG<F 20>HI", {"width": 192}, True, False, True),
        ("english_multiline_height_fixture", b"AB CD EF GH IJ KL MN OP QR ST UV WX YZ " * 8,
         {"width": 192, "height": 144}, True, False, True),
    ]
    # Exact original marker text, rather than invented text fitted to widths.
    for marker, text, _ in MARKERS:
        samples.append(("marker_" + marker, text, {}, False, False, True))
    for font in (1, 2, 3):
        for initialized in (False, True):
            options = {"selected_font": font, "fallback_initialized": initialized,
                       "fallback_width": 37}
            samples.append((f"aux_font{font}_cache_{initialized}", b"ABC", options, False, False, True))
    cases = []
    executed = set()
    for name, text, options, wrapping, same_geometry, glyph_sum in samples:
        case, model = compare_case(source, image, patch_report, metrics, name, text, options,
                                   wrapping=wrapping, same_geometry=same_geometry, glyph_sum=glyph_sum,
                                   restored_terminal_text=text if name == "literal_right_angle_terminal" else None)
        if name in ("ascii", "literal_right_angle_terminal") or name.startswith("marker_"):
            expected = metrics.width(text)
            require(case["encoded"]["final_cursor"] == [expected, 0.0],
                    f"{name}: final logical cursor differs from independent glyph sum {expected}")
        if name in ("font_scale", "restore", "font_selected"):
            cursor = 0.0
            for span in case["encoded"]["spans"]:
                require(span["x"] == cursor and span["y"] == 0.0,
                        f"{name}: span origin differs from independent accumulated design advances")
                cursor = fused(span["design_pixel_width"], span["scale_x"], cursor)
            require(case["encoded"]["final_cursor"] == [cursor, 0.0],
                    f"{name}: final logical cursor differs from independent accumulated design advances")
        cases.append(case)
        executed.update(model.executed)
    metrics_report = []
    for font in range(4):
        for initialized in (False, True):
            metrics_report.append(metric_probe(source, image, patch_report, font=font,
                                               initialized=initialized, cache_width=37))
    varied = {1: {0x88: 41, 0x8C: 17}, 2: {0x88: 59, 0x8C: 29}, 3: {0x88: 31, 0x8C: 61}}
    for font in (1, 2, 3):
        for initialized in (False, True):
            metrics_report.append(metric_probe(source, image, patch_report, font=font,
                                               initialized=initialized, cache_width=23, defaults=varied))
    risks = deferred_fallback_probe(source, image, patch_report)
    flowers = flower_probes(source, image, patch_report)
    historical = {"marker_" + marker: width for marker, _, width in MARKERS}
    markers = [{"name": case["name"], "source_glyph_sum": metrics.width(bytes.fromhex(case["input_hex"])),
                "historical_expected_width": historical[case["name"]],
                "historical_number_matches_independent_source": historical[case["name"]] == metrics.width(bytes.fromhex(case["input_hex"])),
                "encoded_cached_widths": [span["design_pixel_width"] for span in case["encoded"]["spans"]]}
               for case in cases if case["name"].startswith("marker_")]
    return {"kind": "actual encoded PPC instruction software replay",
            "source_sha256": project.digest(source), "image_sha256": project.digest(image),
            "native_layout_patch_encoded": True, "native_fp_executed": False,
            "vm_gpu_executed": False, "elf_written": False, "runtime_accepted": False,
            "production_cutover": False, "case_count": len(cases), "cases": cases,
            "source_constructor_font_facts": metrics.facts,
            "source_constructor_fallback_width_constraint": [fact["fields"][0x8C] for fact in metrics.facts],
            "supported_fixture_invariants_passed": True,
            "independent_ABC_glyph_sum": metrics.width(b"ABC"), "marker_widths": markers,
            "metric_comparisons": metrics_report, "flower_blocks": flowers,
            "deferred_first_use_fallback_comparisons": risks,
            "readonly_prediction_matches_adversarial_deferred_drawing": all(risk["equal"] for risk in risks),
            "encoded_scanner_instruction_addresses_exercised": [hex(pc) for pc in sorted(executed)],
            "external_boundaries": EXTERNAL_BOUNDARIES,
            "synthetic_boundaries": {
                "draw_context": "bounded initialized fields, synthetic height168 by default (long-English fixture144), user option zero; not live constructor-proved dimensions",
                "fonts": "four synthetic objects; source main ranges/table and source1D504 argument fields; auxiliary null tables, reused main range list",
                "spans": "nonoverlapping14D0 objects; constructor captures source-layout fields and raw byte progress; encoded stvewx alone sets14CC",
                "allocator": "bounded synthetic span arena; no source allocator execution",
                "flower_entry_state": "captured span versus deliberately changed context S; actual branch and encoded instructions, not full dispatch/guards/drawing",
                "reposition_endpoint": "F4 source drawing-call argument, not C520; three other endpoint blocks read encoded C520 stores"},
            "limitations": [
                "Software PPC/VMX/FP model only: no native FP, GPU, renderer, emulator or VM runtime proof.",
                "Synthetic constructor does not execute source allocation, game options, renderer or draw calls.",
                "Finite valid inputs and explicitly initialized font objects only; not malformed-input or live-font-state proof.",
                "Differing-default first-use configurations are unsupported negative experiments, not a demonstrated native-game bug: all four source1D504 calls pass46.",
                "Automatic wrapping may change span segmentation and newline placement, but byte/font/scale attributes and explicit wait/page/end records must match.",
                "Explicit synthetic height does not prove complete engine automatic-height/page dispatch; the report retains all scanner span flags/y positions, while construction/drawing remain boundaries.",
                "Unknown star/escape cases assert source byte/control preservation, not an invented glyph-sum interpretation of native syntax."]}
