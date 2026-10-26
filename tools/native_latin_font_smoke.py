"""Finite encoded native replay plus actual staged Latin pixels; never GPU approval."""
from __future__ import annotations

import io
import struct

from PIL import Image, ImageDraw, ImageFont

import geninterface_latin
import native_glyph_extent_smoke as extent
import native_latin_font_patch
import native_layout_patch
import native_layout_smoke
from native_scanner_model import Scanner
from native_runtime_text_smoke import RuntimeCPU
import native_typography_smoke
import native_ui_smoke
import project
import save_preview_smoke


def require(condition, message):
    if not condition:
        raise ValueError("GenInterfaceJP Latin replay: " + message)


class LatinScanner(Scanner):
    """Reuse the runtime replay's high arenas without overlapping appended ELF."""
    CTX, TEXT, FONTS, RANGES = RuntimeCPU.CTX, RuntimeCPU.TEXT, RuntimeCPU.FONTS, RuntimeCPU.RANGES
    STRINGS, SPANS = RuntimeCPU.STRINGS, RuntimeCPU.SPANS
    SPAN_END, STACK = RuntimeCPU.SPAN_END, RuntimeCPU.STACK
    SPAN_SIZE = 0x15E0


def _branch_target(image, pc, kit, headers):
    offset = kit.vaddr_to_fileoff(pc, headers)
    word = struct.unpack_from(">I", image, offset)[0]
    require(word >> 26 == 18 and not word & 2, "expected relative native branch")
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    return pc + displacement


def _music_measure_entry(source, image, native):
    """Resolve the retained pristine measurement clone from real music calls."""
    kit = project.codec()
    source_headers = kit.read_elf_program_headers(source)
    image_headers = kit.read_elf_program_headers(image)
    for site in native["ui_tracking"]["music_original_spacing_calls"]:
        pc = int(site, 0)
        if _branch_target(source, pc, kit, source_headers) != 0x1C8B8:
            continue
        center = _branch_target(image, pc, kit, image_headers)
        for original_pc in range(0x1C8B8, 0x1CAA8, 4):
            word = struct.unpack_from(">I", source, original_pc - 0x10000)[0]
            if word >> 26 == 18 and not word & 2 and _branch_target(source, original_pc, kit, source_headers) == 0x1C5B8:
                return _branch_target(image, center + original_pc - 0x1C8B8, kit, image_headers)
    raise ValueError("No source-bound retained music measurement clone")


def top_dot_rows(cell):
    """Identify the detached top component from ink, not letter-specific rows."""
    occupied = [cell.crop((0, y, cell.width, y + 1)).getbbox() is not None
                for y in range(cell.height)]
    top = next((y for y, ink in enumerate(occupied) if ink), None)
    require(top is not None, "dot fixture has no ink")
    bottom = next((y for y in range(top, cell.height) if not occupied[y]), cell.height)
    require(any(occupied[bottom:]), "top component is not detached from a stem")
    return top, bottom


def sampled_rows(atlas, quad, cell, first, end):
    """Use the real native quad to isolate a complete source ink component."""
    isolated = Image.new("L", atlas.size)
    region = (cell[0], cell[1] + first, cell[2], cell[1] + end)
    isolated.paste(atlas.crop(region), region[:2])
    result = extent.sampled(isolated, quad, cell)
    require(any(bytes.fromhex(result["sampled_alpha_hex"])),
            "isolated ink component contributes no output pixels")
    return {"source_rows": [first, end], "sampled_ink_bbox": result["sampled_ink_bbox"],
            "sampled_alpha_sha256": result["sampled_alpha_sha256"],
            "sampled_alpha_mass": sum(bytes.fromhex(result["sampled_alpha_hex"]))}


