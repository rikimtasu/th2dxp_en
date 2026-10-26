"""Stage original-font descender/cell edges and word-aware wrapping; no deployment."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile

import gates
import native_runtime_text_smoke
import native_typography_patch
import native_typography_smoke
import production_engine
import project
import runtime_text_probe
import scenario_source

INPUT = project.ROOT / "build/runtime-text-probe/EBOOT.elf"
INPUT_SHA256 = "6da9f08969688de1faa9fc8f0566122105e92065d01f324ab85dbf5089006206"
OUTPUT_SHA256 = "ce9da83e005d999e33966e45d449ac04d574cec867219fbb5176873826bb0f4c"
OUTPUT = project.ROOT / "build/typography-probe"
FORM = project.ROOT / "work/qa/typography-results-to-fill.json"
PREVIOUS_FORM = project.ROOT / "work/qa/runtime-text-results-to-fill.json"


def stage(incoming, previous, candidate, native, execution, runtime):
    if OUTPUT.exists() or FORM.exists():
        raise ValueError("Existing typography diagnostic/evidence preserved; staging is not repeated")
    source, kit, meta = project.source_bytes(), project.codec(), project.baseline()
    digest = project.digest(candidate)
    if (project.digest(incoming) != INPUT_SHA256 or previous["output_sha256"] != INPUT_SHA256
            or digest != OUTPUT_SHA256
            or any(row["image_sha256"] != digest or row["runtime_accepted"] is not False
                   for row in (execution, runtime))):
        raise ValueError("Typography input, native template or exact-image execution differs")
    before, after = scenario_source.scan(incoming, kit), scenario_source.scan(candidate, kit)
    if len(before) != 1884 or len(after) != 1884:
        raise ValueError("Typography scenario coverage differs")
    for old, new in zip(before, after):
        if vars(old[0]) != vars(new[0]) or old[1:] != new[1:]:
            raise ValueError("Typography changed diagnostic scenario/index bytes")
    report = copy.deepcopy(previous)
    report.update(input=str(INPUT.relative_to(project.ROOT)), input_sha256=INPUT_SHA256,
                  output=str(OUTPUT / "EBOOT.elf"), output_sha256=digest,
                  native_layout=native, native_template_sha256=digest,
                  runtime_verified=False, production_growth_enabled=False,
                  scenario_payloads_identical_to_input=True)
    report["manual_acceptance"] = [
        "Select distinct TH2_EN_TYPE.elf; preserve originals, earlier evidence and personal saves",
        "Fresh ToHeart2 New Game, never corrupted slots006/007 or an old savestate",
        "Inspect g/j/p/q/y descenders and punctuation at the same original font size",
        "Fitting words and [Hxx] markers stay on one line; overlong tokens may use character fallback",
        "Advance every H01-H08 section through HEND, then check skip/story state and a disposable same-build long-text save/load",
        "Only after layout passes, inspect complete March2 choices, original branch marker and unchanged scene",
        "No older exact-hash acceptance is transferred to the new typography checks",
    ]
    report["limits"] = list(execution["limitations"]) + [
        "Native history-ring behavior and full-game memory fit remain unproved."]
    with tempfile.TemporaryDirectory(prefix=".typography-stage-", dir=project.ROOT / "build") as temporary:
        target = Path(temporary)
        (target / "EBOOT.elf").write_bytes(candidate)
        project.save(target / "manifest.json", report)
        projected, projection = production_engine.rebuild_image(
            source, {}, kit, meta, template_path=target / "EBOOT.elf", template_sha256=digest)
        originals, projected_rows = scenario_source.scan(source, kit), scenario_source.scan(projected, kit)
        if [(row[0].json_filename, row[1]) for row in originals] != [
                (row[0].json_filename, row[1]) for row in projected_rows]:
            raise ValueError("Typography production projection changed original payloads or copied diagnostic English")
        projection.update(image_sha256=project.digest(projected), unchanged_source_payloads=len(projected_rows),
                          runtime_accepted=False, production_written=False)
        report["engine"] = projection
        report["encoded_typography_smoke"] = {"word_cases": len(execution["word_cases"]),
                                               "glyph_scales": len(execution["glyph_cases"]),
                                               "report": "typography-smoke.json", "runtime_accepted": False}
        project.save(target / "typography-smoke.json", execution)
        project.save(target / "runtime-smoke.json", runtime)
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
    return {"output": str(OUTPUT / "EBOOT.elf"), "sha256": digest,
            "verified_payloads": len(after), "source_projection_payloads": len(projected_rows),
            "word_cases": len(execution["word_cases"]), "glyph_scales": len(execution["glyph_cases"]),
            "results_form": FORM.relative_to(project.ROOT).as_posix(), "runtime_verified": False}


def main():
    if OUTPUT.exists() or FORM.exists():
        raise ValueError("Existing typography diagnostic/evidence preserved; staging is not repeated")
    incoming = INPUT.read_bytes()
    previous = project.load(INPUT.parent / "manifest.json")
    if project.digest(incoming) != INPUT_SHA256 or previous["output_sha256"] != INPUT_SHA256:
        raise ValueError("Retained runtime-text input fingerprint differs")
    image, native = native_typography_patch.apply(incoming, previous["native_layout"])
    source, kit = project.source_bytes(), project.codec()
    text = runtime_text_probe.long_literal(image, previous, kit)
    payload = next(row[1] for row in scenario_source.scan(image, kit) if row[2] == "010301000")
    execution = native_typography_smoke.smoke(source, image, native, incoming, previous["native_layout"],
                                             payload, payload.find(text), text)
    failed = runtime_text_probe.INPUT.read_bytes()
    failed_native = project.load(runtime_text_probe.INPUT.parent / "manifest.json")["native_layout"]
    runtime = native_runtime_text_smoke.smoke(image, native, failed, failed_native, text)
    print(json.dumps(stage(incoming, previous, image, native, execution, runtime), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration) as error:
        raise SystemExit(f"ERROR: {error}")
