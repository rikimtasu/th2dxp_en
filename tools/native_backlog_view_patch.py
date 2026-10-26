"""Scroll whole owned backlog records with the source record-navigation buttons.

No logical history entries are split. Cached glyph coordinates are reconstructed
relative to their span's full-precision origin before viewport clipping; this
also avoids treating wrapped signed-short cache coordinates as document space.
"""
from __future__ import annotations

import copy
import re
import struct
import textwrap

import capstone
import native_layout_patch
import project

OFFSET = 0x554  # Owned padding in the existing pagination context allocation.


def apply(image, native):
    source = project.source_bytes()
    if not native.get("history") or not native.get("pagination") or native.get("backlog_view"):
        raise ValueError("Backlog viewport requires owned history/pagination exactly once")
    if not native_layout_patch.native_code_matches(image, image, native):
        raise ValueError("Backlog viewport input differs from its source-bound manifest")
    result, report = bytearray(image), copy.deepcopy(native)
    ui = report["ui_strings"]
    end = ui["file_offset"] + ui["file_size"]
    if end != len(result) or native["pagination"]["context_allocation"]["new"] < 0x558:
        raise ValueError("Backlog viewport requires native-only input and owned context padding")
    result.extend(bytes((-end) % 16))
    start = len(result)
    base = ui["virtual_address"] + start - ui["file_offset"]
    ks, code, entries = native_layout_patch._assembler(), bytearray(), {}
    sites = {int(row["va"], 0) for row in report["patches"]}

    def assemble(body, address):
        lines, branches, count = [], [], 0
        for line in textwrap.dedent(body).strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if re.fullmatch(r"(?:b|bl|beq|bne|bgt|bge|blt|ble)\s+0x[0-9a-fA-F]+", line):
                branches.append((count, line))
                lines.append("nop")
            else:
                lines.append(line)
            if not line.endswith(":"):
                count += 1
        encoded, _ = ks.asm("\n".join(lines), addr=address)
        blob = bytearray(encoded)
        if len(blob) != count * 4:
            raise ValueError("Backlog viewport helper instruction expansion")
        for index, line in branches:
            mnemonic, target = line.split()
            displacement = int(target, 0) - (address + index * 4)
            bound = 1 << (25 if mnemonic in ("b", "bl") else 15)
            if displacement & 3 or not -bound <= displacement < bound:
                raise ValueError("Backlog viewport external branch exceeds its instruction range")
            replacement, _ = ks.asm(line, addr=address + index * 4)
            if len(replacement) != 4:
                raise ValueError("Backlog viewport branch expansion")
            blob[index * 4:index * 4 + 4] = bytes(replacement)
        return bytes(blob)

    def emit(name, body):
        address = base + len(code)
        code.extend(assemble(body, address))
        entries[name] = address
        return address

    def patch(pc, body):
        offset = pc - 0x10000
        if pc in sites or image[offset:offset + 4] != source[offset:offset + 4]:
            raise ValueError("Backlog viewport source guard/overlap at " + hex(pc))
        after = assemble(body, pc)
        if len(after) != 4:
            raise ValueError("Backlog viewport source patch must be one instruction")
        result[offset:offset + 4] = after
        sites.add(pc)
        report["patches"].append({"va": hex(pc), "file_offset": hex(offset),
                                  "source_before": source[offset:offset + 4].hex(),
                                  "input_before": source[offset:offset + 4].hex(),
                                  "after": after.hex(), "purpose": "whole_record_backlog_viewport"})

    initialize = emit("initialize_backlog_scroll", f"""
        stw 27,{OFFSET}(28)
        clrldi 3,3,0x20
        b 0x70e44
    """)
    patch(0x70E40, f"b {initialize:#x}")
    navigate = emit("navigate_record_viewport", f"""
        cmpwi 4,0
        beq view_native
        stdu 1,-0x90(1)
        lwz 5,0x510(3)
        lfs 0,0x38(3)
        lfs 1,0x48(3)
        fadds 2,0,1
        fsubs 3,1,1
        fmr 4,3
        lfs 5,0x98(3)
        lfs 6,0x88(3)
        fmuls 5,5,6
    view_extent_loop:
        cmpwi 5,0
        beq view_extent_done
        lfs 6,0x88(5)
        fmuls 6,6,5
        fcmpu 0,6,4
        ble view_cell_ready
        fmr 4,6
    view_cell_ready:
        lfs 7,0x68(5)
        fadds 7,7,6
        fsubs 7,7,2
        fcmpu 0,7,3
        ble view_next_span
        fmr 3,7
    view_next_span:
        lwz 5,0x14(5)
        b view_extent_loop
    view_extent_done:
        fctiwz 3,3
        stfd 3,0x70(1)
        lwz 6,0x74(1)
        cmpwi 6,0
        ble view_native_restore
        addi 6,6,1
        fsubs 1,1,4
        fctiwz 1,1
        stfd 1,0x70(1)
        lwz 7,0x74(1)
        cmpwi 7,1
        bge view_step_ready
        li 7,1
    view_step_ready:
        lwz 8,{OFFSET}(3)
        cmpwi 4,-1
        beq view_up
        cmpwi 4,1
        bne view_native_restore
        cmpw 8,6
        bge view_native_restore
        add 8,8,7
        cmpw 8,6
        ble view_commit
        mr 8,6
        b view_commit
    view_up:
        cmpwi 8,0
        ble view_native_restore
        subf 8,7,8
        cmpwi 8,0
        bge view_commit
        li 8,0
    view_commit:
        stw 8,{OFFSET}(3)
        addi 1,1,0x90
        blr
    view_native_restore:
        addi 1,1,0x90
    view_native:
        stdu 1,-0xe0(1)
        b 0x69fec
    """)
    patch(0x69FE8, f"b {navigate:#x}")
    reset = emit("reset_rebuilt_record_scroll", f"""
        li 5,0
        stw 5,{OFFSET}(31)
        lis 29,0x65
        b 0x6a078
    """)
    patch(0x6A074, f"b {reset:#x}")

    # Clone the source cache consumer, not the font renderer. Each native glyph
    # call retains its original font, scale, alpha, codepoint and ordering.
    decoder = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    begin, end_draw = 0x59338, 0x594C4
    original = source[begin - 0x10000:end_draw - 0x10000]
    if image[begin - 0x10000:end_draw - 0x10000] != original:
        raise ValueError("Backlog cache consumer differs from guarded source")
    instructions = list(decoder.disasm(original, begin))
    prelude = f"""
        std 25,0xb0(1)
        std 26,0xb8(1)
        std 27,0xc0(1)
        std 28,0xc8(1)
        std 29,0xd0(1)
        lwz 27,{OFFSET}(5)
        lfs 0,0x38(5)
        fctiwz 1,0
        stfd 1,0x78(1)
        lwz 28,0x7c(1)
        lfs 1,0x48(5)
        fadds 1,0,1
        fctiwz 1,1
        stfd 1,0x78(1)
        lwz 29,0x7c(1)
        lfs 0,0x68(6)
        fctiwz 0,0
        stfd 0,0x78(1)
        lwz 26,0x7c(1)
        lfs 0,0x98(5)
        lfs 1,0x88(5)
        fmuls 0,0,1
        lfs 1,0x88(6)
        fmuls 0,0,1
        fctiwz 0,0
        stfd 0,0x78(1)
        lwz 25,0x7c(1)
        addi 25,25,1
    """
    restore = "\n".join(f"ld {reg},{offset}(1)" for reg, offset in
                         ((25, 0xB0), (26, 0xB8), (27, 0xC0), (28, 0xC8), (29, 0xD0)))
    draw = base + len(code)
    mapping, cursor = {}, draw
    for ins in instructions:
        mapping[ins.address] = cursor
        if ins.address == 0x5935C:
            cursor += len(assemble(prelude, cursor))
        if ins.address == 0x59378:
            cursor += 11 * 4
        if ins.address == 0x594A4:
            cursor += len(assemble(restore, cursor))
        cursor += 4
    for ins in instructions:
        address = base + len(code)
        if ins.address == 0x5935C:
            code.extend(assemble(prelude, address))
        if ins.address == 0x59378:
            code.extend(assemble(f"""
                lhz 12,2(30)
                subf 12,26,12
                extsh 12,12
                add 12,12,26
                subf 12,27,12
                cmpw 12,28
                blt {mapping[0x59490]:#x}
                add 11,12,25
                cmpw 11,29
                bgt {mapping[0x59490]:#x}
                nop
            """, base + len(code)))
        if ins.address == 0x594A4:
            code.extend(assemble(restore, base + len(code)))
        address = base + len(code)
        frame_changes = {0x59338: "stdu 1,-0xe0(1)", 0x59340: "std 0,0xf0(1)",
                         0x594A4: "ld 0,0xf0(1)", 0x594BC: "addi 1,1,0xe0"}
        if ins.address in frame_changes:
            blob = assemble(frame_changes[ins.address], address)
        elif ins.address in (0x593C8, 0x59450):
            blob = assemble("mr 5,12", address)
        else:
            word = int.from_bytes(ins.bytes, "big")
            opcode = word >> 26
            if opcode in (16, 18) and not word & 2:
                mask, bits = (0x03FFFFFC, 26) if opcode == 18 else (0xFFFC, 16)
                displacement = word & mask
                if displacement & (1 << (bits - 1)):
                    displacement -= 1 << bits
                target = mapping.get(ins.address + displacement, ins.address + displacement)
                displacement = target - address
                if not -(1 << (bits - 1)) <= displacement < (1 << (bits - 1)):
                    raise ValueError("Backlog draw relocation exceeds branch range")
                word = (word & ~mask) | (displacement & mask)
            blob = word.to_bytes(4, "big")
        code.extend(blob)
    entries["clipped_cache_consumer"] = draw
    dispatch = emit("draw_backlog_viewport", f"""
        lbz 5,0x28(31)
        cmpwi 5,1
        beq draw_history
        b 0x59338
    draw_history:
        mr 5,31
        mr 6,29
        b {draw:#x}
    """)
    patch(0x70A18, f"bl {dispatch:#x}")
    # 6AAE0 is the sole source caller of 38698. Its source icon is a 32px
    # quad at row*62.4+52+20; move/clip it with the text, retaining all native
    # voice-group indices, selection colours and animation phase.
    icon = emit("position_backlog_voice_icon", f"""
        fadds 31,1,31
        lis 12,0x65
        lwz 12,0x2614(12)
        lwz 12,0x2b4(12)
        lwz 11,{OFFSET}(12)
        extsw 11,11
        std 11,0xd0(1)
        lfd 0,0xd0(1)
        fcfid 0,0
        frsp 0,0
        fsubs 31,31,0
        lfs 0,0x38(12)
        fcmpu 0,31,0
        blt icon_clipped
        lfs 1,0x48(12)
        fadds 1,0,1
        li 11,32
        std 11,0xd0(1)
        lfd 0,0xd0(1)
        fcfid 0,0
        frsp 0,0
        fadds 0,31,0
        fcmpu 0,0,1
        bgt icon_clipped
        b 0x38748
    icon_clipped:
        b 0x38a10
    """)
    patch(0x38744, f"b {icon:#x}")
    result.extend(code)
    size = len(result) - ui["file_offset"]
    if size >= 0x10000:
        raise ValueError("Backlog viewport exceeds bounded RX UI mapping")
    ui.update(file_size=size, memory_size=size, flags=5,
              sha256=project.digest(result[ui["file_offset"]:]))
    struct.pack_into(">IIQQQQQQ", result, ui["program_header_offset"], 1, 5,
                     ui["file_offset"], ui["virtual_address"], ui["virtual_address"], size, size, 0x10000)
    report.setdefault("supplemental_code", []).append({"virtual_address": base, "file_offset": start,
                                                       "size": len(code), "sha256": project.digest(code)})
    report["backlog_view"] = {"entries": {name: hex(address) for name, address in entries.items()},
                              "offset_field": OFFSET, "record_slots": 100,
                              "controls": {"older_or_up": "0x400 -> 69FE8(-1)",
                                           "newer_or_down": "0x800 -> 69FE8(+1)"},
                              "geometry": "Source context+38/+48 and context+98*context+88*span+88",
                              "overlap": "viewport height minus largest source row cell",
                              "voice_icon": "Source38698 32px quad follows scroll and is clipped; metadata/selection indices unchanged",
                              "history_payloads_unchanged": True, "runtime_accepted": False}
    report["output_sha256"] = project.digest(result)
    return bytes(result), report
