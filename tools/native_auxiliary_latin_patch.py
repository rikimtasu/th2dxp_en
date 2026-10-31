"""Diagnostic Latin support for the source's Japanese-only auxiliary fonts.

Keep their Japanese indices/pixels and script G controls. Append missing aliases
inside unused cells, extend each owned lookup allocation and install ink metrics.
No disk writes, production cutover, asset deployment or runtime acceptance.
"""
from __future__ import annotations

import struct

import geninterface_latin
import native_japanese_font_patch as japanese
import native_layout_patch
import project

# Story font1 (letters) and the two smaller auxiliary atlases share one object
# layout: 0(3) is the ordered CP932 range list and 0x7c(3) the ink metrics.
FONTS = {
    1: {'tpl': '_initial/font1.tpl', 'hook': 0x118D4, 'continue': 0x118D8, 'table': 0x24702C},
    2: {'tpl': '_initial/font2.tpl', 'hook': 0x11968, 'continue': 0x1196C, 'table': 0x247030},
    3: {'tpl': '_initial/font3.tpl', 'hook': 0x119FC, 'continue': 0x11A00, 'table': 0x247034},
}


def contiguous_ranges(codes):
    ranges = []
    for code in codes:
        if ranges and code == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], code)
        else:
            ranges.append((code, code))
    return ranges


def alias_codes(source):
    """Every full-width CP932 code the native ASCII alias table can select."""
    codes = {code for code, _ in geninterface_latin.aliases(source).values()}
    codes.update(int.from_bytes(char.encode('cp932'), 'big') for char in '‘’“”')
    return codes


