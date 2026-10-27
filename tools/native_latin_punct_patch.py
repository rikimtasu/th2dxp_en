"""Extend the approved Latin face to the punctuation the translation renders.

`geninterface_latin` replaces the 62 alphanumeric and six bracket aliases. The
translation also draws ASCII `! ? . , ' " : ; - ~ * < >` etc. through the
original Japanese font's remaining ASCII aliases, which are full-width cells
with an em-wide advance, so they appear beside the new letters as wide Japanese
marks. This module adds exactly those cells.

It is deliberately chained on top of `geninterface_latin.replacement()` instead
of widening that module's `REPLACED` tuple: the reviewed native template pins
`replacement_characters` and `output_tpl_sha256`, and those must keep identifying
the same 68 reviewed cells. Here the base pixels are read once, only the new
cells' R nibbles change, and every new metric pair is the quantized ink bound of
the pixels written here.

Three printable punctuation aliases stay on their original cells, each for a
measured reason recorded in `EXCLUDED`: `$` and `|` cannot be placed inside the
native cell at the reviewed 47 px em without clipping, and `\` shares its cell
with the full-width yen sign, which the shipped text uses while ASCII `\` only
ever introduces inline controls.

Each alias cell also serves its full-width counterpart (`！` `？` `’` `～` `＞`
and so on), exactly as the reviewed atlas already makes `Ａ`-class aliases carry
the Latin letters. The manifest records the counterpart for every replaced cell,
so that appearance change is explicit rather than incidental.
"""
from __future__ import annotations

import json
import string

import geninterface_latin
import native_layout_patch
import project

# Every printable ASCII punctuation alias except the six brackets (their common
# optical axis belongs to geninterface_latin) and the three measured exclusions.
EXCLUDED = {
    "$": "45 px tall ink starts 3 px above the native cell at the reviewed baseline",
    "|": "57 px ink is taller than the 48 px native cell",
    "\\": "its cell also draws the full-width yen sign the text uses; ASCII \\ only introduces inline controls",
}
PUNCTUATION = "".join(char for char in string.punctuation
                      if char not in geninterface_latin.BRACKETS and char not in EXCLUDED)
CELL = geninterface_latin.NATIVE_CELL
PLANE = 1536
ADVANCE_PADDING = 6
METRICS_POINTER = "0x257038"


def _require(condition, message):
    if not condition:
        raise ValueError("Punctuation atlas: " + message)


