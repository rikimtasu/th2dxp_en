"""Report pre-translation gates; accept manual QA evidence, never launch an emulator."""
import argparse
import json
from pathlib import Path
import struct

from PIL import Image
import project
import assets
import native_layout_patch
import scenario_source

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {
    "opening": ["cold_boot", "marker_visible", "latin_glyphs", "no_clipping"],
    "growth": ["cold_boot", "page_controls", "backlog", "save_load", "save_preview"],
    "windows": ["cold_boot", "growth_marker_visible", "no_clipping", "name_substitution",
                "punctuation", "page_height", "choices", "branching", "unrelated_scene",
                "story_state", "skip_after_long_text", "long_text_save_load",
                "descenders", "word_wrapping", "ui_title", "ui_options", "ui_save_load",
                "ui_name_entry", "ui_calendar", "ui_maps", "ui_visual_music",
                "ui_credits", "ui_readability", "backlog"],
}
ARTIFACTS = {
    "opening": ROOT / "build/vwf-probe/EBOOT.elf",
    "growth": ROOT / "build/save-preview-probe/EBOOT.elf",
    "windows": ROOT / "build/gen-latin-reload-probe/EBOOT.elf",
}
EVIDENCE = ROOT / "work/qa/manual-evidence.json"


def ui_asset_info():
    """Bind the current native UI geometry to its exact staged texture archive."""
    root = ARTIFACTS["windows"].parent
    manifest = project.load(root / "manifest.json")
    if project.digest(ARTIFACTS["windows"].read_bytes()) != manifest["output_sha256"]:
        raise ValueError("Staged UI ELF differs from its paired manifest")
    path = root / "assets/data.sdat"
    expected = manifest["ui_archive"]["sha256"]
    if assets.sha(path) != expected:
        raise ValueError("Staged UI archive differs from its paired manifest")
    return {"path": path, "sha256": expected, "elf_sha256": manifest["output_sha256"]}


def read_evidence(path):
    evidence = project.load(path)
    for kind, checks in CHECKS.items():
        row = evidence.get(kind)
        if not isinstance(row, dict):
            raise ValueError(f"Missing {kind} manual run")
        if row.get("output_sha256") != project.digest(ARTIFACTS[kind].read_bytes()):
            raise ValueError(f"{kind}: manual run does not identify the current staged build")
        for field in ("tester", "rpcs3_version", "tested_at", "scene", "notes"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"{kind}: missing manual {field}")
        if not isinstance(row.get("checks"), dict) or any(row["checks"].get(check) is not True for check in checks):
            raise ValueError(f"{kind}: required manual checks have not all passed")
        if kind == "windows" and row.get("data_sdat_sha256") != ui_asset_info()["sha256"]:
            raise ValueError("windows: manual run does not identify the paired UI archive")
        screenshots = row.get("screenshots")
        if not isinstance(screenshots, list) or not screenshots:
            raise ValueError(f"{kind}: no screenshots supplied")
        for filename in screenshots:
            image = Path(filename)
            if not image.is_absolute():
                image = ROOT / image
            with Image.open(image) as opened:
                opened.verify()
    return evidence


def engine_cutover(image, staged, native, kit):
    """Require the entire correction and real all-scenario appended capacity.

    This is a code/container check, not manual runtime acceptance. Kept
    independent of the production path so staging can exercise both outcomes.
    """
    if not native_layout_patch.native_code_matches(image, staged, native):
        return False, "Complete native VWF correction is absent or differs from the staged diagnostic"
    phoff = struct.unpack_from(">Q", image, 0x20)[0]
    segment = struct.unpack_from(">IIQQQQQQ", image, phoff + 3 * 56)
    kind, flags, offset, address, physical, file_size, memory_size, alignment = segment
    if (kind != 1 or flags != 6 or offset < 6596336 or offset % 0x10000 or
            address < 0xA30000 or address % 0x10000 or physical != address or
            not file_size or file_size != memory_size or offset + file_size > len(image) or
            address + memory_size > 0x100000000 or alignment != 0x10000):
        return False, "Original-alignment appended scenario segment has not been adopted"
    scanned = scenario_source.scan(image, kit)
    if len(scanned) != 1884 or any(
            entry.file_offset % 64 or
            not address <= entry.data_ptr < entry.data_ptr + entry.comp_size_table <= address + file_size
            for entry, *_ in scanned):
        return False, "Complete scenario allocation does not use the validated appended segment"
    return True, "Entire staged native correction and all 1,884 scenarios use appended 64-byte allocations; manual evidence is separate"


