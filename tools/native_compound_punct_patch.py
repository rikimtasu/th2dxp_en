"""Narrow, source-bound private compound punctuation overlay; no script edits.

Proofs are relative to this overlay's supplied input assets, not earlier layers.
Only E000/F040, E001/F041 and E00E/F04E are approved pixel exceptions.
"""
from __future__ import annotations

from PIL import Image

import geninterface_latin as latin
import native_japanese_font_patch as japanese
import native_latin_punct_patch as punctuation
import native_layout_patch
import project

WHITELIST = ((0xE000, 0xF040, '!?', 6950),
             (0xE001, 0xF041, '!!', 6951),
             (0xE00E, 0xF04E, '??', 6964))
MAIN = '_initial/font.tpl'


def compose(font, text):
    """Compose full masks at native ink-width+6 spacing, then quantize once."""
    parts, cursor = [], 0
    for char in text:
        raster, bounds = latin.raster_ink(font, char)
        parts.append((raster, cursor, bounds[1]))
        cursor += raster.width + punctuation.ADVANCE_PADDING
    top = min(y for _, _, y in parts)
    bottom = max(y + raster.height for raster, _, y in parts)
    width = cursor - punctuation.ADVANCE_PADDING
    raster = Image.new('L', (width, bottom - top))
    for mask, x, y in parts:
        raster.paste(mask, (x, y - top))
    cell, ink, placement, pair = punctuation.pack_cell(
        raster, (0, top, width, bottom), baseline=37, border=1, cell_size=48)
    return cell, list(ink), list(placement), list(pair)


def _provenance(source):
    if project.digest(source) != native_layout_patch.SOURCE_SHA256:
        raise ValueError('Compound punctuation requires the immutable executable')
    if (project.digest(latin.FONT.read_bytes()) != latin.FONT_SHA256
            or project.digest(latin.OFL.read_bytes()) != latin.OFL_SHA256):
        raise ValueError('Compound punctuation face/license provenance changed')


def substitute(source, replacements):
    """Return new asset mapping and JSON manifest; never modify supplied inputs."""
    _provenance(source)
    specs = {row[0]: row for row in japanese.SPECS}
    if MAIN not in replacements or set(replacements) - set(specs):
        raise ValueError('Require main font and only supplied native font1/2/3 assets')
    font = latin.raster_font()
    cells = {code: compose(font, text) for _, code, text, _ in WHITELIST}
    output, assets, patches = {}, [], []
    for name, incoming in replacements.items():
        _, table, count, source_hash = specs[name]
        original = (project.ROOT / 'work/assets/fonts' / name).read_bytes()
        if project.digest(original) != source_hash:
            raise ValueError('Immutable source font changed: ' + name)
        if len(incoming) != len(original):
            raise ValueError('Overlay input font size changed: ' + name)
        codes = japanese.native_codes(source, table, count)
        changed, allowed, rows = bytearray(incoming), bytearray(len(incoming)), []
        for unicode, code, text, main_index in WHITELIST:
            indices = [i for i, value in enumerate(codes) if value == code]
            if len(indices) > 1 or (name == MAIN and indices != [main_index]):
                raise ValueError('Compound native source index changed')
            for index in indices:
                cell, ink, placement, pair = cells[code]
                before = japanese.read_cell(incoming, index)
                japanese.write_cell(changed, index, cell, allowed)
                record, channel, x, y, *_ = japanese.slot(incoming, index)
                rows.append({'unicode': f'U+{unicode:04X}', 'cp932': hex(code),
                             'compound': text, 'native_index': index,
                             'record': record, 'channel': 'RGBA'[channel],
                             'atlas_cell': [x, y, x + 48, y + 48],
                             'ink_bounds': ink, 'placement': placement, 'metric_pair': pair,
                             'cell_sha256': project.digest(cell.tobytes()),
                             'input_cell_hex': before.tobytes().hex()})
                if name == MAIN:
                    at = latin.METRICS_OFFSET + index * 2
                    patches.append({'file_offset': hex(at), 'native_index': index,
                                    'source_before': source[at:at + 2].hex(),
                                    'after': bytes(pair).hex()})
        if any((a ^ b) & (255 ^ mask) for a, b, mask in zip(incoming, changed, allowed)):
            raise ValueError('Compound overlay changed unselected packed bits')
        output[name] = bytes(changed)
        assets.append({'asset': name, 'source_sha256': source_hash,
                       'input_sha256': project.digest(incoming),
                       'output_sha256': project.digest(changed), 'range_table': hex(table),
                       'glyph_count': count, 'glyphs': rows})
    manifest = {'source_sha256': project.digest(source), 'font_sha256': latin.FONT_SHA256,
                'ofl_sha256': latin.OFL_SHA256, 'whitelist': [list(row) for row in WHITELIST],
                'baseline': 37, 'em': latin.EM, 'cell': 48, 'sampling_border': 1,
                'advance_rule': 'component full ink width + 6; compound quantized ink width + 6',
                'method': 'full masks, common baseline, full composed ink horizontal centering; '
                          'one nearest4bit quantization; no scaling or clipping',
                'proof_scope': 'overlay-layer-relative; every unselected packed bit retained',
                'all_other_pua_retained': True, 'assets': assets, 'patches': patches,
                'runtime_accepted': False}
    return output, manifest


