"""Pinned, diagnostic-only save/load caption Latin geometry correction.

The list does not call the dialogue renderer: A1660 -> A0470 -> A0EE4 /
A0F14 -> 1BE28 -> 1BCB8. 1BE28 deliberately advances every Latin glyph by
round(font.default_width * scale); its main-font cell/default are 48/46.
The caption's scale is 0.54545456, hence a 25-pixel advance even for 'i'.

Only these two caption calls use a private relocated copy of 1BE28. Its
ASCII path borrows the bearing/advance arithmetic of native 1C178, using
the very same font+7C metrics and glyph index already resolved by 1BE28.
Japanese, special Japanese punctuation, glyph construction, font objects,
other UI, dialogue, backlog, and serialized caption bytes remain untouched.
"""
from __future__ import annotations

import struct

import native_layout_patch
import project

SOURCE_SHA256 = native_layout_patch.SOURCE_SHA256
INPUT_SHA256 = "d7d9c1decc82b9fa05d5bc3f317c6d0741363c7c53cca5bff22940782b017d86"
VA_BIAS = 0x10000
CAVE_START = 0x10E7B8
CAVE_END = 0x110000
DRAW_BEGIN = 0x1BE28
DRAW_END = 0x1C170
CAPTION_SITES = (0xA0EE4, 0xA0F14)


