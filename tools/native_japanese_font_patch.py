"""Source-bound GenInterfaceJP Japanese cells for all four native font atlases.

Chained after the reviewed Latin/punctuation atlas. Native indices, fixed-cell
Japanese advances and private icons are retained. Nothing is installed/written.
"""
from __future__ import annotations

from functools import lru_cache
import struct

from PIL import Image

import geninterface_latin as latin
import native_latin_punct_patch
import native_layout_patch
import project

CELL, BASELINE, ORIGIN_X, BORDER = 48, 40, 1, 1
# Native1CF34/1D0A4/1D224/1D3A4 clone R,G,B,A as successive glyph banks.
CHANNELS = ((0, 0), (1, 4), (1, 0), (0, 4))
SPECS = (
    ('_initial/font.tpl', 0xDA430, 7402, 'ae3fda1bc50d5457326a6e1966c17a1f8d18469d4e425f623768604a62e5fb95'),
    ('_initial/font1.tpl', 0xD8724, 137, '394950c22ceb7b49150b2d6292b632e790e9284d8ede8089362a7ea9023878fd'),
    ('_initial/font2.tpl', 0xD8BBC, 27, '8124114b974bc0e103222b616d81a25151e9ef96cc27d7a0c18627321c50fe97'),
    ('_initial/font3.tpl', 0xD8FC4, 203, '6c03b6390a842193840cb08d69e0c57c0addc211951c503860dc7ca204e91b34'),
)


def japanese(char):
    """Japanese punctuation/kana/CJK only; never PUA, Western aliases or icons."""
    value = ord(char)
    return (0x3001 <= value <= 0x30FF or 0x3400 <= value <= 0x9FFF
            or 0xF900 <= value <= 0xFAFF)


def unicode_glyphs(font_bytes):
    """Read the pinned face's Unicode format12 cmap, rejecting .notdef coverage."""
    tables = struct.unpack_from('>H', font_bytes, 4)[0]
    for index in range(tables):
        tag, _, offset, _ = struct.unpack_from('>4sIII', font_bytes, 12 + index * 16)
        if tag == b'cmap':
            break
    else:
        raise ValueError('Japanese font has no cmap table')
    count = struct.unpack_from('>H', font_bytes, offset + 2)[0]
    for index in range(count):
        platform, encoding, relative = struct.unpack_from('>HHI', font_bytes, offset + 4 + index * 8)
        at = offset + relative
        if (platform, encoding) == (3, 10) and struct.unpack_from('>H', font_bytes, at)[0] == 12:
            groups = struct.unpack_from('>I', font_bytes, at + 12)[0]
            result = set()
            for group in range(groups):
                start, end, glyph = struct.unpack_from('>III', font_bytes, at + 16 + group * 12)
                result.update(range(start + (glyph == 0), end + 1))
            return result
    raise ValueError('Japanese font lacks the expected Unicode format12 cmap')


def native_codes(source, table, expected):
    codes = []
    while True:
        first, last = struct.unpack_from('>II', source, table)
        if not first:
            break
        low = struct.unpack_from('>H', source, first - 0x10000)[0]
        high = struct.unpack_from('>H', source, last - 0x10000)[0]
        if low > high or len(codes) + high - low + 1 > expected:
            raise ValueError('Japanese source range exceeds the reviewed glyph inventory')
        codes.extend(range(low, high + 1))
        table += 8
    if len(codes) != expected:
        raise ValueError('Japanese source glyph count changed')
    return codes


