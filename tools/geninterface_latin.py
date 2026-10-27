"""In-memory, source-bound Latin replacement for the original main-font R plane."""
from __future__ import annotations

import io
import string
import struct

from PIL import Image, ImageDraw, ImageFont, __version__ as PILLOW_VERSION

import native_glyph_extent_smoke
import native_layout_patch
from native_layout_smoke import SourceMetrics
import project

FONT = project.ROOT / "fonts/GenInterfaceJP-0.8.1/Gen Interface JP/GenInterfaceJP-Regular.ttf"
OFL = project.ROOT / "fonts/GenInterfaceJP-0.8.1/OFL.txt"
FONT_SHA256 = "194739ee65ec5f56cc2057fce3e69ce64d53e4a196a8abf2feb2a78b3125567c"
OFL_SHA256 = "01c53a388c44235eb340c6f548142fab1703fa44efcc85a098e54cf534c9f2ab"
ALPHANUMERIC = string.ascii_uppercase + string.ascii_lowercase + string.digits
BRACKETS = "()[]{}"
REPLACED = ALPHANUMERIC + BRACKETS
NATIVE_CELL, EM, BASELINE, SAMPLING_BORDER = 48, 47, 37, 1
METRICS_OFFSET = 0x247038
ALIAS_OFFSET = 0x2514B0
PROVENANCE_KEYS = ("face", "font_sha256", "ofl_sha256", "em", "baseline",
                   "native_cell", "raster_em", "sampling_border", "bracket_policy",
                   "replacement_characters", "pillow_version", "method")


class GlyphMapping(dict):
    """Ordinary glyph mapping with explicit JSON-serializable face provenance."""
    def __init__(self, values, provenance):
        super().__init__(values)
        self.provenance = provenance


def aliases(source):
    """Resolve only original printable-ASCII aliases, using source range order."""
    metrics = SourceMetrics(source)
    result = {}
    for byte in range(32, 127):
        code = struct.unpack_from(">H", source, ALIAS_OFFSET + 2 * (byte - 32))[0]
        index = 0
        for first, last in metrics.ranges:
            if first <= code <= last:
                index += code - first
                break
            index += last - first + 1
        else:
            raise ValueError(f"Missing source ASCII alias {byte:#x}")
        if index >= 1024:
            raise ValueError("ASCII alias outside original main-font R plane")
        result[chr(byte)] = (code, index)
    return result


def raster_font():
    """Return the approved face at the reviewed raster em, refusing other inputs."""
    font_bytes = FONT.read_bytes()
    if project.digest(font_bytes) != FONT_SHA256:
        raise ValueError("Selected font provenance changed")
    return ImageFont.truetype(io.BytesIO(font_bytes), EM, layout_engine=ImageFont.Layout.BASIC)


def raster_ink(font, char):
    """Capture complete, unclipped source-face ink relative to its baseline."""
    scratch = Image.new("L", (192, 192))
    ImageDraw.Draw(scratch).text((72, 72), char, font=font, fill=255, anchor="ls")
    box = scratch.getbbox()
    if box is None:
        raise ValueError(f"Selected font has no ink for {char!r}")
    return scratch.crop(box), tuple(value - 72 for value in box)


