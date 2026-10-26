"""Stage a save-caption correction on the tested VWF/capacity image; never deploy.

Preserves every scenario and serialized-data implementation. Previous builds
and manual results remain intact; changed UI code gets a fresh results form.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import struct
import tempfile

import gates
import layout_probe
import native_layout_patch
import project
import save_preview_patch
import save_preview_smoke

INPUT = project.ROOT / "build/vwf-capacity-probe/EBOOT.elf"
INPUT_SHA256 = "d7d9c1decc82b9fa05d5bc3f317c6d0741363c7c53cca5bff22940782b017d86"
OUTPUT = project.ROOT / "build/save-preview-probe"
FORM = project.ROOT / "work/qa/save-preview-results-to-fill.json"
PREVIOUS_FORM = project.ROOT / "work/qa/vwf-results-to-fill.json"


def native_only(original, patched, report):
    """Compare all bytes outside exact code sites, new cave and RX size fields."""
    if len(original) != len(patched):
        raise ValueError("UI-only diagnostic changed the ELF file length")
    phoff = struct.unpack_from(">Q", original, 0x20)[0]
    extension = report["rx_extension"]
    begin, end = extension["file_begin"], extension["file_end"]
    old_end = struct.unpack_from(">Q", original, phoff + 0x20)[0]
    if begin != old_end or not begin <= end <= native_layout_patch.CAVE_END:
        raise ValueError("Save helper does not extend the reviewed active RX tail")
    if any(original[begin:end]):
        raise ValueError("Save helper would overwrite nonzero input padding")
    ranges = [(phoff + 0x20, phoff + 0x30), (begin, end)]
    for site in report["patches"]:
        offset = int(site["file_offset"], 0)
        before, after = bytes.fromhex(site["input_before"]), bytes.fromhex(site["after"])
        if (len(before) != 4 or len(after) != 4 or not 0 <= offset < native_layout_patch.CAVE_START or
                original[offset:offset + 4] != before or patched[offset:offset + 4] != after):
            raise ValueError("Save patch report does not identify its actual instruction")
        ranges.append((offset, offset + 4))
    previous = 0
    left, right = memoryview(original), memoryview(patched)
    for start, stop in sorted(ranges):
        if start > previous and left[previous:start] != right[previous:start]:
            raise ValueError("UI correction changed bytes outside approved native ranges")
        previous = max(previous, stop)
    if left[previous:] != right[previous:]:
        raise ValueError("UI correction changed trailing data or the scenario arena")
    return [{"file_begin": start, "file_end": stop} for start, stop in sorted(ranges)]


def compose_layout(base, addition, patched):
    """Describe the complete VWF + save correction for production fingerprints."""
    combined = copy.deepcopy(base)
    old, extra = combined["rx_extension"], addition["rx_extension"]
    if extra["file_begin"] != old["file_end"]:
        raise ValueError("Native helper extensions are not contiguous")
    combined["input_sha256"] = INPUT_SHA256
    combined["output_sha256"] = project.digest(patched)
    combined["patches"].extend(addition["patches"])
    combined["injected_blocks"].extend(addition["injected_blocks"])
    end = extra["file_end"]
    old.update(file_end=end, new_filesz=end, new_memsz=end,
               size=end - old["file_begin"])
    combined["save_preview_correction"] = addition
    return combined


def main():
    if OUTPUT.exists() or FORM.exists():
        raise ValueError("Existing save-preview diagnostic/results preserved; do not repeat unchanged staging")
    original, base_report = layout_probe.retained_input(INPUT, INPUT_SHA256)
    previous = project.load(PREVIOUS_FORM)
    if previous["growth"]["output_sha256"] != INPUT_SHA256:
        raise ValueError("Previous manual results identify another growth input")
    kit = project.codec()
    patched, addition = save_preview_patch.apply(original)
    ranges = native_only(original, patched, addition)
    smoke = save_preview_smoke.smoke(original, patched, addition)
    payloads = layout_probe.unchanged_scenarios(original, patched, kit)
    combined = compose_layout(base_report["native_layout"], addition, patched)
    accepted, explanation = gates.engine_cutover(patched, patched, combined, kit)
    old_accepted, _ = gates.engine_cutover(original, patched, combined, kit)
    if not accepted or old_accepted:
        raise ValueError("Complete native cutover guard failed to distinguish the save UI correction")
    report = {
        "output": str(OUTPUT / "EBOOT.elf"), "output_sha256": project.digest(patched),
        "source_sha256": native_layout_patch.SOURCE_SHA256,
        "input": INPUT.relative_to(project.ROOT).as_posix(), "input_sha256": INPUT_SHA256,
        "diagnostic_only": True, "native_layout": combined, "save_preview_patch": addition,
        "allowed_native_ranges": ranges, "verified_payloads": payloads,
        "scenario_bytes_identical_to_growth_candidate": True,
        "original_font_unchanged": True, "editable_scripts_modified": False,
        "save_data_modified_by_tool": False, "installed_game_modified_by_tool": False,
        "opening": base_report["opening"], "segment": base_report["segment"],
        "scenario_start_alignment": base_report["scenario_start_alignment"],
        "runtime_verified": False, "production_layout_enabled": False,
        "production_growth_enabled": False,
        "offline_smoke": (OUTPUT / "encoded-smoke.json").relative_to(project.ROOT).as_posix(),
        "results_form": FORM.relative_to(project.ROOT).as_posix(),
        "previous_runtime_observation": "work/qa/probe-observations/save-preview-overflow.json",
        "manual_acceptance": [
            "Manually boot this distinct ELF as TH2_EN_SAVE_UI.elf; preserve all previous files",
            "Open the save/load list and inspect the existing English spare-save caption",
            "Latin spacing is proportional and the excerpt/ellipsis stays inside the row",
            "Existing Japanese captions, thumbnails, dates and selection remain intact",
            "Full dialogue/backlog and saved data are not shortened or replaced",
            "Record only observed new-build results; older successful save loading remains historical evidence"
        ],
        "limits": [
            "Software instruction replay is not native FP/GPU/menu runtime acceptance",
            "Preview elision changes only a temporary display excerpt, not stored or translated text",
            "No full-game window/pagination/branching or production acceptance follows from staging"
        ],
    }
    # Preserve the already-tested opening artifact and its attributed results.
    # The growth artifact now has changed native UI code, so its new checks are
    # unpassed; the old user results remain linked, never silently repinned.
    form = {"opening": copy.deepcopy(previous["opening"]),
            "growth": {"output_sha256": report["output_sha256"], "tester": "",
                       "rpcs3_version": "", "tested_at": "", "scene": "", "notes": "",
                       "checks": {name: None for name in gates.CHECKS["growth"]}, "screenshots": []},
            "previous_growth_results": PREVIOUS_FORM.relative_to(project.ROOT).as_posix()}
    with tempfile.TemporaryDirectory(prefix=".save-ui-stage-", dir=project.ROOT / "build") as temporary:
        stage = Path(temporary)
        (stage / "EBOOT.elf").write_bytes(patched)
        project.save(stage / "EBOOT.report.json", report)
        project.save(stage / "manifest.json", report)
        project.save(stage / "encoded-smoke.json", smoke)
        shutil.move(str(stage), str(OUTPUT))
    project.save(FORM, form)
    print(json.dumps({"output": report["output"], "sha256": report["output_sha256"],
                      "verified_payloads": payloads, "native_cutover_guard": explanation,
                      "results_form": report["results_form"], "runtime_verified": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"ERROR: {error}")
