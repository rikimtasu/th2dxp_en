"""Grow complete native history records and own backlog decode scratch; no deployment.

Each original ring slot retains its header and traversal stride. Its former
payload starts with an owned pointer/capacity pair and a small inline buffer.
Only overflowing records allocate. Allocations are reused by that slot and
released on arena destruction/reset. Backlog scanner input owns a full copy.
"""
from __future__ import annotations

import capstone
import copy
import re
import struct
import textwrap

import native_layout_patch
import project


def apply(image, native):
    source = project.source_bytes()
    if native.get("history") or not native.get("ui_strings"):
        raise ValueError("History correction requires the native UI mapping exactly once")
    if not native_layout_patch.native_code_matches(image, image, native):
        raise ValueError("History input differs from its source-bound manifest")
    result, report = bytearray(image), copy.deepcopy(native)
    ui = report["ui_strings"]
    end = ui["file_offset"] + ui["file_size"]
    if end != len(result):
        raise ValueError("History helpers must precede scenario relocation")
    result.extend(bytes((-end) % 16))
    code_start = len(result)
    base = ui["virtual_address"] + code_start - ui["file_offset"]
    ks, code, entries = native_layout_patch._assembler(), bytearray(), {}
    sites = {int(row["va"], 0) for row in report["patches"]}

    def assemble(body, address):
        lines, external, count = [], [], 0
        for line in textwrap.dedent(body).strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if re.fullmatch(r"(?:b|bl|beq|bne|bgt|bge|blt|ble)\s+0x[0-9a-fA-F]+", line):
                external.append((count, line))
                lines.append("nop")
            else:
                lines.append(line)
            if not line.endswith(":"):
                count += 1
        encoded, _ = ks.asm("\n".join(lines), addr=address)
        blob = bytearray(encoded)
        if len(blob) != count * 4:
            raise ValueError("History helper instruction expansion")
        for index, line in external:
            replacement, _ = ks.asm(line, addr=address + index * 4)
            if len(replacement) != 4:
                raise ValueError("History external branch expansion")
            blob[index * 4:index * 4 + 4] = bytes(replacement)
        return bytes(blob)

    def emit(name, body):
        address = base + len(code)
        blob = assemble(body, address)
        code.extend(blob)
        entries[name] = address
        return address

    def patch(pc, body):
        offset = pc - 0x10000
        if pc in sites or image[offset:offset + 4] != source[offset:offset + 4]:
            raise ValueError("History site overlaps another correction or changed source")
        after = assemble(body, pc)
        if len(after) != 4:
            raise ValueError("History source patch must be one instruction")
        result[offset:offset + 4] = after
        sites.add(pc)
        report["patches"].append({"va": hex(pc), "file_offset": hex(offset),
                                 "source_before": source[offset:offset + 4].hex(),
                                 "input_before": source[offset:offset + 4].hex(),
                                 "after": after.hex(), "purpose": "owned_growable_history"})

    initialize = emit("initialize_history_payload", """
        stdu 1,-0x80(1)
        mflr 0
        std 0,0x90(1)
        std 31,0x78(1)
        mr 31,3
        bl 0xd83a4
        addi 3,31,8
        stw 3,0(31)
        li 3,0x340
        stw 3,4(31)
        ld 31,0x78(1)
        ld 0,0x90(1)
        mtlr 0
        addi 1,1,0x80
        blr
    """)
    patch(0x6999C, f"bl {initialize:#x}")
    reserve = emit("reserve_history_payload", """
        lwz 5,0x10(3)
        cmplw 4,5
        ble reserve_return
        lis 5,0x7fff
        ori 5,5,0xf000
        cmplw 4,5
        bgt reserve_invalid
        stdu 1,-0xa0(1)
        mflr 0
        std 0,0xb0(1)
        std 28,0x80(1)
        std 29,0x88(1)
        std 30,0x90(1)
        std 31,0x98(1)
        mr 31,3
        addi 30,4,0xfff
        rlwinm 30,30,0,0,19
        mr 3,30
        bl 0x63d70
        cmpwi 3,0
        beq reserve_invalid
        mr 29,3
        lwz 28,0xc(31)
        mr 4,28
        lis 5,0x65
        lwz 5,-0x280(5)
        lis 6,1
        ori 6,6,0x4ce4
        lwzx 5,5,6
        bl 0xd0e18
        addi 3,31,0x14
        cmpw 28,3
        beq reserve_store
        mr 3,28
        bl 0x63da0
    reserve_store:
        stw 29,0xc(31)
        stw 30,0x10(31)
        ld 28,0x80(1)
        ld 29,0x88(1)
        ld 30,0x90(1)
        ld 31,0x98(1)
        ld 0,0xb0(1)
        mtlr 0
        addi 1,1,0xa0
    reserve_return:
        blr
    reserve_invalid:
        trap
    """)
    text_reserve = emit("reserve_complete_history_text", f"""
        stdu 1,-0x80(1)
        mflr 0
        std 0,0x90(1)
        std 31,0x78(1)
        mr 31,3
        mr 3,29
        bl 0xd34a8
        addi 4,3,1
        lis 5,1
        ori 5,5,0x4ce4
        lwzx 5,31,5
        add 4,4,5
        lis 5,1
        ori 5,5,0x4ce8
        lbzx 5,31,5
        cmpwi 5,0
        bne text_explicit_metadata
        addi 4,4,4
    text_explicit_metadata:
        addi 4,4,3
        rlwinm 4,4,0,0,29
        lis 5,1
        ori 5,5,0x4ce0
        lwzx 3,31,5
        bl {reserve:#x}
        mr 3,31
        ld 31,0x78(1)
        ld 0,0x90(1)
        mtlr 0
        addi 1,1,0x80
        lis 4,1
        b 0x69bbc
    """)
    patch(0x69BB8, f"b {text_reserve:#x}")
    text_destination = emit("resolve_history_writer", """
        subf 28,4,5
        lwz 5,0xc(4)
        add 28,28,5
        b 0x69bdc
    """)
    patch(0x69BD8, f"b {text_destination:#x}")
    metadata_reserve = emit("reserve_history_metadata", f"""
        stdu 1,-0x80(1)
        mflr 0
        std 0,0x90(1)
        std 3,0x60(1)
        std 4,0x68(1)
        std 5,0x70(1)
        lis 6,1
        ori 6,6,0x4ce4
        lwzx 6,5,6
        mr 3,4
        addi 4,6,4
        bl {reserve:#x}
        ld 3,0x60(1)
        ld 4,0x68(1)
        ld 5,0x70(1)
        ld 0,0x90(1)
        mtlr 0
        addi 1,1,0x80
        lis 6,1
        b 0x69af8
    """)
    patch(0x69AF4, f"b {metadata_reserve:#x}")
    metadata_destination = emit("resolve_history_metadata_writer", """
        lwz 0,0xc(4)
        add 4,0,5
        b 0x69b10
    """)
    patch(0x69B0C, f"b {metadata_destination:#x}")
    patch(0x69B14, "nop")
    patch(0x69E4C, "lwz 5,0xc(5)")
    patch(0x69E50, "add 7,5,7")
    patch(0x6A200, "lwz 0,0xc(5)")
    patch(0x6A204, "add 4,0,4")
    # Backlog reconstructs whole logical records. Pagination has retired the
    # gameplay prefix, so its current queue no longer has matching ordinals.
    # Use the existing completed-record behavior; do not mark gameplay read.
    patch(0x6A284, "li 7,0")
    scratch = emit("owned_complete_backlog_scratch", """
        stdu 1,-0x80(1)
        mflr 0
        std 0,0x90(1)
        std 31,0x78(1)
        mr 31,4
        mr 3,4
        bl 0xd34a8
        addi 3,3,1
        bl 0x63d70
        cmpwi 3,0
        beq scratch_invalid
        mr 24,3
        mr 4,31
        bl 0xd54dc
        ld 31,0x78(1)
        ld 0,0x90(1)
        mtlr 0
        addi 1,1,0x80
        blr
    scratch_invalid:
        trap
    """)
    patch(0x6A20C, f"bl {scratch:#x}")
    release_scratch = emit("release_backlog_scratch_after_scan", """
        stdu 1,-0x70(1)
        mflr 0
        std 0,0x80(1)
        mr 3,24
        bl 0x63da0
        ld 0,0x80(1)
        mtlr 0
        addi 1,1,0x70
        b 0x6a2a4
    """)
    patch(0x6A2A0, f"b {release_scratch:#x}")
    destroy = emit("release_all_history_payloads", """
        stdu 1,-0x90(1)
        mflr 0
        std 0,0xa0(1)
        std 29,0x78(1)
        std 30,0x80(1)
        std 31,0x88(1)
        mr 31,3
        addi 30,3,0x10
        li 29,100
    destroy_next:
        lwz 3,0xc(30)
        addi 4,30,0x14
        cmpw 3,4
        beq destroy_inline
        bl 0x63da0
    destroy_inline:
        addi 30,30,0x354
        addi 29,29,-1
        cmpwi 29,0
        bne destroy_next
        mr 3,31
        bl 0x45930
        ld 29,0x78(1)
        ld 30,0x80(1)
        ld 31,0x88(1)
        ld 0,0xa0(1)
        mtlr 0
        addi 1,1,0x90
        blr
    """)
    patch(0x69A4C, f"bl {destroy:#x}")
    patch(0x6AA3C, f"bl {destroy:#x}")

    def clone(begin, size, *, targets=None, insert_after=None, pristine=False):
        decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
        original = source if pristine else image
        instructions = list(decoder.disasm(original[begin - 0x10000:begin - 0x10000 + size], begin))
        if sum(ins.size for ins in instructions) != size:
            raise ValueError("Incomplete native renderer clone")
        address = base + len(code)
        mapping, cursor = {}, address
        for ins in instructions:
            mapping[ins.address] = cursor
            cursor += 4 + (4 if ins.address == insert_after else 0)
        for ins in instructions:
            word = int.from_bytes(ins.bytes, "big")
            opcode = word >> 26
            if opcode in (16, 18) and not word & 2:
                mask, bits = (0x03FFFFFC, 26) if opcode == 18 else (0xFFFC, 16)
                displacement = word & mask
                if displacement & (1 << (bits - 1)):
                    displacement -= 1 << bits
                target = ins.address + displacement
                target = mapping.get(target, (targets or {}).get(target, target))
                displacement = target - mapping[ins.address]
                if not -(1 << (bits - 1)) <= displacement < (1 << (bits - 1)):
                    raise ValueError("Relocated renderer branch exceeds native displacement")
                word = (word & ~mask) | (displacement & mask)
            code.extend(word.to_bytes(4, "big"))
            if ins.address == insert_after:
                code.extend(assemble("addi 5,5,4", base + len(code)))
        return address

    # Select wider ASCII advances for raw options only; Japanese and the
    # accepted save-caption metric function retain their original geometry.
    caption_metric = next(row for row in native["injected_blocks"]
                          if row["name"] == "caption_ascii_metric_geometry")
    metric_va = int(caption_metric["va"], 0)
    decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    advance = next(ins.address for ins in decoder.disasm(
        image[metric_va - 0x10000:metric_va - 0x10000 + caption_metric["size"]], metric_va)
                   if ins.mnemonic in ("add", "addc") and ins.op_str == "r5, r5, r7")
    ui_metric = clone(metric_va, caption_metric["size"], insert_after=advance)
    caption_draw = next(int(row["va"], 0) for row in native["injected_blocks"]
                        if row["name"] == "caption_fixed_renderer_with_latin_metrics")
    chooser = emit("raw_option_tracking_dispatch", f"""
        lwz 0,0x114(1)
        lis 12,8
        ori 12,12,0xe810
        cmpw 0,12
        beq option_metric
        addi 12,12,0x34
        cmpw 0,12
        beq option_metric
        bl {metric_va:#x}
        b {caption_draw + 0x1C008 - 0x1BE28:#x}
    option_metric:
        bl {ui_metric:#x}
        b {caption_draw + 0x1C008 - 0x1BE28:#x}
    """)
    entry = next(row for row in report["injected_blocks"]
                 if row["name"] == "caption_ascii_geometry_entry")
    offset = int(entry["va"], 0) - 0x10000
    result[offset:offset + 4] = assemble(f"b {chooser:#x}", int(entry["va"], 0))
    entry["sha256"] = project.digest(result[offset:offset + entry["size"]])

    # Keep Music's accepted two-column spacing/font sizes instead of shrinking
    # full titles or credits when unrelated help/options tracking increases.
    music_draw = clone(0x1C178, 0x1C5B0 - 0x1C178, pristine=True)
    music_measure = clone(0x1C5B8, 0x1C8B0 - 0x1C5B8, pristine=True)
    music_center = clone(0x1C8B8, 0x1CAA8 - 0x1C8B8,
                         targets={0x1C178: music_draw, 0x1C5B8: music_measure}, pristine=True)
    music_targets = {0x1C178: music_draw, 0x1C8B8: music_center}
    music_sites = []
    for ins in decoder.disasm(source[0x8BCFC:0x8C26C], 0x9BCFC):
        if ins.mnemonic == "bl" and int(ins.op_str, 0) in music_targets:
            patch(ins.address, f"bl {music_targets[int(ins.op_str, 0)]:#x}")
            music_sites.append(hex(ins.address))
    report["ui_tracking"] = {"main_font_gap": 6, "extra_design_pixels": 4,
                              "raw_option_metric": hex(ui_metric),
                              "music_original_spacing_calls": music_sites,
                              "save_caption_metric_unchanged": True,
                              "japanese_paths_unchanged": True}
    result.extend(code)
    size = len(result) - ui["file_offset"]
    if size > 0x10000:
        raise ValueError("History code exceeds the bounded UI/native mapping")
    ui.update(file_size=size, memory_size=size, flags=5,
              sha256=project.digest(result[ui["file_offset"]:]))
    struct.pack_into(">IIQQQQQQ", result, ui["program_header_offset"], 1, 5,
                     ui["file_offset"], ui["virtual_address"], ui["virtual_address"],
                     size, size, 0x10000)
    report["supplemental_code"] = [{"virtual_address": base, "file_offset": code_start,
                                    "size": len(code), "sha256": project.digest(code)}]
    report["history"] = {"entries": {name: hex(address) for name, address in entries.items()},
                           "ring_slots": 100, "record_stride": 0x354,
                           "inline_capacity": 0x340, "allocation_quantum": 4096,
                           "overflow_reused_per_slot": True, "runtime_accepted": False,
                           "scratch_lifetime": "Owned full-string copy, released after synchronous native scanner"}
    report["output_sha256"] = project.digest(result)
    return bytes(result), report
