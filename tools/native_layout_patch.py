"""Source-pinned original-font VWF diagnostic correction; never a production cutover.

Geometry-only VMX counters use original glyph design pixels. Integer VM/text
byte counts, original glyph drawing, control dispatch and Japanese full cells
are retained. A per-span width cache serves every independent flower endpoint.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys

import project

SOURCE_SHA256 = "8d8bc60d2b02d12f509a9a3ee9c126876ac8524d4f02c7871206aca9bd66e828"
CAVE_START = 0x10E3E8
CAVE_END = 0x110000
VA_BIAS = 0x10000


def _assembler():
    dependency = project.ROOT / "work/tool-cache/keystone-0.9.2"
    if str(dependency) not in sys.path:
        sys.path.insert(0, str(dependency))
    try:
        import keystone
    except ImportError as error:
        raise ValueError("Pinned work-local Keystone0.9.2 is required; no global dependency is installed") from error
    if keystone.__version__ != "0.9.2":
        raise ValueError("Unexpected Keystone version")
    return keystone.Ks(keystone.KS_ARCH_PPC,
                       keystone.KS_MODE_PPC64 | keystone.KS_MODE_BIG_ENDIAN)


def apply(image: bytes) -> tuple[bytes, dict]:
    """Apply the complete diagnostic to a source-derived image, including growth.

    Existing scenario/arena modifications are preserved. Native sites and RX
    mapping must still be source-identical, except the reviewed terminal branch
    may already be applied. No original/source/install file is written here.
    """
    source = project.source_bytes()
    if project.digest(source) != SOURCE_SHA256:
        raise ValueError("Native layout correction is pinned to another source")
    if len(image) < len(source):
        raise ValueError("Source-derived image is truncated")
    result = bytearray(image)
    phoff = struct.unpack_from(">Q", source, 0x20)[0]
    phsize, phcount = struct.unpack_from(">HH", source, 0x36)
    if phsize != 56 or phcount != 8:
        raise ValueError("Unexpected ELF program-header table")
    original_rx = struct.unpack_from(">IIQQQQQQ", source, phoff)
    current_rx = struct.unpack_from(">IIQQQQQQ", result, phoff)
    if (current_rx != original_rx or original_rx[0] != 1 or
            original_rx[2:4] != (0, VA_BIAS) or
            original_rx[5:7] != (CAVE_START, CAVE_START) or
            original_rx[1] & 5 != 5):
        raise ValueError("RX mapping is not the reviewed original PT_LOAD0")
    if any(source[CAVE_START:CAVE_END]) or any(result[CAVE_START:CAVE_END]):
        raise ValueError("The bounded, currently unmapped RX extension is not zero padding")
    ks = _assembler()
    code = bytearray()
    patches = []
    blocks = []

    def assemble(text, address):
        encoded, _ = ks.asm(text, addr=address)
        if not encoded:
            raise ValueError(f"Assembler emitted no instructions at {address:#x}")
        return bytes(encoded)

    def emit(name, text):
        address = VA_BIAS + CAVE_START + len(code)
        blob = text if isinstance(text, bytes) else assemble(text, address)
        if len(blob) % 4 or CAVE_START + len(code) + len(blob) > CAVE_END:
            raise ValueError("Native helper exceeds its verified bounded RX extension")
        code.extend(blob)
        blocks.append({"name": name, "va": hex(address), "size": len(blob),
                       "sha256": project.digest(blob)})
        return address

    def replace(va, instruction, purpose, allowed=None):
        offset = va - VA_BIAS
        before = source[offset:offset + 4]
        observed = bytes(result[offset:offset + 4])
        if observed != before and observed not in (allowed or ()):
            raise ValueError(f"Native site {va:#x} is not the pinned original instruction")
        after = assemble(instruction, va) if isinstance(instruction, str) else instruction
        if len(after) != 4:
            raise ValueError(f"Patch at {va:#x} is not one instruction")
        result[offset:offset + 4] = after
        patches.append({"va": hex(va), "file_offset": hex(offset),
                        "source_before": before.hex(), "input_before": observed.hex(),
                        "after": after.hex(), "purpose": purpose})

    def hook(va, name, body, continuation):
        target = emit(name, body + f"\nb {continuation:#x}")
        replace(va, f"b {target:#x}", name)

    # Only this helper accesses metrics. It mirrors the selected font's source
    # lookup without executing 1D538's first-use global fallback write. All live
    # scalar registers/CR and F0/F1 are restored; output is geometry V28 and the
    # candidate ink reservation in the scanner frame's unused aligned +4CC slot.
    # Scanner source accesses +4C8 as a byte and next accesses +4D0 as a doubleword;
    # +4CC does not alias a source local, save area, or substitution buffer.
    # Source startup calls 1D504 at 11828/118D0/11964/119F8 with R7=46
    # for all four context fonts. Thus predicting first-use fallback is stable
    # across queued font switches without moving the original cache write.
    metric = emit("selected_font_read_only_metric", """
        stdu 1,-0x100(1)
        std 3,0x20(1)
        std 4,0x28(1)
        std 5,0x30(1)
        std 6,0x38(1)
        std 7,0x40(1)
        std 8,0x48(1)
        std 9,0x50(1)
        std 10,0x58(1)
        std 11,0x60(1)
        std 12,0x68(1)
        mflr 0
        std 0,0x70(1)
        mfcr 0
        std 0,0x78(1)
        stfd 0,0x80(1)
        stfd 1,0x88(1)
        lbz 3,0(28)
        cmpwi 3,0
        beq metric_nul
        lwz 5,0x10c(27)
        lwz 6,0xdc(27)
        sldi 6,6,2
        lwzx 5,5,6
        cmpwi 3,0x20
        blt metric_raw_code
        cmpwi 3,0x7e
        bgt metric_raw_code
        addi 4,3,-0x20
        sldi 4,4,1
        lis 6,0x26
        addi 6,6,0x14b0
        lhzx 4,6,4
        b metric_ranges
    metric_raw_code:
        slwi 4,3,8
        lbz 6,1(28)
        or 4,4,6
    metric_ranges:
        lwz 6,0(5)
        li 7,0
        li 12,0
    metric_range_loop:
        lhz 8,0(6)
        cmpwi 8,0
        beq metric_index_ready
        cmpw 4,8
        blt metric_range_next
        lhz 9,2(6)
        cmpw 4,9
        bgt metric_range_next
        subf 12,8,4
        add 12,12,7
        clrlwi 12,12,16
        b metric_index_ready
    metric_range_next:
        lhz 9,2(6)
        subf 10,8,9
        add 7,7,10
        addi 7,7,1
        addi 6,6,4
        b metric_range_loop
    metric_index_ready:
        lwz 11,0x7c(5)
        cmpwi 11,0
        beq metric_fallback
        li 6,1
        sldi 12,12,1
        add 11,11,12
        lbz 8,0(11)
        lbz 9,1(11)
        b metric_width
    metric_fallback:
        li 6,0
        lis 11,0x65
        lbz 10,0x7eb0(11)
        lis 11,0x26
        addi 11,11,0x157c
        lbz 8,0(11)
        cmpwi 10,0
        beq metric_predict_first_fallback
        lbz 9,1(11)
        b metric_width
    metric_predict_first_fallback:
        lwz 9,0x8c(5)
        clrlwi 9,9,24
    metric_width:
        addi 12,9,6
        addi 4,9,3
        cmpwi 6,0
        bne metric_bound_ready
        lwz 10,0x88(5)
        addi 10,10,3
        subf 10,8,10
        cmpw 4,10
        bge metric_bound_ready
        mr 4,10
    metric_bound_ready:
        extsw 4,4
        std 4,0x98(1)
        lfd 0,0x98(1)
        fcfid 0,0
        frsp 0,0
        lfs 1,0x94(27)
        fcmpu 0,0,1
        bge metric_store_bound
        fmr 0,1
    metric_store_bound:
        stfs 0,0x5cc(1)
        b metric_output
    metric_nul:
        li 12,0
    metric_output:
        stw 12,0x90(1)
        li 0,0x90
        lvewx 28,1,0
        vspltw 28,28,0
        lfd 0,0x80(1)
        lfd 1,0x88(1)
        ld 0,0x78(1)
        mtcrf 255,0
        ld 0,0x70(1)
        mtlr 0
        ld 3,0x20(1)
        ld 4,0x28(1)
        ld 5,0x30(1)
        ld 6,0x38(1)
        ld 7,0x40(1)
        ld 8,0x48(1)
        ld 9,0x50(1)
        ld 10,0x58(1)
        ld 11,0x60(1)
        ld 12,0x68(1)
        addi 1,1,0x100
        blr
    """)

    # R0, F0 and V0 are not live original values at these scanner sites. F0/V0
    # subsequently hold freshly loaded scale for the common geometry phase;
    # no original external call intervenes before their last use at 6ED6C.
    hook(0x6E1F0, "default_design_pixel_unit", """
        vspltisw 28,12
        vspltisw 0,1
        vslw 28,28,0
        lfs 0,0x94(27)
        stfs 0,0x4cc(1)
    """, 0x6E1F4)
    for va, register, mantissa, shift in (
        (0x6E1FC,28,12,2), (0x6E3EC,5,12,2), (0x6E414,5,12,2),
        (0x6E43C,5,12,2), (0x6E518,5,12,2),
        (0x6E4EC,5,9,4), (0x6E9C0,5,12,1),
    ):
        hook(va, f"geometry_literal_{va:x}",
             f"vspltisw {register},{mantissa}\nvspltisw 0,{shift}\nvslw {register},{register},0", va + 4)

    ordinary = emit("ordinary_ascii_metric_and_terminal", f"""
        cmpwi 3,0x2a
        beq ordinary_star
        bl {metric:#x}
        b 0x6e318
    ordinary_star:
        b 0x6e63c
    """)
    replace(0x6E638, f"b {ordinary:#x}", "Measure ordinary ASCII after angle dispatch; retain star dispatch")
    literal = emit("literal_right_angle_metric_and_terminal", f"""
        bne literal_active_command
        bl {metric:#x}
        b 0x6e318
    literal_active_command:
        b 0x6e5a8
    """)
    replace(0x6E5A4, f"b {literal:#x}", "Measure literal > without changing active command close")
    hook(0x6E824, "unknown_asterisk_geometry_skip_edge", f"""
        bl {metric:#x}
        vsldoi 27,28,28,0
    """, 0x6F08C)
    replace(0x6E64C, bytes.fromhex("4082fccc"), "Retain reviewed terminal restoration", [bytes.fromhex("4082fccc")])

    replace(0x6E3A8, "vaddfp 2,5,5", "Newline weighted pixel probe retains native final half and X placement")
    # Cell lvlx V0,R27,R0: unlike lvewx this loads from the unaligned EA into
    # lane0. Preserve the real Cell instruction, not an aligned-down lvx.
    lvlx_v0_ctx_r0 = struct.pack(">I", (31 << 26) | (27 << 16) | (519 << 1))
    before_address = VA_BIAS + CAVE_START + len(code)
    before_blob = assemble("li 0,0xa4", before_address) + lvlx_v0_ctx_r0
    before_blob += assemble("""
        lfs 0,0xa4(27)
        li 0,0x4e8
        stvewx 9,1,0
        lfs 3,0x4e8(1)
        vmaddfp 7,0,9,7
        b 0x6ea60
    """, before_address + len(before_blob))
    before = emit("weighted_scalar_vector_before", before_blob)
    replace(0x6EA5C, f"b {before:#x}", "Feed scalar and vector bounds from identical weighted before count")
    replace(0x6EA6C, "fmuls 3,0,3", "Weighted scalar before uses glyph scale only")
    hook(0x6EA78, "bearing_aware_scalar_vector_bounds", """
        lfs 4,0x4cc(1)
        fmuls 4,4,0
        fmuls 4,4,2
        lfs 5,0x44(27)
        fsubs 4,5,4
        stfs 4,0x4e8(1)
        li 0,0x4e8
        lvewx 9,1,0
        vspltw 9,9,2
    """, 0x6EA7C)
    replace(0x6EA84, "vaddfp 10,10,2", "Remove local byte halfcell factor from weighted vector bound")
    replace(0x6EA88, "fadds 2,2,31", "Remove local byte halfcell factor from weighted scalar bound")
    hook(0x6EC4C, "weighted_visible_scalar_count", """
        li 0,0x4e8
        stvewx 31,1,0
        lfs 25,0x4e8(1)
    """, 0x6EC50)
    for va, instruction, purpose in (
        (0x6ED5C,"fmuls 30,0,25","weighted candidate scalar advance"),
        (0x6ED6C,"vmaddfp 6,0,31,3","weighted candidate vector advance"),
        (0x6ED74,"fadds 30,30,31","weighted candidate scalar endpoint"),
        (0x6ED78,"vaddfp 6,6,2","weighted candidate vector endpoint"),
        (0x6EF34,"vsldoi 2,5,5,0","newline commit glyph scale"),
        (0x6EF50,"fmr 1,2","newline scalar glyph scale"),
        (0x6EF60,"vaddfp 31,31,28","newline vector endpoint"),
        (0x6EF64,"fadds 30,30,31","newline scalar endpoint"),
        (0x6F018,"vsldoi 2,5,5,0","normal commit glyph scale"),
        (0x6F028,"fmr 1,2","normal scalar glyph scale"),
        (0x6F034,"fadds 31,1,31","normal scalar endpoint"),
        (0x6F038,"vaddfp 31,31,28","normal vector endpoint"),
    ):
        replace(va,instruction,purpose)

    replace(0x6DA14,"li 3,0x14d0","Extend span allocation for cached design-pixel width")
    for va in (0x6EE78,0x6EEC0):
        hook(va,f"cache_span_width_{va:x}","""
            cmpwi 3,0
            beq cache_no_node
            li 0,0x14cc
            stvewx 31,3,0
        cache_no_node:
            ori 4,3,0
        """,va+4)

    hook(0x70534,"wait_flower_actual_span_width","""
        lfs 10,0x14cc(30)
        lfs 0,0x84(30)
        fmuls 10,10,0
        lfs 0,0x84(31)
        fmuls 10,10,0
        lfs 11,0x520(31)
        fadds 1,10,11
        stfs 1,0x520(31)
    """,0x7054C)
    hook(0x70630,"final_flower_actual_span_width","""
        fmr 10,1
        fmuls 1,7,8
        lfs 8,0x14cc(30)
        lfs 0,0x84(30)
        fmuls 8,8,0
        lfs 0,0x84(31)
        fmuls 8,8,0
        lfs 7,0x64(30)
        fadds 7,8,7
        stfs 7,0x520(31)
    """,0x7064C)
    hook(0x706CC,"completed_flower_actual_span_width","""
        lfs 2,0x14cc(30)
        lfs 0,0x84(30)
        fmuls 2,2,0
        lfs 0,0x84(31)
        fmuls 2,2,0
        lfs 3,0x64(30)
        fadds 1,2,3
        stfs 1,0x520(31)
    """,0x706E4)
    hook(0x6F988,"reposition_all_actual_span_width","""
        lfs 7,0x14cc(3)
        lfs 0,0x84(3)
        fmuls 7,7,0
        lfs 0,0x84(31)
        fmuls 7,7,0
        lfs 5,0x34(31)
        lfs 8,0x44(31)
        lfs 1,0x78(3)
        lfs 3,0x74(3)
        lwz 3,0x530(31)
        fadds 4,7,4
    """,0x6F9BC)

    end = CAVE_START + len(code)
    if end > CAVE_END:
        raise ValueError("Complete native layout correction exceeds bounded injection region")
    for index in range(1,phcount):
        header = struct.unpack_from(">IIQQQQQQ",result,phoff+index*phsize)
        if header[0] == 1 and header[6] and VA_BIAS < header[3]+header[6] and header[3] < VA_BIAS+end:
            raise ValueError("RX extension overlaps another mapped PT_LOAD")
    result[CAVE_START:end] = code
    struct.pack_into(">QQ",result,phoff+0x20,end,end)
    report = {"source_sha256":SOURCE_SHA256,"input_sha256":project.digest(image),
              "output_sha256":project.digest(result),"diagnostic_only":True,
              "original_glyph_drawing_unchanged":True,"fonts_unchanged":True,
              "raw_vm_byte_counts_unchanged":True,"global_half_constant_unchanged":True,
              "geometry_counter_unit":"original-font design pixels",
              "span_allocation":{"old":0x14CC,"new":0x14D0,"width_field":0x14CC},
              "fallback_initialization":{"font_count":4,"default_width_each":46,
                                         "setter_calls":["0x11828","0x118D0","0x11964","0x119F8"],
                                         "source_cache_writes_moved":False},
              "scanner_candidate_ink_slot":"existing unused aligned stack+0x4CC; scanner frame unchanged",
              "rx_extension":{"program_header":0,"old_filesz":CAVE_START,"new_filesz":end,
                              "old_memsz":CAVE_START,"new_memsz":end,"file_begin":CAVE_START,
                              "file_end":end,"va_begin":VA_BIAS+CAVE_START,"size":len(code)},
              "patches":patches,"injected_blocks":blocks,
              "runtime_accepted":False,"production_cutover":False}
    return bytes(result),report


def ui_data_site(offset):
    """Four-byte UI pointer words or the exact 13-cell footer geometry table."""
    return offset % 4 == 0 and (
        0x642000 <= offset <= 0x647C48 or 0x64112C <= offset <= 0x641178)


def native_code_matches(image: bytes, staged: bytes, report: dict) -> bool:
    """Compare the complete staged native correction, not just terminal flush.

    Scenario data may differ. The reference image/report must identify the
    actual source-pinned diagnostic; its RX header, every patched site and the
    entire injected block must match the candidate. No assembly is performed.
    """
    try:
        if (report["source_sha256"] != SOURCE_SHA256 or
                project.digest(staged) != report["output_sha256"]):
            return False
        extension = report["rx_extension"]
        begin, end = extension["file_begin"], extension["file_end"]
        if begin != CAVE_START or not begin < end <= CAVE_END:
            return False
        phoff = struct.unpack_from(">Q", staged, 0x20)[0]
        phsize, phcount = struct.unpack_from(">HH", staged, 0x36)
        if phsize != 56 or phcount != 8 or not report["patches"]:
            return False
        if image[:0x40] != staged[:0x40]:
            return False
        for index in range(phcount):
            if index == 3:  # Only the reviewed empty RW slot may change.
                continue
            offset = phoff + index * phsize
            if image[offset:offset + phsize] != staged[offset:offset + phsize]:
                return False
        if image[begin:end] != staged[begin:end]:
            return False
        for patch in report["patches"]:
            offset = int(patch["file_offset"], 0)
            expected = bytes.fromhex(patch["after"])
            if (len(expected) != 4 or not 0 <= offset < CAVE_START or
                    staged[offset:offset + 4] != expected or
                    image[offset:offset + 4] != expected):
                return False
        data_sites = set()
        for patch in report.get("data_patches", []):
            offset = int(patch["file_offset"], 0)
            expected = bytes.fromhex(patch["after"])
            if (offset in data_sites or not ui_data_site(offset)
                    or len(expected) != 4 or staged[offset:offset + 4] != expected
                    or image[offset:offset + 4] != expected):
                return False
            data_sites.add(offset)
        latin = report.get("latin_font")
        if latin:
            import native_latin_font_patch
            if not native_latin_font_patch.manifest_matches(latin):
                return False
            for patch in latin["patches"]:
                offset = int(patch["file_offset"], 0)
                expected = bytes.fromhex(patch["after"])
                if (offset in data_sites or staged[offset:offset + 2] != expected
                        or image[offset:offset + 2] != expected):
                    return False
        ui = report.get("ui_strings")
        if data_sites and not ui:
            return False
        if report.get("supplemental_code") and not ui:
            return False
        if ui:
            offset, address, size = ui["file_offset"], ui["virtual_address"], ui["file_size"]
            header = struct.unpack_from(">IIQQQQQQ", image, phoff + 2 * phsize)
            if (ui["program_header_index"] != 2 or offset < 6596336 or offset % 0x10000
                    or address % 0x10000 or not 0 < size <= 0x10000
                    or offset + size > len(image) or address + size > 0x80000000
                    or ui.get("flags") not in (4, 5)
                    or header != (1, ui["flags"], offset, address, address, size, size, 0x10000)
                    or len(ui["records"]) != 142 or ui["translated_records"] != 142
                    or project.digest(staged[offset:offset + size]) != ui["sha256"]
                    or image[offset:offset + size] != staged[offset:offset + size]):
                return False
            supplemental = report.get("supplemental_code", [])
            if (ui["flags"] == 5) != bool(supplemental):
                return False
            code_end = offset
            for block in supplemental:
                code_offset, code_size = block["file_offset"], block["size"]
                if (not code_end <= code_offset < code_offset + code_size <= offset + size
                        or block["virtual_address"] != address + code_offset - offset
                        or code_offset % 4 or code_size % 4
                        or project.digest(staged[code_offset:code_offset + code_size]) != block["sha256"]):
                    return False
                code_end = code_offset + code_size
            for index in range(phcount):
                other = struct.unpack_from(">IIQQQQQQ", image, phoff + index * phsize)
                if (index != 2 and other[0] == 1 and other[6]
                        and address < other[3] + other[6] and other[3] < address + size):
                    return False
        return True
    except (KeyError, TypeError, ValueError, struct.error):
        return False
