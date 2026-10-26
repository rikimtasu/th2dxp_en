"""Relocate reviewed UI constants without changing fonts, names or scenarios.

The private inventory binds each native literal load/static pointer to the
immutable ELF. English is placed in the unused read-only PT_LOAD; tiny leaf
stubs preserve each original instruction's non-destination side effects.
"""
from __future__ import annotations

import copy
import re
import struct

import native_layout_patch
import project

BINDINGS = project.ROOT / "work/ui/native-text-inventory.json"
TRANSLATIONS = project.ROOT / "work/ui/native-text-translations.json"
BINDINGS_SHA256 = "f893d8990d39be0b7c00eb6cf69e1e24ced5d5aa09fff25aa54f46109bfbcae7"
DEFAULT_NAMES = {0xF73D8, 0xF73DD, 0xF73E6, 0xF73EB, 0xF73F2, 0xF73F7}
FORMAT = re.compile(r"%(?:%|[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspn])")

# 8F730 draws both two-state selectors (read text and Takaaki voice). These
# expanded positions leave room for full .7-scale words and their arrows.
# Collapsed values retain .5 scale but move left within their original row.
OPTION_SELECTOR_GEOMETRY = {
    "caller": 0x8F730, "row_origin_x": 161, "first_row_y": 148, "row_pitch": 36,
    "panel_offsets": [475, 1099], "centers": [653, 919],
    "collapsed_center": 391, "arrow_center_margin": 33,
    "arrow_width": 32, "pulse_width": 48, "minimum_clearance": 8,
}
OPTION_SELECTOR_SOURCE = {
    0x8F7E4: "30fb019b", 0x8F834: "30bb019c",
    0x8F8B8: "30fb038b", 0x8F9DC: "333b0310", 0x8F9E0: "32db030f",
    0x8F9E4: "33bb027d", 0x8F9E8: "337b027e",
    0x8FC00: "33a30018",
}


def encode_text(original, translated, encoding):
    """Keep native printf arguments and strict source-consumer encoding."""
    if not isinstance(translated, str) or not translated.strip():
        raise ValueError("UI replacement must be nonblank text")
    if any((ord(char) < 32 and char != "\n") or ord(char) == 127 for char in translated):
        raise ValueError("UI replacement contains a literal control character")
    original_formats = [(match.group(), re.match(r"\d*", original[match.end():]).group())
                        for match in FORMAT.finditer(original)]
    translated_formats = [(match.group(), re.match(r"\d*", translated[match.end():]).group())
                          for match in FORMAT.finditer(translated)]
    if original_formats != translated_formats:
        raise ValueError("UI replacement changes ordered printf conversions or numeric suffixes")
    if FORMAT.sub("", translated).count("%") != FORMAT.sub("", original).count("%"):
        raise ValueError("UI replacement changes literal percent syntax")
    if ([char for char in original if "\ue000" <= char <= "\uf8ff"] !=
            [char for char in translated if "\ue000" <= char <= "\uf8ff"]):
        raise ValueError("UI replacement changes ordered native decorative glyphs")
    if encoding not in ("cp932", "utf8"):
        raise ValueError("Unexpected native UI encoding")
    encoded = translated.encode(encoding, errors="strict")
    if encoded.decode(encoding, errors="strict") != translated:
        raise ValueError("UI replacement does not round-trip its consumer encoding")
    return encoded


