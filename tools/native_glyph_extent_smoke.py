"""Source-bound glyph sampling evidence, not a glyph repair or GPU acceptance.

smoke(source, image, native) executes the retained help/dialogue glyph paths and
compares their sampled original pixels with source geometry. preview(report,
screenshot=None) returns an offline Pillow image; neither function writes files.
The reported incomplete-g shape remains unresolved: do not interpret complete
source-bitmap coverage as visual approval or invent another endpoint offset.
"""
from __future__ import annotations

import io
import math
import struct

from PIL import Image, ImageDraw

import native_layout_patch
import native_layout_smoke
import native_typography_smoke
import native_ui_smoke
import project

FONT_SHA256 = "fa9db1b669a9456747eae576d2647b0bb1a79a162ebf6999a7503eb5d293a184"
TPL_SHA256 = "ae3fda1bc50d5457326a6e1966c17a1f8d18469d4e425f623768604a62e5fb95"
GLYPHS = b"gjpqy"


def require(condition, message):
    if not condition:
        raise ValueError("Glyph extent replay: " + message)


def original_atlas():
    """Independently bind the exported plane to every packed source R nibble."""
    root = project.ROOT / "work/assets/fonts/_initial"
    png, tpl = (root / "font.0.R.png").read_bytes(), (root / "font.tpl").read_bytes()
    require(project.digest(png) == FONT_SHA256 and project.digest(tpl) == TPL_SHA256,
            "original font PNG/TPL differs from the pinned assets")
    atlas = Image.open(io.BytesIO(png)).convert("L")
    require(atlas.size == (1536, 1536), "main font plane dimensions changed")
    require(struct.unpack_from(">I", tpl)[0] == 2, "source font texture count changed")
    # The original non-power-of-two A4R4G4B4 record is linear, pitch3072.
    raw0, raw1, pitch = struct.unpack_from(">HHH", tpl, 4)
    require((raw0, raw1, pitch) == (1536, 1536, 3072)
            and tpl[10] == 0xA3, "source packed font record changed")
    offset = struct.unpack_from(">I", tpl, 12)[0]
    pixels = atlas.tobytes()
    require(len(tpl) >= offset + len(pixels) * 2, "source packed plane is truncated")
    require(all(pixels[index] == ((tpl[offset + index * 2] & 15) * 17)
                for index in range(len(pixels))), "exported R plane differs from packed source nibbles")
    return atlas


def glyph_facts(source, atlas, byte):
    metrics = native_layout_smoke.SourceMetrics(source)
    code = struct.unpack_from(">H", source, 0x2514B0 + 2 * (byte - 32))[0]
    index, found = 0, False
    for first, last in metrics.ranges:
        if first <= code <= last:
            index += code - first
            found = True
            break
        index += last - first + 1
    require(found and index < 1024, "fixture does not select the original R plane")
    x, y = index % 32 * 48, index // 32 * 48
    cell = atlas.crop((x, y, x + 48, y + 48))
    rows = [sum(cell.crop((0, row, 48, row + 1)).tobytes()) for row in range(48)]
    bearing, width = metrics.main_pair(byte)
    require(cell.getbbox() == (bearing, cell.getbbox()[1], bearing + width, cell.getbbox()[3]),
            "original metrics no longer bound their source ink")
    return {"character": chr(byte), "cp932": hex(code), "glyph_index": index,
            "texture_record": 0, "plane": "R", "native_alpha_remap": "0x5655",
            "atlas_cell": [x, y, x + 48, y + 48], "bearing_width": [bearing, width],
            "original_ink_bbox": list(cell.getbbox()), "row_alpha_mass": rows,
            "original_rows_45_47_alpha_hex": [cell.crop((0, row, 48, row + 1)).tobytes().hex()
                                               for row in (45, 46, 47)],
            "cell_sha256": project.digest(cell.tobytes()),
            "direct_ascii_alternate_in_source_ranges": any(a <= byte <= b for a, b in metrics.ranges)}


def vertices(cpu, count):
    cpu.r[3], cpu.r[30], cpu.r[5], cpu.r[6] = cpu.VERTICES, cpu.FONT, count, cpu.QUEUE
    cpu.pc = 0x1B47C
    cpu.execute_until(0x1B69C)
    return [[struct.unpack(">hhIHH", cpu.read(cpu.VERTICES + index * 48 + corner * 12, 12))
             for corner in range(4)] for index in range(count)]