def _generate(source):
    if project.digest(source) != native_layout_patch.SOURCE_SHA256:
        raise ValueError("Latin replacement requires immutable reviewed executable")
    font_bytes, ofl_bytes = FONT.read_bytes(), OFL.read_bytes()
    if project.digest(font_bytes) != FONT_SHA256 or project.digest(ofl_bytes) != OFL_SHA256:
        raise ValueError("Selected font/license provenance changed")
    font = ImageFont.truetype(io.BytesIO(font_bytes), EM, layout_engine=ImageFont.Layout.BASIC)
    atlas = native_glyph_extent_smoke.original_atlas()
    tpl = (project.ROOT / "work/assets/fonts/_initial/font.tpl").read_bytes()
    original = tpl
    output = bytearray(tpl)
    plane_offset = struct.unpack_from(">I", tpl, 12)[0]
    selected = aliases(source)
    metrics = SourceMetrics(source)
    if len({selected[c][1] for c in REPLACED}) != len(REPLACED):
        raise ValueError("Replacement aliases unexpectedly share slots")
    if any(selected[c][1] == selected[other][1]
           for c in REPLACED for other in selected if other not in REPLACED):
        raise ValueError("Replacement aliases overlap retained ASCII")
    rasters = {char: raster_ink(font, char) for char in REPLACED}
    # One optical axis halfway between this face's cap and x-height centers.
    # All six brackets move together, rounded to the nearest native pixel.
    reference_sum = sum(rasters[c][1][1] + rasters[c][1][3] for c in "Hx")
    bracket_top = min(rasters[c][1][1] for c in BRACKETS)
    bracket_bottom = max(rasters[c][1][3] for c in BRACKETS)
    bracket_shift = (reference_sum - 2 * (bracket_top + bracket_bottom) + 2) // 4
    bracket_policy = {"characters": BRACKETS, "vertical_shift": bracket_shift,
                      "reference_characters": "Hx",
                      "text_axis": BASELINE + reference_sum / 4,
                      "ink_axis": BASELINE + bracket_shift + (bracket_top + bracket_bottom) / 2,
                      "method": "Common full-ink envelope centered between cap and x-height axes; nearest whole pixel"}
    rows, mapping = [], {}
    for char, (code, index) in selected.items():
        x, y = index % 32 * NATIVE_CELL, index // 32 * NATIVE_CELL
        cell = atlas.crop((x, y, x + NATIVE_CELL, y + NATIVE_CELL))
        source_ink = cell.getbbox()
        before = metrics.main_pair(ord(char))
        raster_bounds, placement = None, None
        if char in REPLACED:
            raster, raster_bounds = rasters[char]
            width, height = raster.size
            top = raster_bounds[1] + BASELINE + (bracket_shift if char in BRACKETS else 0)
            left = (NATIVE_CELL - width) // 2
            bottom = top + height
            if (left < SAMPLING_BORDER or left + width > NATIVE_CELL - SAMPLING_BORDER
                    or top < SAMPLING_BORDER or bottom > NATIVE_CELL - SAMPLING_BORDER):
                raise ValueError(f"Native cell sampling border cannot fit {char!r}: {left, top, width, height}")
            placement = [left, top]
            cell = Image.new("L", (NATIVE_CELL, NATIVE_CELL))
            cell.paste(raster, (left, top))
            # A4R4G4B4 R has four bits; metrics follow the actual quantized ink.
            cell = cell.point(lambda value: ((value + 8) // 17) * 17)
            ink = cell.getbbox()
            if ink is None:
                raise ValueError("Quantization removed selected glyph")
            pair = (ink[0], ink[2] - ink[0])
            pixels = cell.tobytes()
            for row in range(NATIVE_CELL):
                for column in range(NATIVE_CELL):
                    offset = plane_offset + ((y + row) * 1536 + x + column) * 2
                    output[offset] = (output[offset] & 0xF0) | (pixels[row * NATIVE_CELL + column] // 17)
        else:
            pair = before
            ink = cell.getbbox()
        a, b = pair
        mapping[char] = (cell.crop((a, 0, a + b, NATIVE_CELL)), b + 6)
        rows.append({"character": char, "replaced": char in REPLACED,
                     "cp932_alias": hex(code), "native_index": index,
                     "metric_file_offset": METRICS_OFFSET + index * 2,
                     "source_a": before[0], "source_b": before[1], "a": a, "b": b,
                     "advance": b + 6, "ink_bounds": list(ink) if ink else None,
                     "source_ink_bounds": list(source_ink) if source_ink else None,
                     "raster_baseline_bounds": list(raster_bounds) if raster_bounds else None,
                     "raster_placement": placement,
                     "shared_fullwidth_character": bytes((code >> 8, code & 255)).decode("cp932") if char in REPLACED else None,
                     "atlas_cell": [x, y, x + NATIVE_CELL, y + NATIVE_CELL],
                     "cell_sha256": project.digest(cell.tobytes())})
    provenance = {"face": "Gen Interface JP Regular", "font_sha256": FONT_SHA256,
                  "ofl_sha256": OFL_SHA256, "em": EM, "baseline": BASELINE,
                  "native_cell": NATIVE_CELL, "raster_em": EM,
                  "sampling_border": SAMPLING_BORDER, "bracket_policy": bracket_policy,
                  "replacement_characters": REPLACED,
                  "pillow_version": PILLOW_VERSION,
                  "method": "FreeType BASIC 47px em; native48 cell; full-ink horizontal centering; common Latin baseline; optical bracket axis; transparent sampling border; R4 nearest quantization; native ink-width+6 advance"}
    report = dict(provenance, source_tpl_sha256=project.digest(original),
                  output_tpl_sha256=project.digest(output), glyphs=rows,
                  replacement_count=len(REPLACED), metrics_pointer="0x257038",
                  unrelated_packed_bits_preserved=True, source_paths_unchanged=True,
                  nonreplacement_japanese_private_punctuation_preserved=True,
                  shared_fullwidth_aliases=[{"character": c, "cp932_alias": hex(selected[c][0]),
                                            "native_index": selected[c][1]} for c in REPLACED],
                  fullwidth_latin_and_bracket_aliases_share_replacement=True,
                  runtime_accepted=False)
    return bytes(output), report, GlyphMapping(mapping, provenance)


def glyphs(source):
    """Return all95 printable ASCII: cropped L masks, cell height48, b+6 advances."""
    return _generate(source)[2]


def replacement(source):
    """Return patched TPL bytes and provenance without writes or installation."""
    tpl, report, _ = _generate(source)
    return tpl, report