def apply(image, native):
    source = project.source_bytes()
    if len(image) != len(source) or native.get("ui_strings") or not native.get("typography"):
        raise ValueError("UI needs the native-only typography image exactly once, before scenario growth")
    if not native_layout_patch.native_code_matches(image, image, native):
        raise ValueError("UI input fails the complete native write guard")
    binding_bytes = BINDINGS.read_bytes()
    if project.digest(binding_bytes) != BINDINGS_SHA256:
        raise ValueError("Private source-bound UI inventory has changed")
    bindings = project.load(BINDINGS)
    translations = project.load(TRANSLATIONS)
    if any(document["source_sha256"] != project.digest(source) for document in (bindings, translations)):
        raise ValueError("UI inventory or translations identify another source ELF")
    records = translations["records"]
    expected = {row["offset"]: row for row in bindings["records"]}
    if len(records) != 148 or len(expected) != 148 or {row["offset"] for row in records} != expected.keys():
        raise ValueError("UI translation inventory is incomplete or duplicated")
    phoff = struct.unpack_from(">Q", source, 0x20)[0]
    phsize, phcount = struct.unpack_from(">HH", source, 0x36)
    if phsize != 56 or phcount != 8:
        raise ValueError("Unexpected native UI program-header layout")
    header_offset = phoff + 2 * phsize
    old_header = struct.unpack_from(">IIQQQQQQ", source, header_offset)
    if (old_header[0:2] != (1, 4) or any(old_header[3:7]) or old_header[7] != 0x10000
            or image[header_offset:header_offset + phsize] != source[header_offset:header_offset + phsize]):
        raise ValueError("Original empty read-only PT_LOAD is unavailable")
    headers = [struct.unpack_from(">IIQQQQQQ", image, phoff + index * phsize) for index in range(phcount)]
    address = (max(row[3] + row[6] for row in headers if row[0] == 1 and row[6]) + 0xFFFF) & -0x10000
    file_offset = (len(source) + 0xFFFF) & -0x10000
    start = native["rx_extension"]["file_end"]
    if any(source[start:native_layout_patch.CAVE_END]) or any(image[start:native_layout_patch.CAVE_END]):
        raise ValueError("UI helpers require untouched zero RX padding")
    result, report = bytearray(image), copy.deepcopy(native)
    strings, helpers, rows = bytearray(), bytearray(), []
    sites = {int(row["file_offset"], 0) for row in report["patches"]}
    data_sites = set()
    assembler = native_layout_patch._assembler()
    report["data_patches"] = []
    for row in records:
        binding = expected[row["offset"]]
        if any(row[key] != value for key, value in binding.items()):
            raise ValueError("UI translation changes immutable source/reference metadata")
        offset, old_va = row["offset"], row["va"]
        if not 0xF7300 <= offset < 0xF8C04 or old_va != offset + 0x10000:
            raise ValueError("UI source constant is outside the reviewed read-only region")
        original = row["original"].encode(row["encoding"])
        if (source[offset:offset + len(original) + 1] != original + b"\0"
                or row["source_sha256"] != project.digest(original)):
            raise ValueError("UI source string differs from its immutable bytes/hash")
        encoded = encode_text(row["original"], row["translated"], row["encoding"])
        if row["translated_sha256"] != project.digest(encoded) or not row.get("reviewer", "").strip():
            raise ValueError("UI translation hash or attributed review is missing")
        if offset in DEFAULT_NAMES:
            if row["status"] != "preserved_player_default" or encoded != original:
                raise ValueError("Personal default names are not UI labels and must remain unchanged")
            continue
        if row["status"] != "translated" or encoded == original:
            raise ValueError("UI label lacks an actual reviewed translation")
        if not row["code_references"] and not row["data_references"]:
            raise ValueError("UI string has no proven native consumer")
        target = address + len(strings)
        strings.extend(encoded + b"\0")
        for reference in row["code_references"]:
            pc, register = reference["site"], reference["register"]
            at = pc - 0x10000
            if at in sites or not 0x230 <= at < 0xD631C or not 0 <= register < 32:
                raise ValueError("UI literal load overlaps an existing native patch or leaves executable text")
            before = source[at:at + 4]
            if image[at:at + 4] != before:
                raise ValueError("UI literal load differs from immutable source")
            helper_va = start + 0x10000 + len(helpers)
            # Replay addic/ori first, preserving XER/CR and every other register.
            tail = bytes(assembler.asm(f"lis {register},{target >> 16}; ori {register},{register},{target & 0xFFFF}", addr=helper_va + 4)[0])
            tail += bytes(assembler.asm(f"b {pc + 4:#x}", addr=helper_va + 12)[0])
            blob = before + tail
            after = bytes(assembler.asm(f"b {helper_va:#x}", addr=pc)[0])
            if len(blob) != 16 or len(after) != 4:
                raise ValueError("UI literal helper instruction expansion")
            helpers.extend(blob)
            result[at:at + 4] = after
            sites.add(at)
            purpose = f"ui_literal_{offset:x}_{pc:x}"
            report["patches"].append({"va": hex(pc), "file_offset": hex(at), "source_before": before.hex(),
                                      "input_before": before.hex(), "after": after.hex(), "purpose": purpose})
            report["injected_blocks"].append({"name": purpose, "va": hex(helper_va), "size": len(blob),
                                              "sha256": project.digest(blob)})
        for pointer in row["data_references"]:
            at = int(pointer, 0)
            before, after = struct.pack(">I", old_va), struct.pack(">I", target)
            if at in data_sites or at % 4 or not 0x642000 <= at <= 0x647C48:
                raise ValueError("UI pointer is outside reviewed initialized UI tables or duplicated")
            if source[at:at + 4] != before or image[at:at + 4] != before:
                raise ValueError("UI table pointer differs from immutable source")
            result[at:at + 4] = after
            data_sites.add(at)
            report["data_patches"].append({"file_offset": hex(at), "source_before": before.hex(),
                                          "after": after.hex(), "purpose": f"ui_table_{offset:x}"})
        rows.append({"source_file_offset": offset, "virtual_address": target, "size": len(encoded) + 1,
                     "sha256": project.digest(encoded), "encoding": row["encoding"],
                     "code_references": row["code_references"], "data_references": row["data_references"]})

    def patch_site(pc, purpose, after):
        at = pc - 0x10000
        before = source[at:at + 4]
        if at in sites or image[at:at + 4] != before or len(after) != 4:
            raise ValueError("UI consumer correction overlaps or differs from immutable source")
        sites.add(at)
        result[at:at + 4] = after
        report["patches"].append({"va": hex(pc), "file_offset": hex(at),
                                  "source_before": before.hex(), "input_before": before.hex(),
                                  "after": after.hex(), "purpose": purpose})

    def instruction(text, pc):
        encoded = bytes(assembler.asm(text, addr=pc)[0])
        if len(encoded) != 4:
            raise ValueError("UI consumer instruction expansion")
        return encoded

    def emit(purpose, lines):
        pc = start + 0x10000 + len(helpers)
        blob = b"".join(line if isinstance(line, bytes) else instruction(line, pc + index * 4)
                        for index, line in enumerate(lines))
        helpers.extend(blob)
        report["injected_blocks"].append({"name": purpose, "va": hex(pc), "size": len(blob),
                                          "sha256": project.digest(blob)})
        return pc

    targets = {row["source_file_offset"]: row["virtual_address"] for row in rows}
    consumer_fixes = []
    # These native labels were memcpy'd into 10/39-byte stack arrays. Point the
    # read-only draw argument at the complete translation instead of truncating
    # it, growing the frame, or writing into the new read-only mapping.
    for pc, register, text_offset in ((0x876EC, 29, 0xF77A0), (0x87D48, 30, 0xF77A0),
                                       (0x879D8, 28, 0xF77D4)):
        target = targets[text_offset]
        helper = emit(f"ui_name_label_{pc:x}", [
            f"lis {register},{target >> 16}", f"ori {register},{register},{target & 0xFFFF}",
            f"b {pc + 4:#x}"])
        patch_site(pc, "ui_name_label_without_fixed_copy", instruction(f"bl {helper:#x}", pc))
        consumer_fixes.append({"site": hex(pc), "source_text": hex(text_offset), "register": register,
                               "action": "replace fixed memcpy with complete read-only label pointer"})
    for pc in (0x880FC, 0x88114):
        patch_site(pc, "ui_name_help_without_fixed_copy", instruction("nop", pc))
    pc = 0x8813C
    helper_va = start + 0x10000 + len(helpers)
    primary, secondary = targets[0xF75B4], targets[0xF76A4]
    helper = emit("ui_complete_name_help_selection", [
        source[pc - 0x10000:pc - 0x10000 + 4],
        f"lis 31,{primary >> 16}", f"ori 31,31,{primary & 0xFFFF}",
        f"beq {helper_va + 24:#x}",
        f"lis 31,{secondary >> 16}", f"ori 31,31,{secondary & 0xFFFF}",
        f"b {pc + 4:#x}"])
    patch_site(pc, "ui_complete_name_help_selection", instruction(f"b {helper:#x}", pc))
    consumer_fixes.append({"site": hex(pc), "source_texts": ["0xf75b4", "0xf76a4"],
                           "register": 31, "action": "retain original mode predicate; bypass both fixed stack copies"})
    name_help = helper
    # UI raw strings need their own drawing/measurement pair. Do not reuse the
    # save-caption clone or dialogue's already positioned character records.
    tracking = []
    for pc, destination, metric_pointer, operation in (
            (0x1C3D0, 3, "lwz 12,0x7c(31)", "addc 3,3,4"),
            (0x1C71C, 10, "mr 12,5", "addc 10,10,3")):
        helper_va = start + 0x10000 + len(helpers)
        helper = emit(f"ui_latin_tracking_{pc:x}", [
            operation, "stdu 1,-0x40(1)", "std 0,0x28(1)", "std 12,0x30(1)",
            "mfcr 0", "std 0,0x38(1)", metric_pointer,
            "lis 0,0x25", "ori 0,0,0x7038", "cmpw 12,0",
            f"bne {helper_va + 48:#x}", f"addi {destination},{destination},4",
            "ld 0,0x38(1)", "mtcr 0", "ld 12,0x30(1)", "ld 0,0x28(1)",
            "addi 1,1,0x40", f"b {pc + 4:#x}"])
        patch_site(pc, "ui_latin_tracking", instruction(f"b {helper:#x}", pc))
        tracking.append({"site": hex(pc), "helper": hex(helper),
                         "main_font_metric_pointer": "0x257038",
                         "extra_unscaled_advance": 4})
    proportional = next(int(block["va"], 0) for block in native["injected_blocks"]
                        if block["name"] == "caption_fixed_renderer_with_latin_metrics")
    helper_va = start + 0x10000 + len(helpers)
    dispatcher = emit("ui_main_font_proportional_dispatch", [
        "lis 12,0x25", "ori 12,12,0x7038", "lwz 0,0x7c(3)", "cmpw 0,12",
        f"bne {helper_va + 24:#x}", f"b {proportional:#x}", "b 0x1be28"])
    for pc in (0x8E80C, 0x8E840):
        patch_site(pc, "ui_main_font_proportional_dispatch", instruction(f"bl {dispatcher:#x}", pc))
    # The expanded list formerly centered complete English at x+637/x+783:
    # those fixed Japanese slots overlap at the original .7 scale. Reposition
    # only these two-state values, retaining colors, predicates and the native
    # centered measure/draw pair. Expanded cells use otherwise empty screen
    # space; collapsed Whole Page moves left to stay inside its original row.
    # Neither glyph axis is condensed. Margin33 clears the centered 48px pulse
    # by 8px even when odd measured widths round text/arrow halves differently.
    for pc, expected_word in OPTION_SELECTOR_SOURCE.items():
        if source[pc - 0x10000:pc - 0x10000 + 4].hex() != expected_word:
            raise ValueError("Two-state selector differs from its reviewed source geometry")
    selector_sites = (
        (0x8F7E4, "addic 7,27,391"), (0x8F834, "addic 5,27,392"),
        (0x8F8B8, "addic 7,27,1099"),
        (0x8F9DC, "addic 25,27,920"), (0x8F9E0, "addic 22,27,919"),
        (0x8F9E4, "addic 29,27,653"), (0x8F9E8, "addic 27,27,654"),
        (0x8FC00, "addic 29,3,33"),
    )
    for pc, text in selector_sites:
        patch_site(pc, "ui_full_word_selector_geometry", instruction(text, pc))
    report["ui_consumers"] = {"fixed_copy_bypasses": consumer_fixes,
                               "name_help_selection": hex(name_help), "font_dispatcher": hex(dispatcher),
                               "proportional_renderer": hex(proportional), "latin_tracking": tracking,
                               "option_selector_geometry": dict(
                                   OPTION_SELECTOR_GEOMETRY,
                                   instruction_sites=[hex(pc) for pc in OPTION_SELECTOR_SOURCE],
                                   expanded_scale="original 0.7 on both axes",
                                   collapsed_scale="original 0.5 on both axes",
                                   selection_and_pulse_predicates_unchanged=True),
                               "dialogue_record_consumer": {"site": "0x59488", "target": "0x1be28",
                                                            "positioned_by": "0x594e8"},
                               "fixed_name_grid_calls_unchanged": ["0x86c24", "0x872b8"]}
    graphics_manifest = project.ROOT / "work/ui/graphics-translations.json"
    geometry = project.load(graphics_manifest)["readable_layout"]
    table = geometry["legend_table_file_offset"]
    old_table = bytes.fromhex(geometry["legend_table_source_hex"])
    if table != 0x64112E or len(old_table) != 78 or source[table:table + 78] != old_table:
        raise ValueError("Readable footer layout differs from the pinned native caption table")
    entries = geometry["legend_entries"]
    if len(entries) != 13:
        raise ValueError("Readable footer layout must retain all 13 caption cells")
    new_table, occupied = bytearray(), []
    for index, entry in enumerate(entries):
        x, y, width = struct.unpack_from(">3H", old_table, index * 6)
        if entry["source_crop"] != [x, y, x + width, y + 20]:
            raise ValueError("Readable footer changes an immutable source caption binding")
        left, top, right, bottom = entry["staged_source_crop"]
        if (not 0 <= left < right <= 256 or not 0 <= top < bottom <= 128
                or bottom - top != 20 or any(left < r and l < right and top < b and t < bottom
                                             for l, t, r, b in occupied)):
            raise ValueError("Readable footer cells exceed or overlap the original atlas")
        occupied.append((left, top, right, bottom))
        new_table.extend(struct.pack(">3H", left, top, right - left))
    begin_words, end_words = table & -4, (table + len(old_table) + 3) & -4
    table_words = bytearray(source[begin_words:end_words])
    table_words[table - begin_words:table - begin_words + 78] = new_table
    for at in range(begin_words, end_words, 4):
        before = source[at:at + 4]
        after = bytes(table_words[at - begin_words:at - begin_words + 4])
        if before == after:
            continue
        if (at in data_sites or not native_layout_patch.ui_data_site(at)
                or image[at:at + 4] != before):
            raise ValueError("Readable footer lookup overlaps or differs from immutable source")
        result[at:at + 4] = after
        data_sites.add(at)
        report["data_patches"].append({"file_offset": hex(at), "source_before": before.hex(),
                                      "after": after.hex(), "purpose": "ui_legend_caption_geometry"})
    groups = geometry["credit_groups"]
    if (len(groups) != 2 or groups[0]["source_crop"] != [384, 160, 416, 192]
            or groups[1]["source_crop"] != [416, 160, 448, 192]):
        raise ValueError("Readable music credits change the source role order/cells")
    for group in groups:
        x, y, right, bottom = group["staged_source_crop"]
        left_dst, right_dst = group["destination_x"]
        if (not 0 <= x < right <= 512 or not 0 <= y < bottom <= 512
                or right - x != right_dst - left_dst or not 0 <= left_dst < right_dst <= 1280
                or not 32 <= bottom - y <= 52):
            raise ValueError("Readable music role geometry exceeds its source/destination bounds")
        if not right_dst + 4 <= group["artist_x"] < 1280:
            raise ValueError("Readable music artist column overlaps its complete role label")
    vocal, composer = (group["staged_source_crop"] for group in groups)
    if vocal[3] - vocal[1] != composer[3] - composer[1]:
        raise ValueError("Music role banks must share the same native row height")
    credit_sites = [
        (0x9BFD4, f"addic 26,28,{5 + vocal[3] - vocal[1]}"),
        (0x9C014, f"li 7,{vocal[3]}"), (0x9C030, f"li 4,{groups[0]['destination_x'][0]}"),
        (0x9C034, f"li 10,{vocal[2]}"), (0x9C03C, f"li 6,{groups[0]['destination_x'][1]}"),
        (0x9C058, f"li 9,{vocal[1]}"), (0x9C150, f"li 8,{composer[3]}"),
        (0x9C170, f"li 4,{groups[1]['destination_x'][0]}"),
        (0x9C178, f"li 6,{groups[1]['destination_x'][1]}"),
        (0x9C17C, f"li 8,{composer[0]}"), (0x9C180, f"li 9,{composer[1]}"),
        (0x9C188, f"li 10,{composer[2]}"), (0x9BD04, "fmr 26,27")]
    for pc, shadow in ((0x9C070, 0), (0x9C0A8, 1), (0x9C0D8, 0), (0x9C108, 1)):
        credit_sites.append((pc, f"li 4,{groups[0]['artist_x'] + shadow}"))
    for pc, shadow in ((0x9C1B0, 0), (0x9C1E0, 1), (0x9C210, 0), (0x9C240, 1)):
        credit_sites.append((pc, f"li 4,{groups[1]['artist_x'] + shadow}"))
    for pc, text in credit_sites:
        patch_site(pc, "ui_readable_music_credits", instruction(text, pc))
    report["ui_graphic_layout"] = {"graphics_manifest_sha256": project.digest(graphics_manifest.read_bytes()),
                                    "legend_table_file_offset": table, "legend_entries": entries,
                                    "credit_groups": groups, "credit_instruction_sites": [hex(pc) for pc, _ in credit_sites],
                                    "music_title_font_pixels": 24, "music_credit_font_preset": "existing F27=0.35",
                                    "music_row_height": 60, "music_theme_y_offset": 34,
                                    "font_assets_unchanged": True, "runtime_accepted": False}
    end = start + len(helpers)
    if end > native_layout_patch.CAVE_END or address + len(strings) >= 0x80000000:
        raise ValueError("Native UI strings/helpers exceed reviewed address bounds")
    result[start:end] = helpers
    result.extend(b"\0" * (file_offset - len(result)))
    result.extend(strings)
    struct.pack_into(">IIQQQQQQ", result, header_offset,
                     1, 4, file_offset, address, address, len(strings), len(strings), 0x10000)
    struct.pack_into(">QQ", result, phoff + 0x20, end, end)
    report["rx_extension"].update(file_end=end, new_filesz=end, new_memsz=end,
                                  size=end - report["rx_extension"]["file_begin"])
    report["ui_strings"] = {"program_header_index": 2, "program_header_offset": header_offset,
                             "file_offset": file_offset, "virtual_address": address,
                             "file_size": len(strings), "memory_size": len(strings), "flags": 4,
                             "alignment": 0x10000, "sha256": project.digest(strings),
                             "source_header": source[header_offset:header_offset + phsize].hex(),
                             "bindings_sha256": BINDINGS_SHA256,
                             "translations_sha256": project.digest(TRANSLATIONS.read_bytes()),
                             "translated_records": len(rows), "preserved_player_defaults": sorted(DEFAULT_NAMES),
                             "records": rows, "runtime_accepted": False}
    report["output_sha256"] = project.digest(result)
    return bytes(result), report