def smoke(source, image, native, *, tpl):
    require(project.digest(source) == native_layout_patch.SOURCE_SHA256, "source identity")
    require(native_layout_patch.native_code_matches(image, image, native), "native manifest")
    require(native_latin_font_patch.manifest_matches(native.get("latin_font")), "Latin metric provenance")
    require(project.digest(tpl) == native["latin_font"]["output_tpl_sha256"], "supplied candidate TPL identity")
    _, font = geninterface_latin.replacement(source)
    original = (project.ROOT / "work/assets/fonts/_initial/font.tpl").read_bytes()
    offset = struct.unpack_from(">I", tpl, 12)[0]
    atlas = Image.frombytes("L", (1536, 1536), bytes((value & 15) * 17 for value in tpl[offset:offset + 1536 * 1536 * 2:2]))
    facts = {row["character"]: row for row in font["glyphs"]}
    require(len(font["glyphs"]) == len(facts) == 95
            and set(facts) == {chr(byte) for byte in range(32, 127)}, "all95 glyph manifest")
    require({c for c, row in facts.items() if row["replaced"]} == set(geninterface_latin.REPLACED)
            and font["replacement_count"] == 68, "exact Latin/bracket replacement set")
    face = ImageFont.truetype(io.BytesIO(geninterface_latin.FONT.read_bytes()),
                             font["raster_em"], layout_engine=ImageFont.Layout.BASIC)
    require((font["native_cell"], font["raster_em"], font["sampling_border"]) == (48, 47, 1),
            "raster em must not change the native48 cell or transparent border")
    bracket_policy = font["bracket_policy"]
    require(abs(bracket_policy["ink_axis"] - bracket_policy["text_axis"]) <= 0.5,
            "brackets do not center on the cap/x-height text axis")
    allowed = set()
    for row in font["glyphs"]:
        x, y, right, bottom = row["atlas_cell"]
        cell = atlas.crop((x, y, right, bottom))
        require(project.digest(cell.tobytes()) == row["cell_sha256"], "bitmap/report mismatch")
        metric_offset = row["metric_file_offset"]
        require(image[metric_offset:metric_offset + 2] == bytes((row["a"], row["b"])), "native pair/image mismatch")
        if row["replaced"]:
            box = cell.getbbox()
            require(box == tuple(row["ink_bounds"]) and (box[0], box[2] - box[0]) == (row["a"], row["b"]), "native a/b fails actual quantized ink")
            require(1 <= box[0] < box[2] <= 47 and 1 <= box[1] < box[3] <= 47,
                    "replacement lacks a transparent sampling border")
            # Independently rerasterize into oversized storage; prove no ink
            # was trimmed or moved per letter before/after R4 quantization.
            scratch = Image.new("L", (192, 192))
            ImageDraw.Draw(scratch).text((72, 72), row["character"], font=face, fill=255, anchor="ls")
            raw_box = scratch.getbbox()
            require(raw_box is not None, "selected source face has no ink")
            bounds = [value - 72 for value in raw_box]
            shift = bracket_policy["vertical_shift"] if row["character"] in geninterface_latin.BRACKETS else 0
            placement = [(48 - (raw_box[2] - raw_box[0])) // 2, bounds[1] + font["baseline"] + shift]
            require(bounds == row["raster_baseline_bounds"] and placement == row["raster_placement"],
                    "source raster/placement provenance mismatch")
            require(1 <= placement[0] and placement[0] + raw_box[2] - raw_box[0] <= 47
                    and 1 <= placement[1] and placement[1] + raw_box[3] - raw_box[1] <= 47,
                    "unquantized full ink lacks a transparent sampling border")
            expected = Image.new("L", (48, 48))
            expected.paste(scratch.crop(raw_box), tuple(placement))
            expected = expected.point(lambda value: ((value + 8) // 17) * 17)
            require(expected.tobytes() == cell.tobytes(), "staged pixels clip or alter complete source-face ink")
            allowed.update(offset + ((y + yy) * 1536 + x + xx) * 2 for yy in range(48) for xx in range(48))
    require(len(tpl) == len(original), "TPL size changed")
    changed = 0
    for index, (before, after) in enumerate(zip(original, tpl)):
        if before != after:
            require(index in allowed and (before & 240) == (after & 240), "unrelated packed TPL bit changed")
            changed += 1
    metric_sites = {int(row["file_offset"], 0) for row in native["latin_font"]["patches"]}
    require(all(image[index:index + 2] == source[index:index + 2]
                for index in range(geninterface_latin.METRICS_OFFSET,
                                   geninterface_latin.METRICS_OFFSET + 2 * sum(last - first + 1 for first, last in native_layout_smoke.SourceMetrics(source).ranges), 2)
                if index not in metric_sites), "non-Latin metric pair changed")
    require(metric_sites == {row["metric_file_offset"] for row in facts.values() if row["replaced"]}
            and len(metric_sites) == 68, "exact Latin/bracket metric sites")
    # Exercise every printable alias, not just the visually sensitive examples.
    all95 = bytes(range(32, 127))
    all95_cpu = native_typography_smoke.GlyphCPU(source, image, native)
    all95_records = native_ui_smoke.draw(all95_cpu, image, native, all95, scale=1.0)
    all95_quads = extent.vertices(all95_cpu, len(all95_records))
    all95_evidence = []
    for byte, record, quad in zip(all95, all95_records, all95_quads):
        fact = facts[chr(byte)]
        cell = fact["atlas_cell"]
        require(record[1] == 0 and list(record[6:8]) == cell[:2]
                and list(record[8:10]) == [cell[2] - 1, cell[3] - 1],
                "all95 native glyph record selects the wrong cell")
        sample = extent.sampled(atlas, quad, cell) if fact["ink_bounds"] else None
        if sample is not None:
            require(sample["sampled_size"] == [48, 48] and sample["uv_edges"] == cell
                    and not sample["neighbor_cell_sampled"]
                    and sample["sampled_alpha_sha256"] == fact["cell_sha256"],
                    "all95 native48 sampling differs from staged pixels")
        all95_evidence.append({"character": chr(byte), "queue": list(record),
                               "native_metric": [fact["a"], fact["b"]],
                               "cell_sha256": fact["cell_sha256"],
                               "sampled_alpha_sha256": sample["sampled_alpha_sha256"] if sample else None})
    all95_pens = [record[2] + facts[chr(byte)]["a"] for byte, record in zip(all95, all95_records)]
    require(all(all95_pens[index + 1] - all95_pens[index] == facts[chr(byte)]["advance"]
                for index, byte in enumerate(all95[:-1])),
            "all95 native record advances differ from actual glyph metrics")
    scales = (("name_help", struct.unpack_from(">f", source, 0x87FB4 - 0x10000)[0]),
              ("options", 0.4), ("music", 0.35), ("dialogue", 1.0))
    cases = []
    text = b"WMAZ09ijgpqy()[]{}"
    oracle = save_preview_smoke.SourceUI(image)
    for name, scale in scales:
        cpu = native_typography_smoke.GlyphCPU(source, image, native)
        if name == "name_help":
            records, widths = native_ui_smoke.centered_help(cpu, text, scale)
            quads = extent.vertices(cpu, len(records))
        elif name == "dialogue":
            cpu = native_ui_smoke.DialogueCPU(source, image, native)
            _, records, quads = cpu.dialogue(text, scale)
            widths = []
        else:
            records = native_ui_smoke.draw(cpu, image, native, text,
                                          site=0x8E80C if name == "options" else 0x9C098, scale=scale)
            quads = extent.vertices(cpu, len(records))
            widths = []
        pixels = []
        for byte, record, quad in zip(text, records, quads):
            fact = facts[chr(byte)]
            cell = fact["atlas_cell"]
            require(record[1] == 0 and list(record[6:8]) == cell[:2]
                    and list(record[8:10]) == [cell[2] - 1, cell[3] - 1], "draw selected wrong bitmap/cell")
            sample = extent.sampled(atlas, quad, cell)
            require(sample["uv_edges"] == cell and not sample["neighbor_cell_sampled"], "native UV crop/neighbor read")
            require(sample["sampled_ink_bbox"] is not None, "new glyph produces no visible sampled ink")
            if scale == 1.0:
                require(sample["sampled_size"] == [48, 48]
                        and sample["sampled_alpha_sha256"] == fact["cell_sha256"],
                        "native48px sampling does not reproduce every staged glyph pixel")
            if chr(byte) in "ij":
                mask = atlas.crop(tuple(cell))
                first, end = top_dot_rows(mask)
                sample["top_dot"] = sampled_rows(atlas, quad, cell, first, end)
            if chr(byte) in "gjpqy":
                # The true final descender row, not a hardcoded old-font row,
                # must contribute even at the actual small caller scales.
                last = fact["ink_bounds"][3] - 1
                sample["actual_last_ink_row"] = last
                sample["descender_last_row"] = sampled_rows(atlas, quad, cell, last, last + 1)
            pixels.append({"character": chr(byte), "queue": list(record), "sampling": sample})
        oracle.scale = scale
        entry = _music_measure_entry(source, image, native) if name == "music" else 0x1C5B8
        measurement = save_preview_smoke.measurement_probe(source, image, native, text, oracle,
                                                          extra_tracking=0 if name == "music" else 4, entry=entry)
        # Native draw subtracts the rounded bearing from each full-cell quad.
        # Consecutive logical ink origins must equal that caller's real advance.
        gap = 2 if name == "music" else 6
        pens = [record[2] + oracle.round(facts[chr(byte)]["a"]) for byte, record in zip(text, records)]
        advances = [oracle.round(facts[chr(byte)]["a"] + facts[chr(byte)]["b"] + gap)
                    - oracle.round(facts[chr(byte)]["a"]) for byte in text]
        require(all(pens[index + 1] - pens[index] == advances[index] for index in range(len(pens) - 1)),
                name + " draw advance differs from independent actual-scale metric geometry")
        require(measurement["measured"] == sum(advances), name + " measure/draw advance mismatch")
        if widths:
            require(widths == [measurement["measured"]], "centered help measure differs from actual-scale full loop")
        cases.append({"name": name, "scale": scale, "glyphs": pixels, "native_centered_widths": widths,
                      "native_measurement_at_actual_scale": measurement,
                      "executed_instruction_count": len(cpu.executed)})
    # Main scanner/lookahead consumes actual patched metric memory. Japanese,
    # punctuation, controls and raw byte progress retain their original protocol.
    metrics = native_layout_smoke.SourceMetrics(image)
    scanner_cases = []
    for name, text, options in (("latin_descender_lookahead", b"W gjpqy M gjpqy W gjpqy", {"width": 220}),
                                ("japanese_controls", "日gjpqy本\\n語\\kW".encode("cp932"), {}),
                                ("private_punctuation", bytes.fromhex("f043f047") + b" gjpqy...", {})):
        model = LatinScanner(source, text, image=image, patch_report=native, **options)
        result = model.run()
        for span in result["spans"]:
            payload = bytes.fromhex(span["text_hex"])
            require(span["design_pixel_width"] == metrics.width(payload, span["selected_font_index"]), "scanner cached width differs from patched metric sum")
            require(span["original_byte_progress"] == len(payload), "raw byte progress changed")
        scanner_cases.append({"name": name, "result": result})
    oracle = save_preview_smoke.SourceUI(image)
    caption_cpu = save_preview_smoke.PreviewCPU(source, image, native)
    caption_payload = b"Wgjpqy " * 6
    caption = caption_cpu.caption(caption_payload)
    visible = bytes.fromhex(caption["visible_caption_hex"])
    right_edge, slot_bounds = save_preview_smoke.source_right_edge(source)
    original_excerpt = caption_payload.partition(b"\0")[0][:32]
    expected_caption = save_preview_smoke.expected_display(oracle, original_excerpt, right_edge)
    require(visible == expected_caption, "save caption differs from independently bounded prefix/ellipsis")
    visible.decode("cp932", errors="strict")
    save_preview_smoke.compare_geometry(caption, oracle.geometry(visible, proportional_ascii=True), "new Latin save caption")
    quad_bounds = caption["independent_cell_quad_bounds"]
    ink_bounds = caption["independent_metric_ink_bounds"]
    require(quad_bounds is None or quad_bounds[1] <= right_edge, "save caption native quads exceed source slot bound")
    require(ink_bounds is None or ink_bounds[1] <= right_edge, "save caption ink exceeds source slot bound")
    return {"source_sha256": project.digest(source), "image_sha256": project.digest(image),
            "font": font, "packed_changed_bytes": changed, "unrelated_packed_bits_preserved": True,
            "non_latin_metrics_preserved": True, "all95": all95_evidence,
            "transparent_sampling_border": 1, "complete_source_raster_preserved": True,
            "cases": cases, "scanner_cases": scanner_cases,
            "save_caption": caption, "save_slot_bounds": slot_bounds,
            "expected_save_caption_hex": expected_caption.hex(), "runtime_accepted": False,
            "limits": ["Finite encoded PPC/FP/VMX replay, not game/emulator/GPU execution.",
                       "Texture handles, GPU reservation, dialogue live inputs and centered line tokenization are bounded synthetic fixtures.",
                       "Actual staged pixels sampled by explicit bilinear texel-edge/pixel-center CPU model; RSX shader, alpha/blend, mip/LOD and shader bias remain unverified.",
                       "Reduced-scale bilinear minification is not lossless coverage of every source texel; exact per-pixel equality is asserted only at native48px.",
                       "Native geometry and full bitmap/descender coverage do not replace user visual approval."]}