def _bound_inputs(source, replacements, manifest):
    """Recover and hash-bind layer inputs, then independently regenerate the proof."""
    incoming = {}
    if set(replacements) != {asset['asset'] for asset in manifest['assets']}:
        raise ValueError('Compound asset inventory changed')
    for asset in manifest['assets']:
        name = asset['asset']
        tpl = bytearray(replacements[name])
        for row in asset['glyphs']:
            pixels = bytes.fromhex(row['input_cell_hex'])
            if len(pixels) != 48 * 48 or any(value % 17 for value in pixels):
                raise ValueError('Compound input cell is not native quantized ink')
            japanese.write_cell(tpl, row['native_index'],
                                Image.frombytes('L', (48, 48), pixels), bytearray(len(tpl)))
        if project.digest(tpl) != asset['input_sha256']:
            raise ValueError('Compound retained bits/header or input provenance changed')
        incoming[name] = bytes(tpl)
    expected, bound = substitute(source, incoming)
    if manifest != bound or replacements != expected:
        raise ValueError('Compound pixels/manifest differ from source-bound generation')


def apply(image, manifest, *, source):
    """Install only the three main-font metrics into an already assembled image."""
    _provenance(source)
    # Reconstruct source-bound rows without requiring the caller's atlas here.
    font = latin.raster_font()
    expected = {index: compose(font, text)[3]
                for _, _, text, index in WHITELIST}
    if (manifest['source_sha256'] != project.digest(source)
            or manifest['font_sha256'] != latin.FONT_SHA256
            or manifest['ofl_sha256'] != latin.OFL_SHA256
            or manifest['whitelist'] != [list(row) for row in WHITELIST]):
        raise ValueError('Compound metric manifest provenance changed')
    patches = []
    for index, pair in expected.items():
        at = latin.METRICS_OFFSET + index * 2
        patches.append({'file_offset': hex(at), 'native_index': index,
                        'source_before': source[at:at + 2].hex(), 'after': bytes(pair).hex()})
    if manifest['patches'] != patches:
        raise ValueError('Compound metrics differ from quantized ink')
    result = bytearray(image)
    for patch in patches:
        at = int(patch['file_offset'], 0)
        if result[at:at + 2] != bytes.fromhex(patch['source_before']):
            raise ValueError('Compound metric input differs from immutable source')
        result[at:at + 2] = bytes.fromhex(patch['after'])
    return bytes(result)


def verify(source, image, replacements, manifest):
    """Prove full asset bytes, preserved nibbles, provenance and actual ink metrics."""
    _bound_inputs(source, replacements, manifest)
    for asset in manifest['assets']:
        for row in asset['glyphs']:
            cell = japanese.read_cell(replacements[asset['asset']], row['native_index'])
            ink = cell.getbbox()
            if list(ink) != row['ink_bounds'] or [ink[0], ink[2] - ink[0]] != row['metric_pair']:
                raise ValueError('Compound native metrics mismatch actual quantized ink')
    for patch in manifest['patches']:
        at = int(patch['file_offset'], 0)
        if image[at:at + 2] != bytes.fromhex(patch['after']):
            raise ValueError('Compound native metrics are absent')
    return {'verified_assets': len(replacements),
            'verified_cells': sum(len(asset['glyphs']) for asset in manifest['assets']),
            'verified_metric_pairs': len(manifest['patches']),
            'proof_scope': manifest['proof_scope'], 'all_other_pua_retained': True,
            'source_sha256': project.digest(source), 'image_sha256': project.digest(image),
            'font_sha256': latin.FONT_SHA256, 'ofl_sha256': latin.OFL_SHA256,
            'assets': [{key: asset[key] for key in
                        ('asset', 'source_sha256', 'input_sha256', 'output_sha256')}
                       for asset in manifest['assets']], 'runtime_accepted': False}