def slot(tpl, index):
    """Resolve a native index into its original record/channel/cell storage."""
    records = struct.unpack_from('>I', tpl)[0]
    first_height, first_width = struct.unpack_from('>HH', tpl, 4)
    cells = first_width // CELL * (first_height // CELL)
    if index < 0 or not cells:
        raise ValueError('Japanese glyph index or cell dimensions are invalid')
    bank, within = divmod(index, cells)
    record, channel = divmod(bank, 4)
    if record >= records:
        raise ValueError('Japanese glyph index exceeds its texture banks')
    at = 4 + record * 20
    height, width, pitch = struct.unpack_from('>HHH', tpl, at)
    offset = struct.unpack_from('>I', tpl, at + 8)[0]
    if (not cells or (width, height) != (first_width, first_height)
            or width % CELL or height % CELL or pitch != width * 2
            or tpl[at + 6] != 0xA3 or offset + width * height * 2 > len(tpl)):
        raise ValueError(f'Japanese font is not the reviewed linear A4R4G4B4 texture: '
                         f'index={index}, record={record}, size={width}x{height}, '
                         f'first={first_width}x{first_height}, pitch={pitch}, '
                         f'format={tpl[at + 6]:#x}, offset={offset}, bytes={len(tpl)}')
    x, y = within % (width // CELL) * CELL, within // (width // CELL) * CELL
    byte, shift = CHANNELS[channel]
    return record, channel, x, y, offset + (y * width + x) * 2 + byte, pitch, shift


def read_cell(tpl, index):
    _, _, _, _, start, pitch, shift = slot(tpl, index)
    pixels = bytes(((tpl[start + y * pitch + x * 2] >> shift) & 15) * 17
                   for y in range(CELL) for x in range(CELL))
    return Image.frombytes('L', (CELL, CELL), pixels)


def write_cell(output, index, cell, allowed):
    _, _, _, _, start, pitch, shift = slot(output, index)
    pixels, mask = cell.tobytes(), 15 << shift
    for y in range(CELL):
        for x in range(CELL):
            at = start + y * pitch + x * 2
            output[at] = (output[at] & (255 ^ mask)) | (pixels[y * CELL + x] // 17 << shift)
            allowed[at] |= mask


def pack_cell(raster, bounds):
    """One common CJK origin/baseline; preserve full ink and a transparent border."""
    left, top = ORIGIN_X + bounds[0], BASELINE + bounds[1]
    if (left < BORDER or top < BORDER or left + raster.width > CELL - BORDER
            or top + raster.height > CELL - BORDER):
        raise ValueError(f'Japanese glyph cannot fit without clipping: {bounds}')
    cell = Image.new('L', (CELL, CELL))
    cell.paste(raster, (left, top))
    cell = cell.point(lambda value: ((value + 8) // 17) * 17)
    if cell.getbbox() is None:
        raise ValueError('Japanese glyph has no quantized ink')
    return cell, (left, top)


@lru_cache(maxsize=1)
def substitute(source):
    if project.digest(source) != native_layout_patch.SOURCE_SHA256:
        raise ValueError('Japanese font requires the immutable executable')
    font_bytes = latin.FONT.read_bytes()
    if (project.digest(font_bytes) != latin.FONT_SHA256
            or project.digest(latin.OFL.read_bytes()) != latin.OFL_SHA256):
        raise ValueError('Japanese font/license provenance changed')
    coverage, font = unicode_glyphs(font_bytes), latin.raster_font()
    base, punct = native_latin_punct_patch.substitute_cached(source)
    replacements, assets, patches, rasters = {}, [], [], {}
    for name, table, count, source_hash in SPECS:
        original = (project.ROOT / 'work/assets/fonts' / name).read_bytes()
        if project.digest(original) != source_hash:
            raise ValueError(f'Original Japanese font changed: {name}')
        incoming = base if name == '_initial/font.tpl' else original
        output, allowed, rows = bytearray(incoming), bytearray(len(incoming)), []
        codes = native_codes(source, table, count)
        for index, code in enumerate(codes):
            # The pinned inventory includes a reserved F07F slot. It is neither
            # a CP932 character nor a font fallback: keep its packed bits intact.
            if (code & 255) == 0x7F:
                continue
            char = code.to_bytes(2, 'big').decode('cp932')
            if not japanese(char):
                continue
            if ord(char) not in coverage:
                raise ValueError(f'GenInterfaceJP lacks {char!r} ({code:#x}); no fallback permitted')
            if char not in rasters:
                raster, bounds = latin.raster_ink(font, char)
                cell, placement = pack_cell(raster, bounds)
                rasters[char] = cell, bounds, placement
            cell, bounds, placement = rasters[char]
            write_cell(output, index, cell, allowed)
            record, channel, x, y, *_ = slot(output, index)
            ink = cell.getbbox()
            row = {'character': char, 'cp932': hex(code), 'native_index': index,
                   'record': record, 'channel': 'RGBA'[channel], 'bank': record * 4 + channel,
                   'atlas_cell': [x, y, x + CELL, y + CELL],
                   'raster_baseline_bounds': list(bounds), 'placement': list(placement),
                   'ink_bounds': list(ink), 'cell_sha256': project.digest(cell.tobytes())}
            rows.append(row)
            if name == '_initial/font.tpl':
                at = latin.METRICS_OFFSET + index * 2
                pair = bytes((ink[0], ink[2] - ink[0]))
                patches.append({'file_offset': hex(at), 'source_before': source[at:at + 2].hex(),
                                'after': pair.hex(), 'character': char, 'native_index': index})
        if any((a ^ b) & (255 ^ mask) for a, b, mask in zip(incoming, output, allowed)):
            raise ValueError('Japanese font changed retained packed bits')
        replacements[name] = bytes(output)
        assets.append({'asset': name, 'source_sha256': source_hash,
                       'input_sha256': project.digest(incoming), 'output_sha256': project.digest(output),
                       'glyph_count': count, 'replaced_count': len(rows),
                       'retained_count': count - len(rows), 'range_table': hex(table), 'glyphs': rows})
    manifest = {'face': 'Gen Interface JP Regular', 'font_sha256': latin.FONT_SHA256,
                'ofl_sha256': latin.OFL_SHA256, 'source_sha256': project.digest(source),
                'em': latin.EM, 'baseline': BASELINE, 'origin_x': ORIGIN_X,
                'cell': CELL, 'sampling_border': BORDER,
                'base_punctuation_tpl_sha256': punct['output_tpl_sha256'],
                'japanese_advance': 'unchanged native fixed48; auxiliary fallback ABI unchanged',
                'latin_cells_unchanged': True, 'private_and_unselected_bits_preserved': True,
                'method': 'Common47px em; uniform CJK origin(1,40); no scaling/cropping; nearest4bit quantization',
                'replaced_count': sum(row['replaced_count'] for row in assets),
                'assets': assets, 'patches': patches, 'runtime_accepted': False}
    return replacements, manifest


def apply(image, manifest, *, source):
    if manifest != substitute(source)[1]:
        raise ValueError('Japanese font manifest differs from source/face-derived sites')
    result = bytearray(image)
    for patch in manifest['patches']:
        at = int(patch['file_offset'], 0)
        if result[at:at + 2] != bytes.fromhex(patch['source_before']):
            raise ValueError('Japanese source metric pair changed before patching')
        result[at:at + 2] = bytes.fromhex(patch['after'])
    return bytes(result)


def verify(source, image, replacements, manifest):
    expected, bound = substitute(source)
    if manifest != bound or replacements != expected:
        raise ValueError('Japanese font pixels/manifest differ from the pinned generation')
    for asset in manifest['assets']:
        tpl = replacements[asset['asset']]
        for row in asset['glyphs']:
            cell = read_cell(tpl, row['native_index'])
            if project.digest(cell.tobytes()) != row['cell_sha256'] or list(cell.getbbox()) != row['ink_bounds']:
                raise ValueError(f"Japanese cell/ink mismatch: {row['character']!r}")
    for patch in manifest['patches']:
        at = int(patch['file_offset'], 0)
        if image[at:at + 2] != bytes.fromhex(patch['after']):
            raise ValueError('Japanese metrics are absent from the executable')
    return {'verified_glyphs': manifest['replaced_count'], 'verified_assets': len(replacements),
            'verified_metric_pairs': len(manifest['patches']), 'runtime_accepted': False}
