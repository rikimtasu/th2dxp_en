"""Stage original-font VWF A/B and full-text capacity diagnostics; never deploy.

Uses the preserved terminal-flush and capacity inputs, not editable scripts.
Encoded instruction smoke runs once before either new ELF is published.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

import native_layout_patch
import project
import scenario_source

FLOW = project.ROOT / "build/native-flow-probe/EBOOT.elf"
CAPACITY = project.ROOT / "build/capacity-probe/EBOOT.elf"
FLOW_SHA256 = "b8706df38955e3a98f71dff02ed6f634c64c6f92efb01c3c68ae2a82b1c5ecc3"
CAPACITY_SHA256 = "401c656a719c67cf40b51b2b3fac84b0efaf8824193c5c9df21716aca2f8d485"
TARGETS = {"opening": project.ROOT / "build/vwf-probe",
           "growth": project.ROOT / "build/vwf-capacity-probe"}


def retained_input(path, expected_hash):
    image = path.read_bytes()
    report = project.load(path.with_suffix(".report.json"))
    if project.digest(image) != expected_hash or report["output_sha256"] != expected_hash:
        raise ValueError(f"Preserved diagnostic input differs: {path}")
    if report["source_sha256"] != native_layout_patch.SOURCE_SHA256:
        raise ValueError("Preserved diagnostic refers to another source revision")
    return image, report


def unchanged_scenarios(before, after, kit):
    """Read actual output mappings/chunks and compare every payload to its input."""
    previous = scenario_source.scan(before, kit)
    current = scenario_source.scan(after, kit)
    if len(previous) != len(current) or len(current) != 1884:
        raise ValueError("Native correction changed complete scenario coverage")
    for old, new in zip(previous, current):
        a, old_payload, old_name, old_chunks = old
        b, new_payload, new_name, new_chunks = new
        if a != b or old_name != new_name or old_chunks != new_chunks or old_payload != new_payload:
            raise ValueError("Native-only correction changed a scenario, mapping or container")
    return len(current)


def main():
    for path in TARGETS.values():
        if path.exists():
            raise ValueError(f"Existing diagnostic preserved; do not repeat an unchanged build: {path}")
    source = project.source_bytes()
    kit = project.codec()
    flow, flow_report = retained_input(FLOW, FLOW_SHA256)
    capacity, capacity_report = retained_input(CAPACITY, CAPACITY_SHA256)
    flow_manifest = project.load(FLOW.parent / "manifest.json")
    if flow_manifest["sha256"] != FLOW_SHA256 or len(flow_manifest["profile"]["records"]) != 16:
        raise ValueError("Preserved F01-F16 manifest differs")
    opening = capacity_report["opening"]
    if (opening["full_english_bytes"] <= opening["original_text_bytes"] or
            opening["scenario_growth_bytes"] <= 0 or
            "".join(opening["fragments"]) != opening["complete_english"] or
            len(opening["complete_english"].encode("cp932", errors="strict")) != opening["full_english_bytes"]):
        raise ValueError("Capacity input does not retain the complete grown English sentence")
    reviewed = project.ROOT / capacity_report["reference_review"]
    if project.digest(reviewed.read_bytes()) != capacity_report["reference_review_sha256"]:
        raise ValueError("Capacity input's source/context review changed")

    vwf, native = native_layout_patch.apply(flow)
    # No semantic-PC overrides: this executes the encoded patch in bounded
    # synthetic RAM with explicitly modeled libc/span-construction boundaries.
    import native_layout_smoke
    smoke = native_layout_smoke.smoke(vwf, native)
    grown_vwf, grown_native = native_layout_patch.apply(capacity)
    if not native_layout_patch.native_code_matches(grown_vwf, vwf, native):
        raise ValueError("Growth diagnostic does not use the identical native correction")
    counts = {"opening": unchanged_scenarios(flow, vwf, kit),
              "growth": unchanged_scenarios(capacity, grown_vwf, kit)}
    import gates
    growth_ready, growth_note = gates.engine_cutover(grown_vwf, vwf, native, kit)
    native_only_ready, native_only_note = gates.engine_cutover(vwf, vwf, native, kit)
    old_ready, old_note = gates.engine_cutover(flow, vwf, native, kit)
    if not growth_ready or native_only_ready or old_ready:
        raise ValueError("Production guard failed to distinguish complete native/capacity cutover")
    smoke["production_guard"] = {
        "full_native_and_growth_accepted": growth_note,
        "native_without_growth_rejected": native_only_note,
        "old_terminal_only_rejected": old_note,
    }
    common = {
        "source_sha256": project.digest(source), "diagnostic_only": True,
        "original_font_unchanged": True, "editable_scripts_modified": False,
        "runtime_verified": False, "production_layout_enabled": False,
        "production_growth_enabled": False,
        "offline_smoke": "build/vwf-probe/encoded-smoke.json",
        "limits": ["Software instruction replay is not native FP, GPU, VM or emulator execution",
                   "Full-scene layout, page height, name/choice windows and navigation require manual evidence",
                   "Growth additionally requires loader, branching and save/load acceptance",
                   "No production cutover or bulk translation approval follows from offline success"],
    }
    reports = {}
    reports["opening"] = {
        **common, "output": str(TARGETS["opening"] / "EBOOT.elf"),
        "output_sha256": project.digest(vwf), "input_sha256": FLOW_SHA256,
        "input": FLOW.relative_to(project.ROOT).as_posix(),
        "native_layout": native, "verified_payloads": counts["opening"],
        "script": flow_manifest["script"], "source_name": flow_manifest["source_name"],
        "profile": flow_manifest["profile"], "expected_first_page": flow_manifest["expected_first_page"],
        "scenario_bytes_identical_to_terminal_probe": True,
        "original_wait_page_controls_preserved": True,
        "manual_acceptance": ["F01 full alphabet and F02 appear before advancing",
                              "F05 full sentence/F06 and F07 full alphabet/F08 are retained",
                              "F09 and F11 no longer collide with their untouched Japanese continuations",
                              "F02/F08 flowers follow visible text rather than covering letters",
                              "No clipping, lost fragments, extra waits, backlog or navigation corruption",
                              "Unobserved name/choice/punctuation/save checks remain unpassed"],
    }
    reports["growth"] = {
        **common, "output": str(TARGETS["growth"] / "EBOOT.elf"),
        "output_sha256": project.digest(grown_vwf), "input_sha256": CAPACITY_SHA256,
        "input": CAPACITY.relative_to(project.ROOT).as_posix(),
        "native_layout": grown_native, "verified_payloads": counts["growth"],
        "opening": opening, "segment": capacity_report["segment"],
        "scenario_start_alignment": capacity_report["scenario_start_alignment"],
        "original_scenario_arena_retained": True,
        "scenario_bytes_identical_to_capacity_probe": True,
        "bytecode_controls_verified": capacity_report["bytecode_controls_verified"],
        "reference_review": capacity_report["reference_review"],
        "reference_review_sha256": capacity_report["reference_review_sha256"],
        "manual_acceptance": ["Test only after the VWF opening diagnostic passes",
                              "Cold boot reaches ToHeart2 New Game using the appended segment",
                              "Complete alarm-clock English sentence renders without clipping/overlap",
                              "Page/wait, backlog, branching, unrelated scenes and save/load remain intact"],
    }
    # Stage all related files before publishing new directories; never replace
    # previous diagnostics, manual forms, production or installed game files.
    with tempfile.TemporaryDirectory(prefix=".vwf-stage-", dir=project.ROOT / "build") as temporary:
        root = Path(temporary)
        for kind, image in (("opening", vwf), ("growth", grown_vwf)):
            directory = root / kind
            directory.mkdir()
            (directory / "EBOOT.elf").write_bytes(image)
            project.save(directory / "EBOOT.report.json", reports[kind])
            project.save(directory / "manifest.json", reports[kind])
        project.save(root / "opening/encoded-smoke.json", smoke)
        for kind, target in TARGETS.items():
            shutil.move(str(root / kind), str(target))
    print(json.dumps({kind: {"output": row["output"], "sha256": row["output_sha256"],
                            "verified_payloads": row["verified_payloads"], "runtime_verified": False}
                      for kind, row in reports.items()}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"ERROR: {error}")
