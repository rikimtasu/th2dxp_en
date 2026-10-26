"""Replace only source-derived Latin metric pairs; no lookup/cache ABI changes."""
from __future__ import annotations

import copy
from functools import lru_cache

import geninterface_latin
import native_layout_patch
import project


@lru_cache(maxsize=1)
def metric_manifest(source):
    """Exact reviewed alias/face-derived sites, never an arbitrary data interval."""
    _, font = geninterface_latin.replacement(source)
    patches = []
    for glyph in font["glyphs"]:
        if not glyph["replaced"]:
            continue
        patches.append({"file_offset": hex(glyph["metric_file_offset"]),
                        "virtual_address": hex(glyph["metric_file_offset"] + 0x10000),
                        "source_before": bytes((glyph["source_a"], glyph["source_b"])).hex(),
                        "after": bytes((glyph["a"], glyph["b"])).hex(),
                        "character": glyph["character"], "cp932_alias": glyph["cp932_alias"],
                        "native_index": glyph["native_index"],
                        "purpose": "GenInterfaceJP Regular source-alias Latin/bracket ink-left/width"})
    return {"source_sha256": project.digest(source),
            "font_sha256": font["font_sha256"], "ofl_sha256": font["ofl_sha256"],
            "source_tpl_sha256": font["source_tpl_sha256"],
            "output_tpl_sha256": font["output_tpl_sha256"],
            "em": font["em"], "baseline": font["baseline"],
            "native_cell": font["native_cell"], "raster_em": font["raster_em"],
            "sampling_border": font["sampling_border"],
            "bracket_policy": font["bracket_policy"],
            "replacement_characters": font["replacement_characters"],
            "replacement_count": font["replacement_count"],
            "shared_fullwidth_aliases": font["shared_fullwidth_aliases"],
            "metrics_pointer": "0x257038", "patches": patches}


def manifest_matches(manifest):
    """Bind allowed offsets AND before/after data to immutable inputs and face."""
    return manifest == metric_manifest(project.source_bytes())


def apply(image, native):
    if not native_layout_patch.native_code_matches(image, image, native):
        raise ValueError("Latin metric patch requires complete preceding native image")
    if native.get("latin_font"):
        raise ValueError("Latin metric patch is already present")
    source = project.source_bytes()
    manifest = metric_manifest(source)
    result = bytearray(image)
    for patch in manifest["patches"]:
        offset = int(patch["file_offset"], 0)
        if result[offset:offset + 2] != bytes.fromhex(patch["source_before"]):
            raise ValueError("Latin metric source pair differs from original")
        result[offset:offset + 2] = bytes.fromhex(patch["after"])
    report = copy.deepcopy(native)
    report["latin_font"] = copy.deepcopy(manifest)
    report["fonts_unchanged"] = False
    report["geometry_counter_unit"] = "main-font design pixels; GenInterfaceJP Latin ink width+6"
    if "ui_graphic_layout" in report:
        report["ui_graphic_layout"]["font_assets_unchanged"] = False
    report["output_sha256"] = project.digest(result)
    return bytes(result), report
