"""Reproduce the retained failed pagination-only diagnostic, not the QA target.

Never deploy, launch a game, overwrite an earlier diagnostic, or record a
runtime pass. Production assembly remains separately guarded by real evidence.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile

import gates
import native_layout_patch
import native_layout_smoke
import native_pagination_patch
import native_pagination_smoke
import production_engine
import project
import scenario_source

INPUT = project.ROOT / "build/windows-height-probe/EBOOT.elf"
INPUT_SHA256 = "9c0b32374aa597dc9d6de58db8a4795ff28c05dc85847a7ef4c0678ddcad0ba1"
OUTPUT_SHA256 = "41508616beb8394ccd664a62e05c4b3aa79853fc77640a1512bddd939bd5814d"
OUTPUT = project.ROOT / "build/pagination-probe"
PREVIOUS_FORM = project.ROOT / "work/qa/windows-height-results-to-fill.json"
FORM = project.ROOT / "work/qa/pagination-results-to-fill.json"


def main():
    if OUTPUT.exists() or FORM.exists():
        raise ValueError("Existing paginated diagnostic/evidence preserved; staging is not repeated")
    original, meta, kit = project.source_bytes(), project.baseline(), project.codec()
    incoming = INPUT.read_bytes()
    previous = project.load(INPUT.parent / "manifest.json")
    if (project.digest(incoming) != INPUT_SHA256 or previous["output_sha256"] != INPUT_SHA256
            or previous["runtime_verified"] is not False):
        raise ValueError("Retained source-bound window diagnostic differs")
    candidate, native = native_pagination_patch.apply(incoming, previous["native_layout"])
    digest = project.digest(candidate)
    if digest != OUTPUT_SHA256:
        raise ValueError("Paginated diagnostic differs from its retained historical fingerprint")
    before = scenario_source.scan(incoming, kit)
    after = scenario_source.scan(candidate, kit)
    if len(before) != 1884 or len(before) != len(after):
        raise ValueError("Pagination changed scenario inventory")
    for old, new in zip(before, after):
        if vars(old[0]) != vars(new[0]) or old[1:] != new[1:]:
            raise ValueError("Native pagination changed an original diagnostic scenario payload/index")
    opening_payload = next(payload for entry, payload, name, chunks in after if name == "010301000")
    units = kit.make_structured_units(
        opening_payload, kit.read_text_records_structured(opening_payload, "cp932", None),
        include_offsets=False, encoding="cp932", font_table=None, decode_gaps=False)
    locator = previous["height_marker"]
    long_text = units[locator["unit"]]["items"][locator["item"]]["original_text"].encode("cp932")
    report = copy.deepcopy(previous)
    report.update(output=str(OUTPUT / "EBOOT.elf"), output_sha256=digest,
                  input=str(INPUT.relative_to(project.ROOT)), input_sha256=INPUT_SHA256,
                  native_layout=native, native_template_sha256=digest,
                  runtime_verified=False, production_growth_enabled=False,
                  scenario_payloads_identical_to_input=True)
    # Temporary source-bound assembly exercises the same native-copy contract
    # production will use after acceptance; it never writes production output.
    with tempfile.TemporaryDirectory(prefix=".pagination-stage-", dir=project.ROOT / "build") as temporary:
        stage = Path(temporary)
        project.save(stage / "manifest.json", report)
        (stage / "EBOOT.elf").write_bytes(candidate)
        native_only, staged, copied_native = production_engine.native_image(
            original, meta, template_path=stage / "EBOOT.elf", template_sha256=digest)
        replay_native = copy.deepcopy(copied_native)
        replay_native["output_sha256"] = project.digest(native_only)
        pagination = native_pagination_smoke.smoke(native_only, replay_native, long_text)
        layout = native_layout_smoke.smoke(native_only, replay_native)
        okay, explanation = gates.engine_cutover(candidate, staged, native, kit)
        if not okay:
            raise ValueError("Paginated diagnostic fails complete native/capacity cutover: " + explanation)
        report["engine"] = {"native_template_sha256": digest, "verified_payloads": len(after),
                            "all_scenario_payloads_identical_to_input": True,
                            "native_correction_matches_staged": True, "engine_cutover": explanation,
                            "production_growth_enabled": False}
        report["encoded_pagination_smoke"] = {key: value for key, value in pagination.items()
                                                if key not in ("cases", "limitations")}
        report["encoded_layout_smoke"] = {key: layout[key] for key in
                                            ("case_count", "supported_fixture_invariants_passed")}
        report["manual_acceptance"][0] = "Manually select this distinct diagnostic as TH2_EN_PAGES.elf; preserve originals and earlier evidence"
        report["limits"] = [
            "Encoded automatic-page transitions and saved raw checkpoint reconstruction pass; real rendering/input/save transitions remain unverified.",
            "All diagnostic message/choice/branch bytes are identical to the retained height target; no work translations are inserted.",
            "Backlog/non-dialogue queues retain their original protocol; a single intrinsically oversized row is not scaled or truncated."]
        project.save(stage / "manifest.json", report)
        project.save(stage / "EBOOT.report.json", report)
        project.save(stage / "pagination-smoke.json", pagination)
        project.save(stage / "layout-smoke.json", layout)
        stage.rename(OUTPUT)
    form = project.load(PREVIOUS_FORM)
    form["previous_results"] = PREVIOUS_FORM.relative_to(project.ROOT).as_posix()
    form["windows"] = {"output_sha256": digest, "tester": "", "rpcs3_version": "", "tested_at": "",
                         "scene": "", "notes": "", "checks": {check: None for check in gates.CHECKS["windows"]},
                         "screenshots": []}
    project.save(FORM, form)
    print(json.dumps({"output": report["output"], "sha256": digest,
                      "verified_payloads": len(after), "pagination_cases": pagination["case_count"],
                      "layout_cases": layout["case_count"], "results_form": FORM.relative_to(project.ROOT).as_posix(),
                      "runtime_verified": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        raise SystemExit(f"ERROR: {error}")