def pack_cell(raster, bounds, *, border=geninterface_latin.SAMPLING_BORDER, cell_size=CELL,
              baseline=geninterface_latin.BASELINE):
    """Place one face raster in a native cell; return the quantized cell and pair.

    The placement rule is the reviewed one: full ink horizontally centred, Latin
    baseline, and a transparent sampling border on every side. Quantization is
    the native R4 nearest step, and the metric pair is read back out of the
    quantized pixels rather than the pre-quantized raster.
    """
    from PIL import Image

    width, height = raster.size
    left = (cell_size - width) // 2
    top = bounds[1] + baseline
    bottom = top + height
    if (left < border or left + width > cell_size - border
            or top < border or bottom > cell_size - border):
        raise ValueError(
            f"Punctuation atlas: native cell sampling border cannot fit {width}x{height} "
            f"ink at ({left}, {top}) in a {cell_size} px cell")
    cell = Image.new("L", (cell_size, cell_size))
    cell.paste(raster, (left, top))
    cell = cell.point(lambda value: ((value + 8) // 17) * 17)
    ink = cell.getbbox()
    _require(ink is not None, "quantization removed the selected glyph")
    return cell, ink, (left, top), (ink[0], ink[2] - ink[0])


def _write_cell(output, plane_offset, index, cell, *, plane=PLANE, cell_size=CELL):
    """Replace only the R nibble of this cell's pixels; every other bit is kept."""
    pixels = cell.tobytes()
    x, y = index % 32 * cell_size, index // 32 * cell_size
    for row in range(cell_size):
        for column in range(cell_size):
            offset = plane_offset + ((y + row) * plane + x + column) * 2
            output[offset] = (output[offset] & 0xF0) | (pixels[row * cell_size + column] // 17)


def substitute(source):
    """Return the extended TPL bytes and a manifest chained to the base atlas."""
    _require(project.digest(source) == native_layout_patch.SOURCE_SHA256,
             "requires the immutable reviewed executable")
    base_tpl, base = geninterface_latin.replacement(source)
    selected = geninterface_latin.aliases(source)
    replaced = {row["native_index"] for row in base["glyphs"] if row["replaced"]}
    indices = {}
    for char in PUNCTUATION:
        _require(char in selected, f"{char!r} has no retained printable-ASCII alias")
        index = selected[char][1]
        _require(index not in replaced, f"{char!r} shares a cell with a reviewed Latin/bracket alias")
        _require(index not in indices.values(), f"{char!r} shares a cell with another punctuation alias")
        indices[char] = index
    font = geninterface_latin.raster_font()
    output = bytearray(base_tpl)
    plane_offset = int.from_bytes(base_tpl[12:16], "big")
    rows, patches = [], []
    for char in PUNCTUATION:
        code, index = selected[char]
        raster, bounds = geninterface_latin.raster_ink(font, char)
        cell, ink, placement, (a, b) = pack_cell(raster, bounds)
        _write_cell(output, plane_offset, index, cell)
        _require(cell.getbbox() == ink and (a, b) == (ink[0], ink[2] - ink[0]),
                 f"{char!r} metric pair does not match its quantized ink")
        before = _source_pair(source, index)
        offset = geninterface_latin.METRICS_OFFSET + index * 2
        rows.append({"character": char, "replaced": True, "cp932_alias": hex(code),
                     "native_index": index, "metric_file_offset": offset,
                     "source_a": before[0], "source_b": before[1], "a": a, "b": b,
                     "advance": b + ADVANCE_PADDING, "ink_bounds": list(ink),
                     "raster_baseline_bounds": list(bounds), "raster_placement": list(placement),
                     "shared_fullwidth_character": bytes((code >> 8, code & 255)).decode("cp932"),
                     "atlas_cell": [index % 32 * CELL, index // 32 * CELL,
                                    index % 32 * CELL + CELL, index // 32 * CELL + CELL],
                     "cell_sha256": project.digest(cell.tobytes())})
        patches.append({"file_offset": hex(offset), "virtual_address": hex(offset + 0x10000),
                        "source_before": bytes(before).hex(), "after": bytes((a, b)).hex(),
                        "character": char, "cp932_alias": hex(code), "native_index": index,
                        "purpose": "GenInterfaceJP Regular ASCII punctuation ink-left/width"})
    manifest = {
        "face": "Gen Interface JP Regular",
        "font_sha256": geninterface_latin.FONT_SHA256,
        "ofl_sha256": geninterface_latin.OFL_SHA256,
        "source_sha256": project.digest(source),
        "base_tpl_sha256": base["source_tpl_sha256"],
        "base_output_tpl_sha256": base["output_tpl_sha256"],
        "base_replacement_count": base["replacement_count"],
        "output_tpl_sha256": project.digest(output),
        "em": geninterface_latin.EM, "baseline": geninterface_latin.BASELINE,
        "native_cell": CELL, "raster_em": geninterface_latin.EM,
        "sampling_border": geninterface_latin.SAMPLING_BORDER,
        "characters": PUNCTUATION, "count": len(PUNCTUATION),
        "excluded": EXCLUDED, "metrics_pointer": METRICS_POINTER,
        "advance_rule": "native quantized ink width + 6, same rule as the reviewed letter cells",
        "method": "Chained on the reviewed 68-cell atlas; R4 nearest quantization; "
                  "full-ink horizontal centring; common Latin baseline; transparent border",
        "unrelated_packed_bits_preserved": True,
        "nonreplacement_punctuation_preserved": True,
        "runtime_accepted": False,
        "glyphs": rows, "patches": patches,
    }
    return bytes(output), manifest


def _source_pair(source, index):
    offset = geninterface_latin.METRICS_OFFSET + index * 2
    return source[offset], source[offset + 1]


_CACHE = {}


def substitute_cached(source=None):
    """Memoize the asset-backed atlas (rasterizing 24 cells is not free)."""
    source = source if source is not None else project.source_bytes()
    key = project.digest(source)
    if _CACHE.get("key") != key:
        tpl, manifest = substitute(source)
        _CACHE.update(key=key, tpl=tpl, manifest=manifest)
    return _CACHE["tpl"], _CACHE["manifest"]


def apply(image, manifest=None, *, source=None):
    """Install the punctuation metric pairs into an assembled executable."""
    source = source if source is not None else project.source_bytes()
    if manifest is None:
        manifest = substitute_cached(source)[1]
    _require(manifest["source_sha256"] == project.digest(source),
             "manifest identifies another source executable")
    result = bytearray(image)
    for patch in manifest["patches"]:
        offset = int(patch["file_offset"], 0)
        before, after = bytes.fromhex(patch["source_before"]), bytes.fromhex(patch["after"])
        _require(result[offset:offset + 2] == before,
                 f"metric pair for {patch['character']!r} differs from the immutable original")
        result[offset:offset + 2] = after
    for patch in manifest["patches"]:
        offset = int(patch["file_offset"], 0)
        _require(bytes(result[offset:offset + 2]) == bytes.fromhex(patch["after"]),
                 f"metric pair for {patch['character']!r} did not stay installed")
    return bytes(result), manifest


def verify(image, tpl, manifest):
    """Prove the executable pairs and the atlas carry exactly this manifest.

    Cells are compared one by one before the whole-file digest so a single
    changed pixel reports which character moved instead of only "TPL differs".
    The digest still runs last, and it is what rejects a TPL whose untouched
    bytes (header padding, other cells) were edited.
    """
    offset = int.from_bytes(tpl[12:16], "big")
    for row in manifest["glyphs"]:
        index = row["native_index"]
        pair = (row["a"], row["b"])
        at = row["metric_file_offset"]
        _require(bytes(image[at:at + 2]) == bytes(pair),
                 f"{row['character']!r} metric pair is absent from the executable")
        x, y = index % 32 * CELL, index // 32 * CELL
        pixels = bytearray()
        for line in range(CELL):
            for column in range(CELL):
                pixels.append(tpl[offset + ((y + line) * PLANE + x + column) * 2] & 15)
        quantized = bytes(value * 17 for value in pixels)
        _require(project.digest(quantized) == row["cell_sha256"],
                 f"{row['character']!r} atlas cell differs from the manifest")
        ink = _ink_box(pixels, CELL)
        _require(list(ink) == row["ink_bounds"] and (ink[0], ink[2] - ink[0]) == pair,
                 f"{row['character']!r} atlas ink does not match its native pair")
        _require(1 <= ink[0] < ink[2] <= CELL - 1 and 1 <= ink[1] < ink[3] <= CELL - 1,
                 f"{row['character']!r} lacks a transparent sampling border")
    _require(project.digest(tpl) == manifest["output_tpl_sha256"],
             "supplied TPL differs from the manifest")
    return {"verified_characters": len(manifest["glyphs"]),
            "advance_rule": manifest["advance_rule"],
            "output_tpl_sha256": manifest["output_tpl_sha256"],
            "runtime_accepted": False}


def _ink_box(pixels, size):
    xs = [column for line in range(size) for column in range(size)
          if pixels[line * size + column]]
    ys = [line for line in range(size) for column in range(size)
          if pixels[line * size + column]]
    if not xs:
        raise ValueError("Punctuation atlas: empty cell")
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def load_report(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)
