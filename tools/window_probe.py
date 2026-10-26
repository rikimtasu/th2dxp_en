"""Stage missing English name/punctuation/height/choice cases; never deploy."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile

import choice_text
import gates
import production_engine
import project
import scenario_graph
import scenario_source

OUTPUT = project.ROOT / "build/windows-height-probe"
FORM = project.ROOT / "work/qa/windows-height-results-to-fill.json"
PREVIOUS_FORM = project.ROOT / "work/qa/save-preview-results-to-fill.json"
GROWTH_TEMPLATE_SHA256 = "6027c7c9221cd79522167218a4bc433a710152db1c7bf83704470a4cc4ff3eed"
REFERENCE = project.ROOT / "work/pc-reference/full-reference"


def reference_choices():
    manifest = project.load(REFERENCE / "manifest.json")
    hashes = {name.replace("\\", "/"): digest for name, digest in manifest["output_sha256"].items()}
    operands = REFERENCE / "text-operands.jsonl"
    if project.digest(operands.read_bytes()) != hashes["text-operands.jsonl"]:
        raise ValueError("Encoded PC reference changed")
    rows = []
    with operands.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["entry"] == "010302100.SDT" and row["classification"] == "choice":
                rows.append(row)
    if len(rows) != 3 or [row["instruction_index"] for row in rows] != [123, 124, 125]:
        raise ValueError("Reviewed PC selection no longer has its original three choices")
    entries = project.load(REFERENCE / "entries.json")
    for row in rows:
        raw = (REFERENCE / "parser-dump/entries" / f"{row['entry_index']}.bin").read_bytes()
        start, size = row["text_entry_offset"], row["byte_length"]
        if (project.digest(raw) != entries[row["entry_index"]]["decoded_sha256"] or
                raw[start:start + size].hex() != row["raw_hex"] or
                project.digest(raw[start:start + size]) != row["raw_sha256"] or
                raw[start:start + size].decode("cp932") != row["text"]):
            raise ValueError("PC choice differs from its pinned decoded archive bytes")
    return rows, {"manifest_sha256": project.digest((REFERENCE / "manifest.json").read_bytes()),
                  "archive_sha256": manifest["archive_sha256"], "choices": rows,
                  "review": "Diagnostic context review: same thrill/amusement-park/sports/home alternatives, in original order. Native choice count and A/B/C destinations are separately bound; this is not bulk import approval."}


def compare_units(before, after):
    if len(before) != len(after):
        raise ValueError("Diagnostic changed logical message unit count")
    for old_unit, new_unit in zip(before, after):
        if len(old_unit["items"]) != len(new_unit["items"]):
            raise ValueError("Diagnostic changed message item count")
        for old, new in zip(old_unit["items"], new_unit["items"]):
            if old["kind"] != new["kind"]:
                raise ValueError("Diagnostic changed message item kind")
            if old["kind"] == "text":
                if new["original_text"] != old["translated_text"] or new["control_suffix"] != old["control_suffix"]:
                    raise ValueError("Diagnostic message text/control did not re-extract completely")
            elif old != new:
                raise ValueError("Diagnostic changed original message bytecode/control bytes")


def main():
    if OUTPUT.exists() or FORM.exists():
        raise ValueError("Existing window diagnostic/results preserved; do not repeat staging")
    source, kit, meta = project.source_bytes(), project.codec(), project.baseline()
    scanned = scenario_source.scan(source, kit)
    by_native = {name: (entry, payload) for entry, payload, name, _ in scanned}
    previous = project.load(PREVIOUS_FORM)
    if previous["growth"]["output_sha256"] != GROWTH_TEMPLATE_SHA256:
        raise ValueError("Earlier accepted controls identify another native candidate")
    template = project.load(gates.ARTIFACTS["growth"].parent / "manifest.json")
    parts = template["opening"]["fragments"]
    opening = copy.deepcopy(project.load(project.BASELINE / "script_0000.json"))
    for item, text in zip((0, 1), parts):
        opening[0]["items"][item]["translated_text"] = text
    if project.engine_controls(opening[57]["items"][0]["original_text"]) != ["*nnk"]:
        raise ValueError("Source nickname diagnostic locator changed")
    opening[57]["items"][0]["translated_text"] = '[N01] "Oh, *nnk-kun! You\'re here... aren\'t you?"'
    punctuation = next((ui, ii) for ui, unit in enumerate(opening) if ui > 57
                       for ii, item in enumerate(unit["items"])
                       if item["kind"] == "text" and not project.engine_controls(item["original_text"]))
    ui, ii = punctuation
    opening[ui]["items"][ii]["translated_text"] = '[P01] !?.,:; \'" () [] {} +-= _/ @#$%&^|~'
    height_locator = next((ui, ii) for ui, unit in enumerate(opening) if ui > punctuation[0]
                          for ii, item in enumerate(unit["items"])
                          if item["kind"] == "text" and not project.engine_controls(item["original_text"]))
    height_text = " ".join(
        f"[H{index:02d}] Full-length English must remain readable beyond one window. "
        "Advance normally to follow every numbered section; nothing should disappear below the screen."
        for index in range(1, 9)) + " [HEND]"
    ui, ii = height_locator
    opening[ui]["items"][ii]["translated_text"] = height_text
    changed = {"script_0000.json": opening}
    choice_entry, choice_payload = by_native["010302100"]
    choice_name = choice_text.companion_name(choice_entry.json_filename)
    choices = copy.deepcopy(project.load(choice_text.baseline_dir() / choice_name))
    pc_rows, provenance = reference_choices()
    if len(choices) != 3:
        raise ValueError("PS3 choice count differs from the reviewed three alternatives")
    for unit, pc in zip(choices, pc_rows):
        if project.engine_controls(unit["items"][0]["original_text"]) != project.engine_controls(pc["text"]):
            raise ValueError("PC/PS3 choice controls differ; no silent normalization")
        unit["items"][0]["translated_text"] = pc["text"]
    changed[choice_name] = choices
    _, old_labels, old_sites, _ = scenario_graph.scan_sites(choice_payload, kit)
    destinations = [site["operands"][0].get("value") for site in old_sites if site["command_id"] == 0x1F]
    if destinations != ["010302101", "010302102", "010302103"] or [row["name"] for row in old_labels] != ["@A", "@B", "@C"]:
        raise ValueError("Original A/B/C choice destinations differ")
    branches = []
    for index, native in enumerate(destinations, 1):
        entry, _ = by_native[native]
        view = copy.deepcopy(project.load(project.BASELINE / entry.json_filename))
        locator = next((ui, ii) for ui, unit in enumerate(view)
                       for ii, item in enumerate(unit["items"])
                       if item["kind"] == "text" and not project.engine_controls(item["original_text"]))
        ui, ii = locator
        marker = f"[B0{index}] Original choice branch {chr(64 + index)} reached."
        view[ui]["items"][ii]["translated_text"] = marker
        changed[entry.json_filename] = view
        branches.append({"native_name": native, "script": entry.json_filename,
                         "unit": ui, "item": ii, "marker": marker})
    with tempfile.TemporaryDirectory(prefix="window-probe-", dir=project.ROOT / "work") as temporary:
        scripts = Path(temporary) / "script"
        choice_text.copy_baseline(scripts)
        for name, view in changed.items():
            project.save(scripts / name, view)
        validated, stats = project.validate(scripts, meta, allow_growth=True)
        rebuilt, engine = production_engine.rebuild_image(
            source, validated, kit, meta, template_path=gates.ARTIFACTS["growth"],
            template_sha256=GROWTH_TEMPLATE_SHA256)
    output_rows = {entry.json_filename: payload for entry, payload, _, _ in scenario_source.scan(rebuilt, kit)}
    for name, view in changed.items():
        if name.endswith("_choices.json"):
            continue
        payload = output_rows[name]
        observed = kit.make_structured_units(payload, kit.read_text_records_structured(payload, "cp932", None),
                                              include_offsets=False, encoding="cp932", font_table=None, decode_gaps=False)
        compare_units(view, observed)
    choice_output = output_rows[choice_entry.json_filename]
    if [row["text"] for row in choice_text.records(choice_output, kit)] != [row["text"] for row in pc_rows]:
        raise ValueError("Full original PC choice strings did not re-extract")
    _, new_labels, new_sites, _ = scenario_graph.scan_sites(choice_output, kit)
    if [(site["command_id"], site["raw_hex"]) for site in old_sites] != [(site["command_id"], site["raw_hex"]) for site in new_sites]:
        raise ValueError("Selection expressions, flags or scenario-load commands changed")
    for old, new in zip(old_labels, new_labels):
        if old["name"] != new["name"] or choice_payload[old["payload_offset"]:] != choice_output[new["payload_offset"]:]:
            raise ValueError("Original choice branch body/label destination changed")
    digest = project.digest(rebuilt)
    native = copy.deepcopy(template["native_layout"])
    native["output_sha256"] = digest
    native["input_sha256"] = project.digest(source)
    for patch in native["patches"]:
        patch["input_before"] = patch["source_before"]
    report = {"output": str(OUTPUT / "EBOOT.elf"), "output_sha256": digest,
              "source_sha256": project.digest(source), "diagnostic_only": True,
              "native_layout": native, "native_template_sha256": GROWTH_TEMPLATE_SHA256,
              "engine": engine, "verified_payloads": engine["verified_payloads"],
              "validation": stats, "opening": template["opening"],
              "name_marker": {"script": "script_0000.json", "unit": 57, "item": 0, "marker": "N01"},
              "punctuation_marker": {"script": "script_0000.json", "unit": punctuation[0], "item": punctuation[1], "marker": "P01"},
              "height_marker": {"script": "script_0000.json", "unit": height_locator[0], "item": height_locator[1],
                                "bytes": len(height_text.encode("cp932")), "markers": [f"H{i:02d}" for i in range(1, 9)] + ["HEND"],
                                "added_engine_controls": False, "runtime_pagination_unproved": True},
              "earlier_unaccepted_window_stage": "build/windows-probe/manifest.json",
              "choice_script": choice_entry.json_filename, "choice_companion": choice_name,
              "choice_reference": provenance, "branches": branches,
              "choice_expressions_and_branch_bodies_unchanged": True,
              "editable_scripts_modified": False, "installed_game_or_saves_modified": False,
              "runtime_verified": False, "production_growth_enabled": False,
              "manual_acceptance": [
                  "Manually select this distinct diagnostic as TH2_EN_WINDOWS.elf; preserve originals and earlier evidence",
                  "New Game or the opening spare save: the complete grown English sentence remains visible",
                  "At the first Konomi conversation inspect N01 dynamic nickname and P01 punctuation; no raw *nnk, missing glyphs or overlap",
                  "For the long H01-H08 paragraph, advance normally until HEND: all sections must remain reachable without vertical clipping or lost text; stop on failure",
                  "Fast-forward ordinary story to March2 after school: all three full English choices fit without overlap",
                  "Choose one option; its corresponding B01/B02/B03 marker appears through the original branch",
                  "Continue into another unchanged scene and confirm ordinary Japanese still renders",
                  "Do not repeat accepted F markers, save preview, save-load, auto/skip or backlog checks; no personal save overwrite is needed"],
              "limits": ["Diagnostic markers are not imported translations or full-game coverage",
                         "New text surfaces, automatic page-height flow and resized selection labels need manual evidence; native code is identical to the accepted-control candidate",
                         "Later saves positioned after modified records are not general compatibility evidence"]}
    form = {"previous_results": PREVIOUS_FORM.relative_to(project.ROOT).as_posix()}
    for kind in ("opening", "growth"):
        form[kind] = copy.deepcopy(previous[kind])
        form[kind]["checks"] = {check: previous[kind]["checks"][check] for check in gates.CHECKS[kind]}
        form[kind]["notes"] += " Required cases are now split by their actual diagnostic surface; the prior full form is preserved separately."
    form["windows"] = {"output_sha256": digest, "tester": "", "rpcs3_version": "", "tested_at": "", "scene": "", "notes": "",
                       "checks": {check: None for check in gates.CHECKS["windows"]}, "screenshots": []}
    with tempfile.TemporaryDirectory(prefix=".window-stage-", dir=project.ROOT / "build") as temporary:
        stage = Path(temporary)
        (stage / "EBOOT.elf").write_bytes(rebuilt)
        project.save(stage / "EBOOT.report.json", report)
        project.save(stage / "manifest.json", report)
        stage.rename(OUTPUT)
    project.save(FORM, form)
    print(json.dumps({"output": report["output"], "sha256": digest,
                      "verified_payloads": report["verified_payloads"], "branches": branches,
                      "results_form": FORM.relative_to(project.ROOT).as_posix(), "runtime_verified": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        raise SystemExit(f"ERROR: {error}")
