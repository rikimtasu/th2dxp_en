"""Source-guarded glyph texel endpoints and word-aware native wrapping.

Extends the retained runtime-text template; never changes fonts, script bytes,
raw progress or installed files. Native controls remain scanner boundaries.
"""
from __future__ import annotations

import copy
import re
import struct
import textwrap

import native_layout_patch
import project


def apply(image, native):
    source = project.source_bytes()
    if native.get("typography") or not native.get("runtime_text"):
        raise ValueError("Typography needs the retained runtime-text correction exactly once")
    if not native_layout_patch.native_code_matches(image, image, native):
        raise ValueError("Typography input fails the complete native write guard")
    start = native["rx_extension"]["file_end"]
    if any(source[start:native_layout_patch.CAVE_END]) or any(image[start:native_layout_patch.CAVE_END]):
        raise ValueError("Typography requires original zero RX padding")
    result, code, report = bytearray(image), bytearray(), copy.deepcopy(native)
    assembler = native_layout_patch._assembler()
    entries = {}

    def assemble(body, address):
        lines, external, count = [], [], 0
        for line in textwrap.dedent(body).strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if re.fullmatch(r"(?:b|bl|beq|bne|bgt|bge|blt|ble)\s+(?:(?:cr[0-7]),\s*)?0x[0-9a-fA-F]+", line):
                external.append((count, line))
                lines.append("nop")
            else:
                lines.append(line)
            count += not line.endswith(":")
        blob = bytearray(assembler.asm("\n".join(lines), addr=address)[0])
        if len(blob) != count * 4:
            raise ValueError("Typography helper instruction expansion")
        for index, line in external:
            encoded = bytes(assembler.asm(line, addr=address + index * 4)[0])
            if len(encoded) != 4:
                raise ValueError("Typography external branch expansion")
            blob[index * 4:index * 4 + 4] = encoded
        return bytes(blob)

    def emit(name, body):
        address = start + 0x10000 + len(code)
        blob = assemble(body, address)
        if start + len(code) + len(blob) > native_layout_patch.CAVE_END:
            raise ValueError("Typography helpers exceed bounded RX padding")
        code.extend(blob)
        entries[name] = address
        report["injected_blocks"].append({"name": name, "va": hex(address), "size": len(blob),
                                           "sha256": project.digest(blob)})
        return address

    def hook(va, name, body):
        offset = va - 0x10000
        row = next((row for row in report["patches"] if int(row["va"], 0) == va), None)
        expected = bytes.fromhex(row["after"]) if row else source[offset:offset + 4]
        if image[offset:offset + 4] != expected:
            raise ValueError(f"Typography site {va:#x} differs from the reviewed input")
        target = emit(name, body)
        after = assemble(f"b {target:#x}", va)
        result[offset:offset + 4] = after
        if row is None:
            row = {"va": hex(va), "file_offset": hex(offset),
                   "source_before": source[offset:offset + 4].hex()}
            report["patches"].append(row)
        row.update(input_before=expected.hex(), after=after.hex(), purpose=name)

    # Queue rectangles are inclusive. The backend treated their final screen
    # coordinates and texels as edges, shrinking both extents by one. Convert
    # right/bottom before the existing transform; retain the queue/crop ABI.
    hook(0x1B580, "glyph_exclusive_screen_right", """
        vaddfp 11,11,3
        vmaddfp 11,7,11,8
        b 0x1b584
    """)
    hook(0x1B598, "glyph_exclusive_screen_bottom", """
        vaddfp 12,12,3
        vmaddfp 12,6,12,8
        b 0x1b59c
    """)
    hook(0x1B624, "glyph_exclusive_u_edge", """
        lhz 11,0(11)
        addi 11,11,1
        b 0x1b628
    """)
    hook(0x1B65C, "glyph_exclusive_v_edge", """
        lhz 9,0(9)
        addi 9,9,1
        b 0x1b660
    """)
    metric = next(int(block["va"], 0) for block in native["injected_blocks"]
                  if block["name"] == "selected_font_read_only_metric")
    bounds = next(int(block["va"], 0) for block in native["injected_blocks"]
                  if block["name"] == "bearing_aware_scalar_vector_bounds")
    save_gp = "\n".join(f"std {reg},{0x30 + 8 * (reg - 3):#x}(1)" for reg in range(3, 13))
    restore_gp = "\n".join(f"ld {reg},{0x30 + 8 * (reg - 3):#x}(1)" for reg in range(3, 13))
    save_fp = "\n".join(f"stfd {reg},{0xa0 + 8 * reg:#x}(1)" for reg in range(6))
    restore_fp = "\n".join(f"lfd {reg},{0xa0 + 8 * reg:#x}(1)" for reg in range(6))
    # The existing metric helper writes caller+4CC. Own that scratch explicitly;
    # a small leaf frame here would corrupt the scanner's locals above it.
    hook(0x6EA78, "word_boundary_before_overflow", f"""
        stdu 1,-0x600(1)
        std 0,0x28(1)
        mflr 0
        std 0,0x610(1)
        mfcr 0
        std 0,0x20(1)
        {save_gp}
        {save_fp}
        std 28,0x80(1)
        li 0,0x100
        stvx 28,1,0
        lis 8,0x65
        lbz 8,-0x6b(8)
        cmpwi 8,0
        bne word_finish
        li 0,0
        stw 0,0xd4(1)
        lfs 0,0xd4(1)
        fmuls 5,3,2
        fadds 5,5,31
        stfs 5,0xe0(1)
        fcmpu 0,5,0
        ble word_finish
        ld 8,0xac0(1)
        cmpw 28,8
        beq word_begin
        lbz 8,-1(28)
        cmpwi 8,0x20
        bne word_finish
    word_begin:
        stw 0,0xd4(1)
        lfs 3,0xd4(1)
        fmr 4,3
        fmr 5,3
    word_character:
        lbz 8,0(28)
        cmpwi 8,0x81
        beq word_quote
        cmpwi 8,0x21
        blt word_compare
        cmpwi 8,0x7e
        bgt word_compare
        cmpwi 8,0x5c
        beq word_compare
        cmpwi 8,0x3c
        beq word_compare
        cmpwi 8,0x3e
        beq word_compare
        cmpwi 8,0x2a
        beq word_compare
        bl {metric:#x}
        li 0,0xd0
        stvewx 28,1,0
        lwz 8,0xd0(1)
        extsw 8,8
        std 8,0xd8(1)
        lfd 1,0xd8(1)
        fcfid 1,1
        frsp 1,1
        lfs 2,0x4cc(1)
        li 9,1
        b word_measure
    word_quote:
        lbz 8,1(28)
        cmpwi 8,0x65
        blt word_compare
        cmpwi 8,0x68
        bgt word_compare
        lfs 1,0x94(27)
        fmr 2,1
        li 9,2
    word_measure:
        fadds 2,3,2
        fcmpu 0,2,4
        ble word_keep_bound
        fmr 4,2
    word_keep_bound:
        fadds 3,3,1
        lfs 0,0xa4(27)
        lfs 1,0x84(27)
        fmuls 0,0,1
        fmuls 5,4,0
        lfs 1,0x44(27)
        fcmpu 0,5,1
        bge word_finish
        add 28,28,9
        b word_character
    word_compare:
        lfs 0,0xd4(1)
        fcmpu 0,4,0
        ble word_finish
        lfs 0,0xe0(1)
        fadds 0,0,5
        lfs 1,0x44(27)
        fcmpu 0,0,1
        blt word_finish
        stfs 4,0xacc(1)
    word_finish:
        ld 0,0x20(1)
        mtcrf 255,0
        li 0,0x100
        lvx 28,1,0
        ld 28,0x80(1)
        {restore_fp}
        {restore_gp}
        ld 0,0x610(1)
        mtlr 0
        ld 0,0x28(1)
        addi 1,1,0x600
        b {bounds:#x}
    """)
    end = start + len(code)
    result[start:end] = code
    phoff = struct.unpack_from(">Q", result, 0x20)[0]
    struct.pack_into(">QQ", result, phoff + 0x20, end, end)
    report["rx_extension"].update(new_filesz=end, new_memsz=end, file_end=end,
                                  size=end - native_layout_patch.CAVE_START)
    report.update(input_sha256=project.digest(image), output_sha256=project.digest(result),
                  runtime_accepted=False, production_cutover=False)
    report["typography"] = {
        "glyph_queue_inclusive_protocol_preserved": True,
        "glyph_backend_converts_uv_to_exclusive_edges": True,
        "glyph_backend_converts_screen_to_exclusive_edges": True,
        "word_wrapping": "Printable ASCII runs, apostrophes/hyphens and CP932 quotation marks; native controls remain boundaries",
        "overlong_words": "Original character wrapping, without shortening or an empty-line retry loop",
        "text_font_assets_and_raw_progress_unchanged": True,
        "entries": {name: hex(value) for name, value in entries.items()},
    }
    if not native_layout_patch.native_code_matches(bytes(result), bytes(result), report):
        raise ValueError("Typography correction fails complete native write guard")
    return bytes(result), report
