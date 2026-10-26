"""Source-bound opacity, literal scratch and checkpoint fixes; no deployment.

The source has 32 opacity bytes, a 1024-byte VM literal scratch, and a small
inline save-text list adjacent to live flags. Proportional/long English exceeds
those independent assumptions. Save entries may now reference immutable native
scenario literals; old inline entries remain readable. No displayed text is cut.
"""
from __future__ import annotations

import copy
import re
import struct
import textwrap

import native_layout_patch
import project

SPAN_ALPHA = 0x14E0
FONT_ALPHA = 0x164
OPACITY_CAPACITY = 256
VM_SCRATCH = 0x7B0
VM_SIZE = VM_SCRATCH + 0x10000
TRACE_CAPACITY = 0x300
TRACE_TAG = 0xFF544852
TABLE_VA = 0xFE8B4
SCENARIO_COUNT = 1884


def apply(image, native):
    source = project.source_bytes()
    if not native_layout_patch.native_code_matches(image, image, native):
        raise ValueError("Runtime text correction requires a complete source-bound template")
    if native.get("runtime_text"):
        raise ValueError("Runtime text correction already present")
    start = native["rx_extension"]["file_end"]
    if any(source[start:native_layout_patch.CAVE_END]) or any(image[start:native_layout_patch.CAVE_END]):
        raise ValueError("Runtime text helpers require original zero RX padding")
    ks = native_layout_patch._assembler()
    result, code = bytearray(image), bytearray()
    report = copy.deepcopy(native)
    sites = {int(row["va"], 0): row for row in report["patches"]}
    entries = {}

    def assemble(body, address):
        lines, external, count = [], [], 0
        for line in textwrap.dedent(body).strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if re.fullmatch(r"(?:b|bl|beq|bne|bgt|bge|blt|ble|bso)\s+(?:(?:cr[0-7]),\s*)?0x[0-9a-fA-F]+", line):
                external.append((count, line))
                lines.append("nop")
            else:
                lines.append(line)
            if not line.endswith(":"):
                count += 1
        encoded, _ = ks.asm("\n".join(lines), addr=address)
        blob = bytearray(encoded)
        if len(blob) != count * 4:
            raise ValueError("Unexpected runtime helper instruction expansion")
        for index, line in external:
            replacement, _ = ks.asm(line, addr=address + index * 4)
            if len(replacement) != 4:
                raise ValueError("Runtime helper branch expansion")
            blob[index * 4:index * 4 + 4] = bytes(replacement)
        return bytes(blob)

    def emit(name, body):
        address = start + 0x10000 + len(code)
        blob = assemble(body, address)
        if start + len(code) + len(blob) > native_layout_patch.CAVE_END:
            raise ValueError("Runtime text helpers exceed bounded RX padding")
        code.extend(blob)
        entries[name] = address
        report["injected_blocks"].append({"name": name, "va": hex(address),
                                           "size": len(blob), "sha256": project.digest(blob)})
        return address

    def replace(va, instruction, purpose):
        offset = va - 0x10000
        row = sites.get(va)
        expected = bytes.fromhex(row["after"]) if row else source[offset:offset + 4]
        if image[offset:offset + 4] != expected:
            raise ValueError(f"Runtime text patch input differs at {va:#x}")
        after = assemble(instruction, va)
        if len(after) != 4:
            raise ValueError("Runtime text site must be exactly one instruction")
        result[offset:offset + 4] = after
        if row is None:
            row = {"va": hex(va), "file_offset": hex(offset),
                   "source_before": source[offset:offset + 4].hex()}
            report["patches"].append(row)
            sites[va] = row
        row.update(input_before=expected.hex(), after=after.hex(), purpose=purpose)

    # The native tail-fill reads alpha[index-1], including index0. Give it an
    # owned zero predecessor instead of aliasing the cached-width field.
    for va, instruction in (
        (0x6DA14, "li 3,0x15e0"), (0x6DA38, "addic 3,29,0x14df"),
        (0x6DA44, "li 5,0x101"), (0x59B78, "li 3,0x264"),
        (0x59160, "addic 30,30,0x164"), (0x59178, "li 5,0x100"),
        (0x59190, "li 5,0x100"), (0x59878, "addic 6,22,0x164"),
        (0x6FEAC, "addic 5,23,0x14e0"), (0x700AC, "cmpwi 29,0x100"),
        (0x7016C, "li 5,0x14e0"), (0x70178, "lbz 4,0x14e0(3)"),
        (0x70198, "li 4,0x14e0"), (0x701D4, "cmpwi 29,0x100"),
        (0x701DC, "lbz 3,0x14df(3)"), (0x701E4, "li 5,0x100"),
        (0x701FC, "stb 3,0x14e0(5)"), (0x703A0, "addic 5,30,0x14e0"),
    ):
        replace(va, instruction, "Move/size native opacity storage to match its 256 glyph records")

    allocation = emit("vm_extended_scratch_allocation", f"""
        lis 4,{VM_SIZE >> 16}
        ori 4,4,{VM_SIZE & 0xffff}
        b 0x44754
    """)
    identity = emit("vm_native_program_identity", """
        stw 3,0x79c(4)
        lwz 5,0x144(4)
        b 0x44540
    """)
    literal = emit("vm_literal_source_reference", """
        addc 4,4,3
        lwz 0,0x144(31)
        subf 0,0,4
        stw 0,0x7a0(31)
        stw 29,0x7a4(31)
        b 0x4375c
    """)
    replace(0x44750, f"b {allocation:#x}", "Allocate full u16 literal scratch without moving native locals")
    replace(0x4453C, f"b {identity:#x}", "Capture immutable native table identity for save references")
    replace(0x43758, f"b {literal:#x}", "Capture exact literal payload offset and byte count")
    replace(0x43744, "b 0x43758", "Retain the full u16 literal and advance VM over every encoded byte")
    for va, instruction in (
        (0x435D4, "addic 25,31,0x7b0"), (0x43790, "stb 30,0x7b0(3)"),
        (0x43F4C, "addic 3,30,0x7b0"), (0x43F70, "addic 27,30,0x7b0"),
        (0x43FD4, "stb 5,0x7b0(3)"), (0x44C3C, "addic 3,30,0x7b0"),
        (0x44C64, "addic 27,30,0x7b0"), (0x44CC4, "stb 5,0x7b0(4)"),
    ):
        replace(va, instruction, "Move every VM scratch-string producer/consumer away from native local variables")

    append = emit("bounded_save_literal_append", f"""
        stdu 1,-0xa0(1)
        mflr 0
        std 0,0xb0(1)
        std 28,0x80(1)
        std 29,0x88(1)
        std 30,0x90(1)
        std 31,0x98(1)
        mr 31,27
        lwz 30,0xf0(31)
        lwz 29,0(30)
        lwz 28,0xfc(31)
        cmplwi 29,{TRACE_CAPACITY}
        bgt append_invalid
        andi. 3,29,3
        bne append_invalid
        cmpwi 20,8
        blt append_inline
        lis 3,0x65
        lwz 3,0x2614(3)
        lwz 3,0x7c(3)
        addi 4,3,0x7b0
        cmpw 4,25
        bne append_inline
        lwz 4,0x7a4(3)
        cmpw 4,20
        bne append_inline
        lwz 12,0x79c(3)
        mr 5,12
        lis 4,0xf
        ori 4,4,0xe8b4
        subf 5,4,5
        srwi 5,5,4
        cmplwi 5,{SCENARIO_COUNT}
        bge append_invalid
        lwz 6,0x7a0(3)
        lis 4,0x20
        cmplw 6,4
        bge append_invalid
        cmpwi 6,3
        blt append_inline
        lwz 8,8(12)
        add 7,6,20
        cmplw 7,8
        bge append_inline
        lwz 7,0x144(3)
        add 7,7,6
        lbz 8,-3(7)
        cmpwi 8,10
        bne append_inline
        lbz 8,-2(7)
        lbz 9,-1(7)
        slwi 9,9,8
        or 8,8,9
        cmpw 8,20
        bne append_inline
        li 9,0
    append_compare_source:
        lbzx 10,25,9
        lbzx 11,7,9
        cmpw 10,11
        bne append_inline
        addi 9,9,1
        cmplw 9,20
        blt append_compare_source
        slwi 5,5,21
        or 5,5,6
        addi 4,29,8
        cmplwi 4,{TRACE_CAPACITY}
        bgt append_invalid
        add 28,28,29
        lis 3,0xff54
        ori 3,3,0x4852
        stw 3,0(28)
        stw 5,4(28)
        stw 4,0(30)
        b append_done
    append_inline:
        add 3,29,20
        addi 3,3,4
        rlwinm 3,3,0,0,29
        cmplwi 3,{TRACE_CAPACITY}
        bgt append_invalid
        mr 29,3
        lwz 3,0(30)
        add 3,28,3
        mr 4,25
        bl 0xd54dc
        stw 29,0(30)
        b append_done
    append_invalid:
        trap
    append_done:
        ld 28,0x80(1)
        ld 29,0x88(1)
        ld 30,0x90(1)
        ld 31,0x98(1)
        ld 0,0xb0(1)
        mtlr 0
        addi 1,1,0xa0
        b 0x6e1a4
    """)
    replace(0x6E14C, f"b {append:#x}", "Store bounded immutable literal references instead of overflowing live save flags")

    restore = emit("replay_saved_literal_references", f"""
        stdu 1,-0x120(1)
        mflr 0
        std 0,0x130(1)
        std 21,0xc8(1)
        std 22,0xd0(1)
        std 23,0xd8(1)
        std 24,0xe0(1)
        std 25,0xe8(1)
        std 26,0xf0(1)
        std 27,0xf8(1)
        std 28,0x100(1)
        std 29,0x108(1)
        std 30,0x110(1)
        li 30,0
        li 29,0
        li 24,0
        li 23,-1
    replay_next:
        lwz 3,0x80(31)
        lwz 4,0x128(3)
        cmplwi 4,{TRACE_CAPACITY}
        bgt replay_invalid
        andi. 5,4,3
        bne replay_invalid
        cmpw 30,4
        beq replay_done
        bgt replay_invalid
        add 3,3,30
        addi 28,3,0x12c
        mr 6,4
        lwz 4,0(28)
        lis 5,0xff54
        ori 5,5,0x4852
        cmpw 4,5
        bne replay_inline
        addi 5,30,8
        cmplw 5,6
        bgt replay_invalid
        lwz 22,4(28)
        srwi 21,22,21
        clrlwi 22,22,11
        cmplwi 21,{SCENARIO_COUNT}
        bge replay_invalid
        cmpw 21,23
        beq replay_cached
        cmpwi 24,0
        beq replay_allocate
        mr 3,24
        bl 0x63da0
    replay_allocate:
        lis 25,0xf
        ori 25,25,0xe8b4
        slwi 4,21,4
        add 25,25,4
        stw 25,0xa0(1)
        lwz 3,8(25)
        bl 0x63d70
        mr 24,3
        cmpwi 24,0
        beq replay_invalid
        lwz 4,4(25)
        lwz 5,8(25)
        lwz 6,12(25)
        bl 0x28d28
        mr 23,21
    replay_cached:
        lwz 25,0xa0(1)
        cmpwi 22,3
        blt replay_invalid
        lwz 5,8(25)
        cmplw 22,5
        bge replay_invalid
        add 28,24,22
        lbz 3,-3(28)
        cmpwi 3,10
        bne replay_invalid
        lbz 26,-2(28)
        lbz 3,-1(28)
        slwi 3,3,8
        or 26,26,3
        add 4,22,26
        cmplw 4,5
        bge replay_invalid
        li 3,0
        stbx 3,28,26
        li 25,8
        b replay_submit
    replay_inline:
        subf 5,30,6
        li 26,0
    replay_inline_length:
        cmplw 26,5
        bge replay_invalid
        lbzx 6,28,26
        cmpwi 6,0
        beq replay_inline_ready
        addi 26,26,1
        b replay_inline_length
    replay_inline_ready:
        addi 25,26,4
        rlwinm 25,25,0,0,29
        cmplw 25,5
        bgt replay_invalid
    replay_submit:
        add 29,29,26
        li 8,0
        cmpwi 27,0
        beq replay_scan
        cmpw 29,27
        blt replay_scan
        subf 8,27,29
        subf 8,8,26
    replay_scan:
        lwz 3,0x2b0(31)
        mr 4,28
        li 5,1
        li 6,0
        li 7,0
        bl 0x6df90
        mr 3,28
        li 4,0
        li 5,0
        bl 0x69b38
        add 30,30,25
        b replay_next
    replay_invalid:
        trap
    replay_done:
        cmpwi 24,0
        beq replay_return
        mr 3,24
        bl 0x63da0
    replay_return:
        lwz 3,0x80(31)
        ld 21,0xc8(1)
        ld 22,0xd0(1)
        ld 23,0xd8(1)
        ld 24,0xe0(1)
        ld 25,0xe8(1)
        ld 26,0xf0(1)
        ld 27,0xf8(1)
        ld 28,0x100(1)
        ld 29,0x108(1)
        ld 30,0x110(1)
        ld 0,0x130(1)
        mtlr 0
        addi 1,1,0x120
        b 0x5cc30
    """)
    replace(0x5CB5C, f"b {restore:#x}", "Replay old inline or full immutable literal save entries without 256-byte truncation")
    end = start + len(code)
    result[start:end] = code
    phoff = struct.unpack_from(">Q", result, 0x20)[0]
    struct.pack_into(">QQ", result, phoff + 0x20, end, end)
    report["rx_extension"].update(new_filesz=end, new_memsz=end, file_end=end,
                                  size=end - native_layout_patch.CAVE_START)
    report.update(input_sha256=project.digest(image), output_sha256=project.digest(result),
                  runtime_accepted=False, production_cutover=False)
    report["runtime_text"] = {
        "opacity_capacity": OPACITY_CAPACITY, "span_allocation": 0x15E0,
        "span_alpha": SPAN_ALPHA, "font_allocation": 0x264, "font_alpha": FONT_ALPHA,
        "vm_allocation": VM_SIZE, "vm_scratch": VM_SCRATCH, "vm_literal_capacity": 65536,
        "trace_capacity": TRACE_CAPACITY, "trace_tag": hex(TRACE_TAG),
        "trace_reference": "8 bytes: FF544852 plus native-index11/payload-offset21; inline legacy strings remain supported",
        "save_layout_size_unchanged": True, "save_entry_semantics_extended": True,
        "invalid_checkpoint_traps_without_writing_live_flags": True,
        "entries": {key: hex(value) for key, value in entries.items()},
        "displayed_text_shortened": False,
    }
    if not native_layout_patch.native_code_matches(bytes(result), bytes(result), report):
        raise ValueError("Runtime text correction fails its complete native write guard")
    return bytes(result), report