def apply(image: bytes) -> tuple[bytes, dict]:
    """Return a new diagnostic image and replay metadata; never write an ELF.

    Accept only the reviewed VWF+growth candidate, preserving its old helpers
    and appended scenario segment. This is intentionally not a bulk builder.
    """
    source = project.source_bytes()
    if project.digest(source) != SOURCE_SHA256:
        raise ValueError("Save preview correction requires the pinned original source")
    if project.digest(image) != INPUT_SHA256:
        raise ValueError("Save preview correction requires the reviewed VWF+growth candidate")
    phoff = struct.unpack_from(">Q", source, 0x20)[0]
    phsize, phcount = struct.unpack_from(">HH", source, 0x36)
    if (phoff != 0x40 or phsize != 56 or phcount != 8 or
            image[0x20:0x28] != source[0x20:0x28] or
            image[0x36:0x3A] != source[0x36:0x3A]):
        raise ValueError("Unexpected ELF program-header table")
    original_rx = struct.unpack_from(">IIQQQQQQ", source, phoff)
    current_rx = struct.unpack_from(">IIQQQQQQ", image, phoff)
    expected_rx = list(original_rx)
    expected_rx[5:7] = (CAVE_START, CAVE_START)
    if (current_rx != tuple(expected_rx) or current_rx[0] != 1 or
            current_rx[2:5] != (0, VA_BIAS, VA_BIAS) or
            current_rx[1] & 7 != 5):
        raise ValueError("RX mapping is not the reviewed VWF extension")
    if len(image) < CAVE_END or any(source[CAVE_START:CAVE_END]) or any(image[CAVE_START:CAVE_END]):
        raise ValueError("Save preview cave is not bounded zero RX padding")

    # Guard the whole affected source path, not just the overwritten branches.
    ranges = ((0xA1660, 0xA1C9C), (0xA0470, 0xA1334),
              (DRAW_BEGIN, DRAW_END), (0x1BCB8, 0x1BE24),
              (0x1C178, 0x1C5B0), (0x6F664, 0x6F884))
    source_ranges = []
    for begin, end in ranges:
        blob = source[begin - VA_BIAS:end - VA_BIAS]
        if image[begin - VA_BIAS:end - VA_BIAS] != blob:
            raise ValueError(f"Save preview source range changed at {begin:#x}")
        source_ranges.append({"va_begin": hex(begin), "va_end": hex(end),
                              "sha256": project.digest(blob)})

    result = bytearray(image)
    ks = native_layout_patch._assembler()
    code = bytearray()
    blocks = []
    patches = []

    def assemble(text: str, va: int) -> bytes:
        encoded, _ = ks.asm(text, addr=va)
        if not encoded or len(encoded) % 4:
            raise ValueError(f"Invalid save preview helper at {va:#x}")
        return bytes(encoded)

    def emit(name: str, blob: bytes) -> int:
        va = VA_BIAS + CAVE_START + len(code)
        if not blob or len(blob) % 4 or CAVE_START + len(code) + len(blob) > CAVE_END:
            raise ValueError("Save preview helper exceeds bounded RX padding")
        code.extend(blob)
        blocks.append({"name": name, "va": hex(va), "size": len(blob),
                       "sha256": project.digest(blob)})
        return va

    def replace(va: int, text: str, purpose: str) -> None:
        offset = va - VA_BIAS
        before = source[offset:offset + 4]
        if image[offset:offset + 4] != before:
            raise ValueError(f"Save preview site changed at {va:#x}")
        after = assemble(text, va)
        if len(after) != 4:
            raise ValueError("Save preview source site is not one instruction")
        result[offset:offset + 4] = after
        patches.append({"va": hex(va), "file_offset": hex(offset),
                        "source_before": before.hex(), "input_before": before.hex(),
                        "after": after.hex(), "purpose": purpose})

    clone_va = VA_BIAS + CAVE_START
    clone = bytearray(source[DRAW_BEGIN - VA_BIAS:DRAW_END - VA_BIAS])
    # Internal PC-relative branches retain their exact displacement. Only the
    # two external BLs change displacement; reject any unreviewed branch shape.
    relocated_calls = []
    for offset in range(0, len(clone), 4):
        word = struct.unpack_from(">I", clone, offset)[0]
        opcode = word >> 26
        if opcode not in (16, 18):
            continue
        bits = 26 if opcode == 18 else 16
        mask = 0x03FFFFFC if opcode == 18 else 0xFFFC
        displacement = word & mask
        if displacement & (1 << (bits - 1)):
            displacement -= 1 << bits
        old_va = DRAW_BEGIN + offset
        if word & 2:
            raise ValueError("Unexpected absolute branch in native caption draw")
        target = old_va + displacement
        if DRAW_BEGIN <= target < DRAW_END:
            continue
        if opcode != 18 or word & 1 != 1 or target != 0x1BCB8:
            raise ValueError(f"Unexpected external caption branch at {old_va:#x}")
        clone[offset:offset + 4] = assemble(f"bl {target:#x}", clone_va + offset)
        relocated_calls.append({"source_va": hex(old_va),
                                "clone_va": hex(clone_va + offset), "target": hex(target)})
    if len(relocated_calls) != 2:
        raise ValueError("Native caption renderer does not have its two glyph calls")

    ascii_va = clone_va + len(clone)
    metric_va = ascii_va + 8
    # The native frame uses +80..87 as FP scratch and saves R20 at +98.
    # +88..8B holds the original horizontal scale; +8C..8F the next cursor.
    # 1BE3C's zero R6 is dead: both ASCII and Japanese paths define R6 before
    # reading it. Preserve every other instruction of the native fixed loop.
    for old_va, text in ((0x1BE3C, "stfs 2,0x88(1)"),
                         (0x1C004, f"b {ascii_va:#x}"),
                         (0x1C02C, "lwz 26,0x8c(1)")):
        offset = old_va - DRAW_BEGIN
        clone[offset:offset + 4] = assemble(text, clone_va + offset)
    emit("caption_fixed_renderer_with_latin_metrics", bytes(clone))

    emit("caption_ascii_geometry_entry", assemble(
        f"bl {metric_va:#x}\nb {clone_va + 0x1C008 - DRAW_BEGIN:#x}", ascii_va))
    # The draw clone and linear bound pass share exactly the same calculation.
    # Only volatile scalar/FP scratch and CR0 change; no carry-setting operation.
    ascii_code = assemble("""
        lwz 3,0x7c(31)
        li 4,0
        lwz 5,0x8c(31)
        cmpwi 3,0
        beq caption_metrics_ready
        slwi 7,6,1
        add 3,3,7
        lbz 4,0(3)
        lbz 5,1(3)
    caption_metrics_ready:
        lwz 7,0x88(31)
        lwz 8,0x8c(31)
        subf 7,8,7
        add 5,5,4
        add 5,5,7
        std 4,0x80(1)
        lfd 4,0x80(1)
        fcfid 4,4
        frsp 4,4
        lfs 2,0x88(1)
        lis 3,2
        lfs 3,-0x41dc(3)
        fmadds 4,4,2,3
        fctiwz 4,4
        stfd 4,0x80(1)
        lwz 4,0x84(1)
        subf 4,4,26
        extsw 5,5
        std 5,0x80(1)
        lfd 4,0x80(1)
        fcfid 4,4
        frsp 4,4
        fmadds 4,4,2,3
        fctiwz 4,4
        stfd 4,0x80(1)
        lwz 5,0x84(1)
        add 5,4,5
        stw 5,0x8c(1)
        extsh 4,4
        blr
    """, metric_va)
    emit("caption_ascii_metric_geometry", ascii_code)

    bound_va = VA_BIAS + CAVE_START + len(code)
    # A0650/A0668/A0670 and A0708/A0720/A0728 describe both nine-slice
    # borders: X=209,273,1010,1030. Use 1010 as a conservative content edge,
    # not a claim about GPU clipping. The second text pass starts at X=421.
    # Walk complete native characters once; remember the last prefix that also
    # fits the original CP932 ellipsis. Bound full quads, including cell overhang.
    bound_code = assemble(f"""
        stb 20,0x138(1)
        stdu 1,-0x180(1)
        std 0,0xa0(1)
        std 3,0xa8(1)
        std 4,0xb0(1)
        std 5,0xb8(1)
        std 6,0xc0(1)
        std 7,0xc8(1)
        std 8,0xd0(1)
        std 9,0xd8(1)
        std 10,0xe0(1)
        std 11,0xe8(1)
        std 12,0xf0(1)
        std 26,0x100(1)
        std 27,0x108(1)
        std 31,0x110(1)
        mflr 0
        std 0,0x118(1)
        mfcr 0
        std 0,0x120(1)
        stfd 0,0x130(1)
        mffs 0
        stfd 0,0x138(1)
        stfd 2,0x140(1)
        stfd 3,0x148(1)
        stfd 4,0x150(1)
        lis 31,0x25
        lwz 31,0x7028(31)
        lwz 31,0x50(31)
        lis 3,0xa
        lfs 2,0x468(3)
        stfs 2,0x88(1)
        lis 3,2
        lfs 3,-0x41dc(3)
        lwz 4,0x88(31)
        std 4,0x80(1)
        lfd 4,0x80(1)
        fcfid 4,4
        frsp 4,4
        fmadds 4,4,2,3
        fctiwz 4,4
        stfd 4,0x80(1)
        lwz 4,0x84(1)
        stw 4,0x90(1)
        lwz 4,0x8c(31)
        std 4,0x80(1)
        lfd 4,0x80(1)
        fcfid 4,4
        frsp 4,4
        fmadds 4,4,2,3
        fctiwz 4,4
        stfd 4,0x80(1)
        lwz 4,0x84(1)
        stw 4,0x94(1)
        addi 27,1,0x298
        addi 9,27,0x20
        mr 10,27
        li 26,0
        li 12,0
    caption_bound_loop:
        cmplw 27,9
        bge caption_bound_done
        lbz 3,0(27)
        cmpwi 3,0
        beq caption_bound_done
        li 11,1
        cmpwi 3,0x20
        blt caption_bound_control
        cmpwi 3,0x7e
        ble caption_bound_ascii
        cmpwi 3,0x80
        blt caption_bound_skip
        cmpwi 3,0x9f
        ble caption_bound_pair
        cmpwi 3,0xe0
        blt caption_bound_skip
    caption_bound_pair:
        lbz 4,1(27)
        cmpwi 4,0
        beq caption_bound_incomplete
        slwi 3,3,8
        or 3,3,4
        li 11,2
        b caption_bound_lookup
    caption_bound_ascii:
        addi 3,3,-0x20
        slwi 3,3,1
        lis 4,0x26
        addi 4,4,0x14b0
        lhzx 3,4,3
    caption_bound_lookup:
        lwz 4,0(31)
        li 8,0
        li 6,0
    caption_bound_range:
        lhz 5,0(4)
        cmpwi 5,0
        beq caption_bound_index
        cmpw 3,5
        blt caption_bound_range_next
        lhz 7,2(4)
        cmpw 3,7
        bgt caption_bound_range_next
        subf 6,5,3
        add 6,6,8
        clrlwi 6,6,16
        b caption_bound_index
    caption_bound_range_next:
        lhz 7,2(4)
        subf 7,5,7
        add 8,8,7
        addi 8,8,1
        addi 4,4,4
        b caption_bound_range
    caption_bound_index:
        cmpwi 11,1
        bne caption_bound_japanese
        .long 0x48000001
        lwz 5,0x8c(1)
        b caption_bound_quad
    caption_bound_japanese:
        mr 4,26
        lwz 5,0x94(1)
        add 5,26,5
        cmpwi 6,0x1b29
        beq caption_bound_japanese_special
        cmpwi 6,0x1b2d
        bne caption_bound_quad
    caption_bound_japanese_special:
        lwz 5,0x90(1)
        add 5,26,5
    caption_bound_quad:
        lwz 3,0x90(1)
        add 4,4,3
        addi 4,4,-1
        cmpwi 6,0x1b29
        beq caption_bound_quad_extra
        cmpwi 6,0x1b2d
        beq caption_bound_quad_extra
        cmpwi 6,0x1b2f
        beq caption_bound_quad_extra
        cmpwi 6,0x1c
        beq caption_bound_quad_extra
        cmpwi 6,0x1b30
        bne caption_bound_quad_edge
    caption_bound_quad_extra:
        addi 4,4,1
    caption_bound_quad_edge:
        cmpwi 4,588
        bgt caption_bound_ellipsis
        mr 26,5
        add 27,27,11
        add 12,12,11
    caption_bound_reserve:
        lwz 3,0x90(1)
        add 3,26,3
        addi 3,3,-1
        cmpwi 3,588
        bgt caption_bound_loop
        cmpwi 12,30
        bgt caption_bound_loop
        mr 10,27
        b caption_bound_loop
    caption_bound_control:
        cmpwi 3,0xa
        bne caption_bound_skip
        li 26,0
    caption_bound_skip:
        addi 27,27,1
        addi 12,12,1
        b caption_bound_reserve
    caption_bound_incomplete:
        stb 4,0(27)
        b caption_bound_done
    caption_bound_ellipsis:
        lis 3,0x10
        lhz 3,0x6828(3)
        srwi 4,3,8
        stb 4,0(10)
        stb 3,1(10)
        li 3,0
        stb 3,2(10)
    caption_bound_done:
        lfd 0,0x138(1)
        mtfsf 255,0
        lfd 0,0x130(1)
        lfd 2,0x140(1)
        lfd 3,0x148(1)
        lfd 4,0x150(1)
        ld 0,0x118(1)
        mtlr 0
        ld 0,0x120(1)
        mtcrf 255,0
        ld 3,0xa8(1)
        ld 4,0xb0(1)
        ld 5,0xb8(1)
        ld 6,0xc0(1)
        ld 7,0xc8(1)
        ld 8,0xd0(1)
        ld 9,0xd8(1)
        ld 10,0xe0(1)
        ld 11,0xe8(1)
        ld 12,0xf0(1)
        ld 26,0x100(1)
        ld 27,0x108(1)
        ld 31,0x110(1)
        ld 0,0xa0(1)
        addi 1,1,0x180
        .long 0x48000000
    """, bound_va)
    # Keystone's PPC fixups misencode numeric external targets in this block
    # when local labels are also present. Resolve its two branch relocation
    # slots separately at their actual PCs, like the relocated clone calls.
    bound_code = bytearray(bound_code)
    for marker, instruction in ((0x48000001, f"bl {metric_va:#x}"),
                                (0x48000000, "b 0xa0eac")):
        slots = [offset for offset in range(0, len(bound_code), 4)
                 if struct.unpack_from(">I", bound_code, offset)[0] == marker]
        if len(slots) != 1:
            raise ValueError("Save preview external branch relocation is ambiguous")
        offset = slots[0]
        bound_code[offset:offset + 4] = assemble(instruction, bound_va + offset)
    emit("caption_bounded_metric_excerpt", bound_code)
    replace(0xA0EA8, f"b {bound_va:#x}", "Bound only the temporary caption by complete characters and source row geometry")
    for va in CAPTION_SITES:
        replace(va, f"bl {clone_va:#x}", "Use original-font Latin metrics only for save/load slot caption")

    end = CAVE_START + len(code)
    for index in range(1, phcount):
        header = struct.unpack_from(">IIQQQQQQ", image, phoff + index * phsize)
        if header[0] == 1 and header[6] and VA_BIAS < header[3] + header[6] and header[3] < VA_BIAS + end:
            raise ValueError("Save preview RX extension overlaps another PT_LOAD")
    result[CAVE_START:end] = code
    struct.pack_into(">QQ", result, phoff + 0x20, end, end)
    report = {
        "source_sha256": SOURCE_SHA256, "input_sha256": INPUT_SHA256,
        "output_sha256": project.digest(result), "diagnostic_only": True,
        "patches": patches, "source_sites": patches, "injected_blocks": blocks,
        "rx_extension": {"program_header": 0, "old_filesz": CAVE_START,
                         "new_filesz": end, "old_memsz": CAVE_START, "new_memsz": end,
                         "file_begin": CAVE_START, "file_end": end,
                         "va_begin": VA_BIAS + CAVE_START, "size": len(code)},
        "source_ranges": source_ranges, "relocated_calls": relocated_calls,
        "source_path": {
            "list_renderer": ["0xa1660", "0xa1c9c"],
            "slot_call": "0xa17b0", "slot_renderer": ["0xa0470", "0xa1334"],
            "caption_format": ["0xa0e7c", "0xa0ea8"],
            "caption_draw_calls": [hex(va) for va in CAPTION_SITES],
            "fixed_draw": [hex(DRAW_BEGIN), hex(DRAW_END)],
            "metric_arithmetic_reference": ["0x1c344", "0x1c400"],
            "serialized_excerpt_builder": ["0x6f664", "0x6f884"],
            "ellipsis_source": "0x6f7d8..0x6f7e8 copies literal 0x106828 (CP932 8163) to excerpt+0x1c",
            "glyph_record_constructor": ["0x1bcb8", "0x1be24"],
            "font": "global 0x257028 -> +0x50; ranges +0, metrics +0x7c",
            "serialized_caption": "slot base 0x676530 + index*0x3fc0 + 0x1080; read only",
            "display_buffer": "slot frame +0x118..+0x158; hard NUL at +0x138",
            "caption_x": [420, 421], "caption_scale_constant_va": "0xa0468",
            "slot_top": "148 + visible_row*90, plus native scroll interpolation",
            "row_border_x": [209, 273, 1010, 1030],
            "row_border_source": ["0xa0650", "0xa0668", "0xa0670", "0xa0708", "0xa0720", "0xa0728"],
            "conservative_content_right": 1010,
            "selected_and_normal_caption_right": 1010,
            "maximum_relative_quad_right": 588,
            "edge_convention": "Conservative content edge1010 is exclusive; encoded right vertex <=1009",
            "width_policy": "Keep original hard32 excerpt if every full native quad fits; otherwise longest whole-character prefix plus original 8163 ellipsis within32 bytes and exclusive right1010",
        },
        "abi": {
            "draw": "Native1BE28 ABI: R3 font, R4/R5 signed16 x/y, R7 CP932, R8 color; F1 depth, F2/F3 scales; caller SP+0x74 word style",
            "clone_frame_size": 0x100, "ascii_scale_slot": 0x88,
            "ascii_next_cursor_slot": 0x8C,
            "bound": "At A0EA8: replay stb R20,0x138(SP); frame0x180 preserves R0/R3..12/R26/R27/R31/full CR/LR/F0/F2..4/FPSCR; CTR/XER/VMX untouched; return A0EAC",
            "draw_safety": "Original prologue/epilogue and nonvolatile state retained; ASCII helper uses only volatile scalar/FP scratch and CR0; VMX never touched",
        },
        "allowed_writes": ["Native caller/clone/helper stack frames", "Existing display excerpt only: hard32 NUL, final incomplete lead, or overwidth prefix+8163+NUL", "Native font+0x14 glyph count and font+0x10 vertex records via original1BCB8"],
        "fonts_unchanged": True, "original_glyph_drawing_unchanged": True,
        "japanese_fixed_cell_path_unchanged": True, "other_ui_unchanged": True,
        "serialized_saves_unchanged": True, "dialogue_backlog_unchanged": True,
        "original_vwf_helpers_unchanged": True, "source_allocation": False,
        "runtime_accepted": False, "production_cutover": False,
    }
    return bytes(result), report