def extend_atlas(source, main_tpl, auxiliary_tpl, *, font=1, codes=None):
    """Append aliases after every source index, preserving every other bit."""
    spec = FONTS[font]
    _, table, count, _ = japanese.SPECS[font]
    original = japanese.native_codes(source, table, count)
    main = japanese.native_codes(source, japanese.SPECS[0][1], 7402)
    wanted = alias_codes(source) if codes is None else set(codes)
    missing = sorted(wanted - set(original))
    full = original + missing
    height, width = struct.unpack_from('>HH', auxiliary_tpl, 4)
    capacity = (width // 48) * (height // 48) * 4
    # Each appended range names at least one cell; the lookup allocation is
    # extended separately from the texture-bank capacity check below.
    if len(full) > capacity:
        raise ValueError(
            f'{spec["tpl"]} needs {len(missing)} Latin aliases but its four texture '
            f'banks hold {capacity} cells after {count} native glyphs')
    output, allowed = bytearray(auxiliary_tpl), bytearray(len(auxiliary_tpl))
    for index, code in enumerate(missing, len(original)):
        cell = japanese.read_cell(main_tpl, main.index(code))
        japanese.write_cell(output, index, cell, allowed)
    if any((a ^ b) & (255 ^ mask) for a, b, mask in zip(auxiliary_tpl, output, allowed)):
        raise ValueError(f'{spec["tpl"]} changed unrelated packed bits')
    for index in range(len(original)):
        if japanese.read_cell(output, index).tobytes() != japanese.read_cell(auxiliary_tpl, index).tobytes():
            raise ValueError(f'{spec["tpl"]} changed an original Japanese/private glyph')
    old_range_count = struct.unpack_from('>I', source, spec['table'])[0] // 8 - 1
    ranges = contiguous_ranges(missing)
    return bytes(output), {'font': font, 'tpl': spec['tpl'],
                           'original_glyphs': len(original), 'added_glyphs': len(missing),
                           'codes': full, 'added_ranges': ranges, 'old_range_count': old_range_count,
                           'original_pixels_and_indices_preserved': True}


def apply(image, main_tpl, auxiliary_tpl, native, *, source, font=1, codes=None):
    """Extend the bounded RX helper tail and owned PH2 data, not scenario bytes."""
    spec = FONTS[font]
    hook, table_bytes_offset = spec['hook'], spec['table']
    if project.digest(source) != native_layout_patch.SOURCE_SHA256:
        raise ValueError(f'{spec["tpl"]} requires the pinned source executable')
    if image[hook - 0x10000:hook - 0x10000 + 4] != source[hook - 0x10000:hook - 0x10000 + 4]:
        raise ValueError(f'{spec["tpl"]} constructor return is already changed')
    if source[hook - 0x10000:hook - 0x10000 + 4] != bytes.fromhex('60000000'):
        raise ValueError(f'{spec["tpl"]} constructor return is not the source nop')
    if image[table_bytes_offset:table_bytes_offset + 4] != source[table_bytes_offset:table_bytes_offset + 4]:
        raise ValueError(f'{spec["tpl"]} lookup allocation is already changed')
    tpl, report = extend_atlas(source, main_tpl, auxiliary_tpl, font=font, codes=codes)
    range_bytes = b''.join(struct.pack('>HH', low, high) for low, high in report['added_ranges']) + bytes(4)
    main_codes = japanese.native_codes(source, japanese.SPECS[0][1], 7402)
    metrics = bytearray()
    for index, code in enumerate(report['codes']):
        ink = japanese.read_cell(tpl, index).getbbox()
        if ink is None:
            if code != 0x8140:
                raise ValueError(f'{spec["tpl"]} has an unexpectedly empty non-space glyph')
            at = geninterface_latin.METRICS_OFFSET + main_codes.index(code) * 2
            metrics.extend(image[at:at + 2])
        else:
            metrics.extend((ink[0], ink[2] - ink[0]))
    phoff = struct.unpack_from('>Q', image, 0x20)[0]
    phsize = struct.unpack_from('>H', image, 0x36)[0]
    ph2 = phoff + 2 * phsize
    kind, flags, file_start, va, _, filesz, memsz, _ = struct.unpack_from('>IIQQQQQQ', image, ph2)
    if kind != 1 or flags != 5 or not filesz or filesz != memsz:
        raise ValueError(f'{spec["tpl"]} needs the existing owned non-writable R-X PH2')
    start = (file_start + filesz + 3) & ~3
    data_va = va + start - file_start
    # Producer59908 consumes the pair through an unaligned16-byte vector load.
    # Own its tail bytes too; the final pair must not depend on page padding.
    data = range_bytes + bytes(metrics) + bytes(16)
    end = start + len(data)
    for index in range(struct.unpack_from('>H', image, 0x38)[0]):
        if index == 2:
            continue
        header = struct.unpack_from('>IIQQQQQQ', image, phoff + index * phsize)
        if header[0] != 1 or not header[6]:
            continue
        if (file_start < header[2] + header[5] and header[2] < end or
                va < header[3] + header[6] and header[3] < va + end - file_start):
            raise ValueError(f'{spec["tpl"]} data extension overlaps another mapping')
    if end > len(image) or any(image[file_start + filesz:end]):
        raise ValueError(f'{spec["tpl"]} data extension is not existing empty padding')
    rx_start = native['rx_extension']['file_end']
    address = rx_start + 0x10000
    metrics_va = data_va + len(range_bytes)
    assembler = native_layout_patch._assembler()
    instructions = f'''
        stdu 1,-0x40(1)
        std 0,0x20(1)
        std 11,0x28(1)
        std 12,0x30(1)
        mfctr 0
        std 0,0x38(1)
        lwz 11,0(3)
        addi 11,11,{report['old_range_count'] * 4}
        lis 12,{data_va >> 16}
        ori 12,12,{data_va & 0xffff}
        li 0,{len(range_bytes) // 4}
        mtctr 0
    copy_range:
        lwz 0,0(12)
        stw 0,0(11)
        addi 12,12,4
        addi 11,11,4
        bdnz copy_range
        lis 12,{metrics_va >> 16}
        ori 12,12,{metrics_va & 0xffff}
        stw 12,0x7c(3)
        ld 0,0x38(1)
        mtctr 0
        ld 12,0x30(1)
        ld 11,0x28(1)
        ld 0,0x20(1)
        addi 1,1,0x40
        b {spec["continue"]:#x}
    '''
    code = bytes(assembler.asm(instructions, addr=address)[0])
    rx_end = rx_start + len(code)
    if rx_end > native_layout_patch.CAVE_END or any(image[rx_start:rx_end]):
        raise ValueError(f'{spec["tpl"]} helper exceeds empty RX tail')
    rx_filesz, rx_memsz = struct.unpack_from('>QQ', image, phoff + 32)
    if (rx_filesz, rx_memsz) != (rx_start, rx_start):
        raise ValueError(f'{spec["tpl"]} RX mapping differs from the supplied native report')
    result = bytearray(image)
    result[start:end] = data
    result[rx_start:rx_end] = code
    result[hook - 0x10000:hook - 0x10000 + 4] = bytes(assembler.asm(f'b {address:#x}', addr=hook)[0])
    table_bytes = (report['old_range_count'] + len(report['added_ranges']) + 1) * 8
    struct.pack_into('>I', result, table_bytes_offset, table_bytes)
    struct.pack_into('>QQ', result, phoff + 32, rx_end, rx_end)
    struct.pack_into('>QQ', result, ph2 + 32, end - file_start, end - file_start)
    report.update(input_sha256=project.digest(image), output_sha256=project.digest(result),
                  input_tpl_sha256=project.digest(auxiliary_tpl), output_tpl_sha256=project.digest(tpl),
                  main_tpl_sha256=project.digest(main_tpl),
                  constructor_hook=hex(hook), helper_va=hex(address), helper_size=len(code),
                  range_data_va=hex(data_va), metrics_va=hex(metrics_va), table_bytes=table_bytes,
                  table_offset=hex(table_bytes_offset),
                  rx_end=rx_end, ph2_data_file_begin=start, ph2_data_file_end=end,
                  runtime_accepted=False, production_enabled=False)
    return bytes(result), tpl, report


def verify(image, tpl, report):
    """Bind the staged pixels, helper, hook and owned data to their report."""
    hook, table_bytes_offset = int(report['constructor_hook'], 16), int(report['table_offset'], 16)
    if project.digest(tpl) != report['output_tpl_sha256'] or project.digest(image) != report['output_sha256']:
        raise ValueError(f'{report["tpl"]} image/pixels differ from their report')
    word = struct.unpack_from('>I', image, hook - 0x10000)[0]
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    if word >> 26 != 18 or word & 3 or hook + displacement != int(report['helper_va'], 16):
        raise ValueError(f'{report["tpl"]} constructor hook does not reach its helper')
    if struct.unpack_from('>I', image, table_bytes_offset)[0] != report['table_bytes']:
        raise ValueError(f'{report["tpl"]} lookup allocation differs from its report')
    phoff = struct.unpack_from('>Q', image, 0x20)[0]
    phsize, phcount = struct.unpack_from('>HH', image, 0x36)
    ph2 = phoff + 2 * phsize
    file_start = struct.unpack_from('>Q', image, ph2 + 8)[0]
    filesz = struct.unpack_from('>Q', image, ph2 + 32)[0]
    if (struct.unpack_from('>QQ', image, phoff + 32) != (report['rx_end'], report['rx_end'])
            or filesz != report['ph2_data_file_end'] - file_start):
        raise ValueError(f'{report["tpl"]} mapping sizes differ from their report')
    return {'font': report['font'], 'tpl': report['tpl'],
            'verified_glyphs': report['added_glyphs'], 'verified_ranges': len(report['added_ranges']),
            'helper_size': report['helper_size'], 'rx_end': report['rx_end'],
            'runtime_accepted': False}
