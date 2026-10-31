"""Stage full-text growth in a separate segment; never patch production or deploy."""
import copy
import json
import struct

import flow_probe
import project
import scenario_capacity
import scenario_source


ROOT = project.ROOT
OUTPUT = ROOT / "build/capacity-probe/EBOOT.elf"
REVIEW = ROOT / "work/alignment/opening-reviewed.json"


def main():
    source = project.source_bytes()
    kit = project.codec()
    meta = project.baseline()
    reviewed = project.load(REVIEW)
    locator = reviewed["ps3"]
    if locator["script"] != "script_0000.json" or locator["unit"] != 0:
        raise ValueError("Diagnostic no longer identifies the observed opening")
    original = project.load(project.BASELINE / locator["script"])
    source_unit = original[0]
    items = locator["text_items"]
    if [row["item"] for row in items] != [0, 1]:
        raise ValueError("Opening review does not preserve the original two fragments")
    for row in items:
        if source_unit["items"][row["item"]]["original_text"] != row["original_text"]:
            raise ValueError("Reviewed Japanese differs from immutable opening source")
    if [row for row in source_unit["items"] if row["kind"] != "text"] != locator["controls_preserved"]:
        raise ValueError("Reviewed opening controls differ from source")
    if "".join(row["original_text"] for row in items) != reviewed["review"]["japanese"]:
        raise ValueError("Opening source sentence differs from its context review")
    pc = reviewed["ittaku"]
    reference = project.load(ROOT / "reference/ittaku/manifest.json")
    if pc["archive_sha256"] != reference["source"]["sha256"]:
        raise ValueError("Reviewed sentence is not tied to the verified PC reference")
    sentence = pc["complete_sentence_without_pc_hard_wrap"]
    if sentence != pc["text_as_stored"].replace("\\n", " ") or "\\" in sentence:
        raise ValueError("Diagnostic may remove only the PC sentence's hard wrapping")
    sentence_bytes = sentence.encode("cp932", errors="strict")
    if sentence_bytes.decode("cp932") != sentence or len(sentence_bytes) != pc["cp932_bytes"]:
        raise ValueError("Reviewed English encoding differs")
    # Split the complete sentence across the same two source records. Retain
    # the boundary space so concatenation remains byte-for-byte complete.
    split = sentence.rfind(" ", 1, len(sentence) // 2 + 1)
    if split < 1 or split == len(sentence) - 1:
        raise ValueError("Opening sentence has no safe two-fragment word boundary")
    parts = (sentence[:split], sentence[split:])
    if "".join(parts) != sentence:
        raise ValueError("Diagnostic shortened the reviewed sentence")
    edited = copy.deepcopy(original)
    for row, text in zip(items, parts):
        edited[0]["items"][row["item"]]["translated_text"] = text
    scanned = scenario_source.scan(source, kit)
    entry, payload, native_name, _ = scanned[0]
    if entry.json_filename != locator["script"] or native_name != locator["native_name"]:
        raise ValueError("Opening scenario identity differs from reviewed evidence")
    grown = kit.rebuild_scenario_from_structured_json(
        payload, edited, encoding="cp932", font_table=None, allow_growth=True)
    if len(grown) <= len(payload):
        raise ValueError("The full sentence did not actually grow its source scenario")
    observed = kit.make_structured_units(
        grown, kit.read_text_records_structured(grown, "cp932", None),
        include_offsets=False, encoding="cp932", font_table=None, decode_gaps=False)
    if len(observed) != len(original):
        raise ValueError("Scenario growth changed the original logical unit count")
    for ui, (old_unit, new_unit) in enumerate(zip(original, observed)):
        if len(old_unit["items"]) != len(new_unit["items"]):
            raise ValueError("Scenario growth changed original item ordering/count")
        for ii, (old, new) in enumerate(zip(old_unit["items"], new_unit["items"])):
            if old["kind"] != new["kind"]:
                raise ValueError("Scenario growth changed an item kind")
            if old["kind"] != "text":
                if old != new:
                    raise ValueError("Scenario growth changed original control/opcode bytes")
            else:
                wanted = parts[ii] if ui == 0 and ii in (0, 1) else old["original_text"]
                if new["original_text"] != wanted or new["control_suffix"] != old["control_suffix"]:
                    raise ValueError("Scenario growth lost text or changed original suffix controls")
    if source[flow_probe.BRANCH_OFFSET:flow_probe.BRANCH_OFFSET + 4] != flow_probe.ORIGINAL_BRANCH:
        raise ValueError("Unexpected original terminal-flush dispatch")
    terminal = bytearray(source)
    terminal[flow_probe.BRANCH_OFFSET:flow_probe.BRANCH_OFFSET + 4] = flow_probe.TERMINAL_BRANCH
    rebuilt, report = scenario_capacity.relocate(bytes(terminal), {entry.json_filename: grown}, kit, meta)
    report.update(
        output=str(OUTPUT), output_sha256=project.digest(rebuilt), source_sha256=project.digest(source),
        opening={"script": entry.json_filename, "native_name": native_name, "unit": 0,
                 "complete_english": sentence, "fragments": list(parts),
                 "original_text_bytes": sum(row["original_text_bytes"] for row in items),
                 "full_english_bytes": len(sentence_bytes), "scenario_growth_bytes": len(grown) - len(payload)},
        reference_review=REVIEW.relative_to(ROOT).as_posix(), reference_review_sha256=project.digest(REVIEW.read_bytes()),
        terminal_flush_preserved=True, original_font_unchanged=True,
        metric_layout_fixed=False, manual_target_ready=False,
        manual_target_note="Capacity-only staging. Integrate the supported original-font VWF/layout correction before asking for a combined layout/growth acceptance run.",
        bytecode_controls_verified=True, editable_scripts_modified=False)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(rebuilt)
    project.save(OUTPUT.with_suffix(".report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, struct.error) as error:
        raise SystemExit(f"ERROR: {error}")