def status():
    meta = project.baseline()
    source = project.source_bytes()
    kit = project.codec()
    scanned = scenario_source.scan(source, kit)
    expected = {entry.json_filename for entry, _, _, _ in scanned}
    declared = {entry["json_filename"] for entry in meta["entries"]}
    if expected != declared:
        raise ValueError("Baseline does not cover the entire raw scenario index")
    # Structural/encoding validation is independent of the separately reported
    # manual and production-engine gates; full-length work must be inspectable.
    project.validate(project.SCRIPTS, meta, allow_growth=True)
    rows = [{"gate": "complete_extraction", "state": "passed", "evidence": f"{len(scanned)} indexed scenarios, no silent skips"}]
    font = ROOT / "work/assets/font-report.json"
    fonts_ok = font.exists()
    if fonts_ok:
        report = project.load(font)
        for row in report["font_candidates"]:
            asset = ROOT / "work/assets/fonts" / row["name"]
            fonts_ok = fonts_ok and project.digest(asset.read_bytes()) == row["sha256"]
            fonts_ok = fonts_ok and bool(row["images"]) and all((ROOT / image).exists() for image in row["images"])
    rows.append({"gate": "asset_font_recovery", "state": "passed" if fonts_ok else "blocked",
                 "evidence": "Recovered original font atlases; runtime glyph mapping/advance widths are a separate manual gate"})
    production = ROOT / "build/english/EBOOT.elf"
    # Long text also needs opacity, VM scratch and bounded checkpoint fixes.
    # Accepted older controls remain attributed to their original short run.
    try:
        ui_archive = ui_asset_info()
        ui_ok, ui_note = True, str(ui_archive["path"].relative_to(ROOT))
    except (OSError, ValueError, KeyError) as error:
        ui_archive = None
        ui_ok, ui_note = False, str(error)
    native_manifest = ARTIFACTS["windows"].parent / "manifest.json"
    production_ok = False
    production_note = "Production or supported native-layout diagnostic is not staged"
    if production.exists() and ARTIFACTS["windows"].exists() and native_manifest.exists():
        staged = ARTIFACTS["windows"].read_bytes()
        manifest = project.load(native_manifest)
        production_ok, production_note = engine_cutover(
            production.read_bytes(), staged, manifest["native_layout"], kit)
        if production_ok and (ui_archive is None or not (production.parent / "data.sdat").is_file()
                              or assets.sha(production.parent / "data.sdat") != ui_archive["sha256"]):
            production_ok = False
            production_note = "Native UI code requires the exact paired production data.sdat"
    rows.append({"gate": "production_native_layout_and_capacity_cutover",
                 "state": "passed" if production_ok else "blocked", "evidence": production_note})
    for kind in CHECKS:
        manifest = ARTIFACTS[kind].parent / "manifest.json"
        okay = ARTIFACTS[kind].exists() and manifest.exists()
        if okay:
            report = project.load(manifest)
            wanted = report["output_sha256"]
            okay = wanted == project.digest(ARTIFACTS[kind].read_bytes())
        rows.append({"gate": f"{kind}_diagnostic", "state": "passed" if okay else "blocked",
                     "evidence": str(manifest.relative_to(ROOT))})
    rows.append({"gate": "paired_ui_archive_diagnostic", "state": "passed" if ui_ok else "blocked",
                 "evidence": ui_note})
    try:
        read_evidence(EVIDENCE)
        manual = {"gate": "manual_runtime_layout_and_growth", "state": "passed", "evidence": str(EVIDENCE.relative_to(ROOT))}
    except (OSError, ValueError, KeyError) as error:
        manual = {"gate": "manual_runtime_layout_and_growth", "state": "blocked", "evidence": str(error)}
    rows.append(manual)
    report = {"bulk_translation_allowed": all(row["state"] == "passed" for row in rows), "gates": rows,
              "emulator_launched_by_tool": False,
              "publication_note": "Ittaku reuse rights and release packaging remain separate publication requirements"}
    project.save(ROOT / "work/gates.json", report)
    print(json.dumps(report, indent=2))
    return report


def template(path):
    report = {}
    for kind, checks in CHECKS.items():
        report[kind] = {"output_sha256": project.digest(ARTIFACTS[kind].read_bytes()),
                        "tester": "", "rpcs3_version": "", "tested_at": "", "scene": "", "notes": "",
                        "checks": {check: None for check in checks}, "screenshots": []}
        if kind == "windows":
            report[kind]["data_sdat_sha256"] = ui_asset_info()["sha256"]
    path = path if path.is_absolute() else ROOT / path
    if path.exists():
        raise ValueError("Existing manual results form left untouched")
    project.save(path, report)
    print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("check", help="Exit nonzero until all bulk-translation prerequisites have evidence")
    form = commands.add_parser("template", help="Write an explicitly unpassed manual results form")
    form.add_argument("--output", type=Path, default=Path("work/qa/gen-latin-reload-results-to-fill.json"))
    record = commands.add_parser("record", help="Validate and import the user's actual manual results")
    record.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.command == "template":
        template(args.output)
    elif args.command == "record":
        result = read_evidence(args.file)
        project.save(EVIDENCE, result)
        print("Recorded manual evidence for the exact current probe builds")
    else:
        report = status()
        if args.command == "check" and not report["bulk_translation_allowed"]:
            return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"ERROR: {error}")