def sampled(atlas, quad, cell, *, uv_bias=0.0):
    """Bilinear normalized-edge model: UV is texel-edge, centers are n+0.5.

    This deliberately does not clamp to the glyph cell: neighboring-cell reads
    must be exposed, not hidden by Pillow crop/resize's implicit edge extension.
    Pixel-center rasterization and bilinear filtering are explicit assumptions,
    not a replay of the RSX fragment program, alpha test, blend or derivatives.
    """
    left, right = min(v[0] for v in quad), max(v[0] for v in quad)
    top, bottom = min(v[1] for v in quad), max(v[1] for v in quad)
    u0, u1 = min(v[3] for v in quad), max(v[3] for v in quad)
    v0, v1 = min(v[4] for v in quad), max(v[4] for v in quad)
    require(right > left and bottom > top, "empty native glyph quad")
    pixels = atlas.load()
    output = Image.new("L", (right - left, bottom - top))
    target = output.load()
    support_x, support_y, row_mass, neighbor_alpha = set(), set(), {}, 0.0
    for y in range(bottom - top):
        vv = v0 + (y + 0.5) * (v1 - v0) / (bottom - top) - 0.5 + uv_bias
        vy, fy = math.floor(vv), vv - math.floor(vv)
        for x in range(right - left):
            uu = u0 + (x + 0.5) * (u1 - u0) / (right - left) - 0.5 + uv_bias
            ux, fx = math.floor(uu), uu - math.floor(uu)
            alpha = 0.0
            for dy, wy in ((0, 1 - fy), (1, fy)):
                for dx, wx in ((0, 1 - fx), (1, fx)):
                    weight = wx * wy
                    if weight <= 0:
                        continue
                    ax, ay = ux + dx, vy + dy
                    require(0 <= ax < atlas.width and 0 <= ay < atlas.height,
                            "sample outside the actual texture")
                    support_x.add(ax)
                    support_y.add(ay)
                    value = pixels[ax, ay] * weight
                    alpha += value
                    row_mass[ay] = row_mass.get(ay, 0.0) + value
                    if not (cell[0] <= ax < cell[2] and cell[1] <= ay < cell[3]):
                        neighbor_alpha += value
            target[x, y] = min(255, max(0, round(alpha)))
    outside = [min(support_x) < cell[0], max(support_x) >= cell[2],
               min(support_y) < cell[1], max(support_y) >= cell[3]]
    return {"screen_bounds": [left, top, right, bottom], "uv_edges": [u0, v0, u1, v1],
            "pixel_center": 0.5, "uv_bias": uv_bias, "neighbor_alpha_mass": neighbor_alpha,
            "sample_support": [min(support_x), min(support_y), max(support_x) + 1, max(support_y) + 1],
            "neighbor_cell_sampled": any(outside), "sampled_ink_bbox": list(output.getbbox()),
            "sampled_last_ink_row_mass": row_mass.get(cell[1] + 46, 0.0),
            "sampled_alpha_sha256": project.digest(output.tobytes()),
            "sampled_size": list(output.size), "sampled_alpha_hex": output.tobytes().hex()}


