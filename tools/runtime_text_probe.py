"""Stage the corrected long-text diagnostic; never deploy or run RPCS3.

Requires the existing Capstone analysis dependency and work-local Keystone0.9.2.
Preserves the failed ELF/results and every scenario payload. Production remains
separately gated by genuine exact-build runtime evidence.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import struct
import tempfile

import gates
import native_runtime_text_patch
import native_runtime_text_smoke
import production_engine
import project
import scenario_source

INPUT = project.ROOT / "build/pagination-probe/EBOOT.elf"
INPUT_SHA256 = "41508616beb8394ccd664a62e05c4b3aa79853fc77640a1512bddd939bd5814d"
OUTPUT_SHA256 = "6da9f08969688de1faa9fc8f0566122105e92065d01f324ab85dbf5089006206"
OUTPUT = project.ROOT / "build/runtime-text-probe"
PREVIOUS_FORM = project.ROOT / "work/qa/pagination-results-to-fill.json"
FORM = project.ROOT / "work/qa/runtime-text-results-to-fill.json"


def inputs():
    if OUTPUT.exists() or FORM.exists():
        raise ValueError("Existing corrected diagnostic/evidence preserved; staging is not repeated")
    incoming = INPUT.read_bytes()
    previous = project.load(INPUT.parent / "manifest.json")
    if (project.digest(incoming) != INPUT_SHA256 or previous["output_sha256"] != INPUT_SHA256
            or previous["runtime_verified"] is not False):
        raise ValueError("Retained failed pagination diagnostic differs")
    return incoming, previous


def long_literal(image, previous, kit):
    payload = next(payload for entry, payload, name, chunks in scenario_source.scan(image, kit)
                   if name == "010301000")
    units = kit.make_structured_units(
        payload, kit.read_text_records_structured(payload, "cp932", None),
        include_offsets=False, encoding="cp932", font_table=None, decode_gaps=False)
    locator = previous["height_marker"]
    text = units[locator["unit"]]["items"][locator["item"]]["original_text"].encode("cp932")
    if len(text) != 1286 or not text.endswith(b"[HEND]"):
        raise ValueError("Complete unchanged diagnostic paragraph differs")
    return text


def stage(incoming, previous, candidate, native, execution):
    """Publish an already exercised exact-image replay without rerunning it."""
    if OUTPUT.exists() or FORM.exists():
        raise ValueError("Existing corrected diagnostic/evidence preserved; staging is not repeated")
    original, meta, kit = project.source_bytes(), project.baseline(), project.codec()
    digest = project.digest(candidate)
    if (project.digest(incoming) != INPUT_SHA256 or previous["output_sha256"] != INPUT_SHA256
            or digest != OUTPUT_SHA256 or execution["image_sha256"] != digest
            or execution["source_sha256"] != project.digest(original)
            or execution["runtime_accepted"] is not False
            or not execution["full_literal_vm_terminator_preserved"]
            or not execution["native_held_pages"]["full_text_visible_at_modeled_draw_boundary"]):
        raise ValueError("Corrected diagnostic and completed encoded replay differ")
    before, after = scenario_source.scan(incoming, kit), scenario_source.scan(candidate, kit)
    if len(before) != 1884 or len(after) != len(before):
        raise ValueError("Runtime text correction changed scenario inventory")
    for old, new in zip(before, after):
        if vars(old[0]) != vars(new[0]) or old[1:] != new[1:]:
            raise ValueError("Runtime text correction changed a diagnostic payload/index")
        if len(new[1]) >= 1 << 21:
            raise ValueError("A scenario exceeds the checkpoint reference offset format")
    report = copy.deepcopy(previous)
    report.update(output=str(OUTPUT / "EBOOT.elf"), output_sha256=digest,
                  input=str(INPUT.relative_to(project.ROOT)), input_sha256=INPUT_SHA256,
                  native_layout=native, native_template_sha256=digest,
                  runtime_verified=False, production_growth_enabled=False,
                  scenario_payloads_identical_to_input=True)
    report["manual_acceptance"] = [
        "Manually select this distinct build as TH2_EN_RUNTIME.elf; preserve all originals and failed evidence",
        "Fresh ToHeart2 New Game, not savestate or corrupted slots006/007; confirm the complete grown opening",
        "Inspect N01 nickname and P01 punctuation, then advance H01-H08 through HEND without missing text",
        "At the long paragraph use only a new disposable spare slot; reload it on this same build and confirm the saved page and unread remainder",
        "Exercise skip beyond this paragraph into an unchanged scene; stop on black screen, wrong story branding or missing content",
        "Confirm base-game date/story remains March1/ToHeart2 through this progression; do not repair old saves",
        "Only after height passes, inspect March2's three complete choices and an original B01/B02/B03 branch",
        "Earlier short-run control/menu acceptance remains historical; it does not accept this new long-text checkpoint codec",
    ]
    report["limits"] = list(execution["limitations"])
    report["limits"].append("Backlog submission is modeled, not its full native history ring; long-session history and memory fit remain unproved.")
    with tempfile.TemporaryDirectory(prefix=".runtime-text-stage-", dir=project.ROOT / "build") as temporary:
        target = Path(temporary)
        project.save(target / "manifest.json", report)
        (target / "EBOOT.elf").write_bytes(candidate)
        projected, projection = production_engine.rebuild_image(
            original, {}, kit, meta, template_path=target / "EBOOT.elf", template_sha256=digest)
        originals = scenario_source.scan(original, kit)
        projected_rows = scenario_source.scan(projected, kit)
        if [(row[0].json_filename, row[1]) for row in originals] != [
                (row[0].json_filename, row[1]) for row in projected_rows]:
            raise ValueError("Native-only production projection copied diagnostic text or changed source payloads")
        payload = next(payload for entry, payload, name, chunks in originals if name == "010301000")
        units = kit.make_structured_units(
            payload, kit.read_text_records_structured(payload, "cp932", None),
            include_offsets=False, encoding="cp932", font_table=None, decode_gaps=False)
        text = next(item["original_text"].encode("cp932") for unit in units for item in unit["items"]
                    if isinstance(item.get("original_text"), str) and len(item["original_text"].encode("cp932")) >= 8)
        frame = payload.find(b"\x0a" + struct.pack("<H", len(text)) + text)
        if frame < 0:
            raise ValueError("Production projection source literal is not bound to its native frame")
        bound = copy.deepcopy(native)
        bound["output_sha256"] = project.digest(projected)
        cpu = native_runtime_text_smoke.RuntimeCPU(original, projected, bound, b"A", payload, frame + 3,
                                                  dialogue=True, height=628)
        decoded = cpu.decode_literal()
        if decoded["text"] != text or decoded["next_byte"] != 2:
            raise ValueError("Production projection native literal parser changed source text/bytecode")
        cpu.run()
        cpu.assert_flags()
        trace = cpu.read(cpu.STATE + 0x12C, cpu.get(cpu.STATE + 0x128, 4))
        restored = native_runtime_text_smoke.RuntimeCPU(original, projected, bound, b"A", payload, frame + 3,
                                                       dialogue=True, height=628)
        restored.replay_saved(trace)
        restored.assert_flags()
        if restored.backlog_submissions != [text] or restored.heap:
            raise ValueError("Production projection checkpoint did not replay the complete source literal")
        projection.update(image_sha256=project.digest(projected), unchanged_source_payloads=len(projected_rows),
                          source_literal_bytes=len(text), source_literal_checkpoint_replayed=True,
                          runtime_accepted=False, production_written=False)
        report["engine"] = projection
        report["encoded_runtime_text_smoke"] = {
            "report": "runtime-smoke.json", "image_sha256": execution["image_sha256"],
            "corrected_vm_literal_bytes": execution["corrected_vm_literal_bytes"],
            "opacity_glyphs": execution["native_opacity_glyphs_checked"], "runtime_accepted": False}
        project.save(target / "runtime-smoke.json", execution)
        project.save(target / "projection-smoke.json", projection)
        project.save(target / "manifest.json", report)
        project.save(target / "EBOOT.report.json", report)
        target.rename(OUTPUT)
    form = project.load(PREVIOUS_FORM)
    form["previous_results"] = PREVIOUS_FORM.relative_to(project.ROOT).as_posix()
    form["windows"] = {"output_sha256": digest, "tester": "", "rpcs3_version": "", "tested_at": "",
                       "scene": "", "notes": "", "checks": {check: None for check in gates.CHECKS["windows"]},
                       "screenshots": []}
    project.save(FORM, form)
    return {"output": report["output"], "sha256": digest, "verified_payloads": len(after),
            "source_projection_payloads": len(projected_rows), "native_sites": len(native["patches"]),
            "helper_bytes": native["rx_extension"]["size"], "runtime_verified": False,
            "results_form": FORM.relative_to(project.ROOT).as_posix()}


def main():
    incoming, previous = inputs()
    candidate, native = native_runtime_text_patch.apply(incoming, previous["native_layout"])
    text = long_literal(candidate, previous, project.codec())
    execution = native_runtime_text_smoke.smoke(candidate, native, incoming, previous["native_layout"], text)
    print(json.dumps(stage(incoming, previous, candidate, native, execution), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration) as error:
        raise SystemExit(f"ERROR: {error}")