def smoke(source, image, native):
    require(project.digest(source) == native_layout_patch.SOURCE_SHA256,
            "immutable source is not the reviewed executable")
    require(native_layout_patch.native_code_matches(image, image, native),
            "corrected image differs from its complete native manifest")
    atlas = original_atlas()
    facts = [glyph_facts(source, atlas, byte) for byte in GLYPHS]
    scale = struct.unpack_from(">f", source, 0x87FB4 - 0x10000)[0]
    require(scale == 0.5833333134651184, "actual name-help scale changed")
    # Source-proven plane selection: page0 fetch at1B420/1B438; record0's
    # first cloned descriptor remaps R into alpha at1CF34/1CF4C.
    for pc, word in ((0x1B420, 0xA1050002), (0x1B438, 0x7CC6402E),
                     (0x1CF34, 0x38A05655), (0x1CF4C, 0x90A40010)):
        require(struct.unpack_from(">I", source, pc - 0x10000)[0] == word,
                f"source texture-plane selector changed at {pc:#x}")
        require(image[pc - 0x10000:pc - 0x10000 + 4] == source[pc - 0x10000:pc - 0x10000 + 4],
                f"texture-plane selector was modified at {pc:#x}")
    cases = []
    for name, factor in (("name_help_actual_scale", scale), ("dialogue_48px", 1.0)):
        if name.startswith("name_help"):
            old_cpu = native_typography_smoke.GlyphCPU(source, source, None)
            new_cpu = native_typography_smoke.GlyphCPU(source, image, native)
            old_records, _ = native_ui_smoke.centered_help(old_cpu, GLYPHS, factor)
            new_records, _ = native_ui_smoke.centered_help(new_cpu, GLYPHS, factor)
            old_quads, new_quads = vertices(old_cpu, len(old_records)), vertices(new_cpu, len(new_records))
            path = ["0x1c9f0", "0x1c178", "0x1bcb8", "0x1b47c"]
        else:
            old_cpu = native_ui_smoke.DialogueCPU(source, source, None)
            new_cpu = native_ui_smoke.DialogueCPU(source, image, native)
            _, old_records, old_quads = old_cpu.dialogue(GLYPHS, factor)
            _, new_records, new_quads = new_cpu.dialogue(GLYPHS, factor)
            path = ["0x598dc", "0x59338", "0x1be28", "0x1bcb8", "0x1b47c"]
        glyphs = []
        for fact, old_record, record, old_quad, quad in zip(facts, old_records, new_records, old_quads, new_quads):
            cell = fact["atlas_cell"]
            require(record[1] == 0 and list(record[6:8]) == cell[:2], "actual producer selected another glyph/page")
            require(list(record[8:10]) == [cell[2] - 1, cell[3] - 1], "producer clipped original glyph texels")
            require(record[0:2] == old_record[0:2] and record[6:] == old_record[6:],
                    "source glyph selection/color/scale protocol changed")
            require(max(v[0] for v in quad) == record[4] + 1
                    and max(v[1] for v in quad) == record[5] + 1,
                    "native screen edge truncates the requested cell")
            before, after = sampled(atlas, old_quad, cell), sampled(atlas, quad, cell)
            require(after["uv_edges"] == cell, "native UV edges truncate the original atlas cell")
            require(not after["neighbor_cell_sampled"], "native sampling includes a neighboring atlas cell")
            require(after["sampled_last_ink_row_mass"] > 0, "original final descender row is unsampled")
            sensitivity = []
            for bias in (-0.5, 0.5):
                alternative = sampled(atlas, quad, cell, uv_bias=bias)
                sensitivity.append({key: value for key, value in alternative.items()
                                    if key not in ("sampled_alpha_hex", "sampled_size")})
            glyphs.append({"character": fact["character"], "queue": list(record),
                           "source": before, "retained_endpoint_correction": after,
                           "unverified_half_texel_shader_bias_sensitivity": sensitivity})
        cases.append({"name": name, "scale": factor, "path": path, "glyphs": glyphs,
                      "executed_source_instruction_count": len(old_cpu.executed),
                      "executed_image_instruction_count": len(new_cpu.executed)})
    return {"source_sha256": project.digest(source), "image_sha256": project.digest(image),
            "original_font_png_sha256": FONT_SHA256, "original_font_tpl_sha256": TPL_SHA256,
            "texture_record": {"dimensions": [1536, 1536], "format": "A4R4G4B4",
                               "wrap_s": 1, "wrap_t": 1, "filter_mode": 1, "mip_flag": 1,
                               "native_alpha_remap_sites": ["0x1cf34", "0x1cf4c"],
                               "page_lookup_sites": ["0x1b420", "0x1b438"],
                               "actual_gpu_filter_alpha_and_lod_unverified": True},
            "glyph_facts": facts, "cases": cases, "new_native_correction_applied": False,
            "user_visible_shape_corrected": False, "runtime_accepted": False,
            "finding": "Retained paths sample the complete original descender. No additional source-supported geometry offset established; reported visual defect remains open.",
            "limitations": ["Finite encoded PPC/FP/VMX caller/queue/vertex replay, not RPCS3 or GPU execution.",
                            "Centered-help line tokenization and dialogue producer live inputs use existing bounded fixtures.",
                            "Texture resource objects, allocation and GPU reservation are synthetic boundaries.",
                            "Pillow preview explicitly models bilinear pixel-center sampling; RSX shader, alpha/blend, mip/LOD and pixel-center convention are not executed.",
                            "R selection is source-bound to native descriptor remap; no GPU texture readback was obtained.",
                            "Complete original bitmap coverage does not establish that its tail shape meets the user's requirement.",
                            "A different tail design requires authorization to repair glyph assets or change the original-font boundary."]}


def preview(report, screenshot=None):
    """Return a labeled offline original/source/retained comparison for review.

    screenshot may be a Pillow image or filename. Its crop is the actual reported
    name-help reading-g region, not a claim of pixel-exact shader reproduction.
    """
    atlas = original_atlas()
    canvas = Image.new("RGB", (1000, 740), (28, 32, 36))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 10), "Original assets only. No new glyph fix. CPU bilinear model, NOT GPU output.", fill="white")
    for index, fact in enumerate(report["glyph_facts"]):
        x = 12 + index * 190
        draw.text((x, 40), f"{fact['character']} index{fact['glyph_index']} R ink{fact['original_ink_bbox']}", fill="white")
        cell = atlas.crop(tuple(fact["atlas_cell"]))
        canvas.paste(cell.convert("RGB").resize((144, 144), Image.Resampling.NEAREST), (x, 62))
        for row, case in enumerate(report["cases"]):
            glyph = case["glyphs"][index]
            for column, key in enumerate(("source", "retained_endpoint_correction")):
                result = glyph[key]
                tile = Image.frombytes("L", tuple(result["sampled_size"]), bytes.fromhex(result["sampled_alpha_hex"]))
                factor = min(72 / tile.width, 84 / tile.height)
                size = (round(tile.width * factor), round(tile.height * factor))
                canvas.paste(tile.convert("RGB").resize(size, Image.Resampling.NEAREST), (x + column * 82, 240 + row * 120))
            draw.text((x, 220 + row * 120), case["name"], fill="white")
            draw.text((x, 325 + row * 120), "source      retained", fill="white")
    if screenshot is not None:
        shot = screenshot if isinstance(screenshot, Image.Image) else Image.open(screenshot)
        crop = shot.crop((825, 215, 849, 244)).convert("RGB")
        canvas.paste(crop.resize((120, 145), Image.Resampling.NEAREST), (500, 550))
        draw.text((12, 510), "Reported screenshot, reading-g crop (original pixels, nearest-neighbor enlarged):", fill="white")
    draw.text((12, 720), "Full original ink coverage is not visual acceptance. User-reported incomplete tail remains unresolved.", fill="white")
    return canvas
