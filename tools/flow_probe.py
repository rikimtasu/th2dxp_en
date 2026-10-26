"""Stage an original-font diagnostic for the native ASCII terminal-span bug.

The failed explicit-break script is reproduced exactly; only one native branch
is changed. Production builds, translation work and installed games stay untouched.
"""
from pathlib import Path
import copy
import json
import tempfile

import project
import scenario_source
import text_layout
import choice_text

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = 24  # Conservative diagnostic target, NOT a measured universal font width.
FAILED_FLOW_SHA256 = "c051bd3cf61ac4c8bca7c1850dc23ae4cab9294f787aaf6105a3f5daf8e460df"
BRANCH_OFFSET = 0x5E64C  # VA 0x6E64C; ordinary one-byte character dispatch.
ORIGINAL_BRANCH = bytes.fromhex("4082038c")  # bne 0x6E9D8: skips terminal check.
TERMINAL_BRANCH = bytes.fromhex("4082fccc")  # bne 0x6E318: reuses existing check.
SAMPLES = {
    (0, 0): "[F01] ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    (0, 1): "[F02] abcdefgh",
    (1, 0): "[F03] 0123456789",
    (2, 0): "[F04] IiLl WwMm",
    (3, 0): "[F05] The quick brown fox jumps.",
    (3, 1): "[F06] NEXT FRAGMENT",
    (4, 0): "[F07] abcdefghijklmnopqrstuvwxyz",
    (4, 1): "[F08] END",
}


def main():
    original = project.source_bytes()
    if original[BRANCH_OFFSET:BRANCH_OFFSET + 4] != ORIGINAL_BRANCH:
        raise ValueError("Unexpected native ASCII dispatch; refusing another revision")
    kit = project.codec()
    meta = project.baseline()
    entry = meta["entries"][0]
    if entry["source_name"] != "010301000":
        raise ValueError("Unexpected opening scene identity")
    baseline = project.load(project.BASELINE / entry["json_filename"])
    edited = copy.deepcopy(baseline)
    samples = dict(SAMPLES)
    # Cover the same first 12 units as the original glyph probe. Short later
    # markers also test page continuation and keep this diagnostic within its
    # original compressed slot; no real translation content is shortened.
    for ui, unit in enumerate(baseline[:12]):
        for ii, item in enumerate(unit["items"]):
            if item["kind"] != "text" or (ui, ii) in samples:
                continue
            if len(item["original_text"].encode("cp932")) >= 12 and "\\" not in item["original_text"]:
                samples[ui, ii] = f"[F{len(samples)+1:02d}] OK"
    for (ui, ii), text in samples.items():
        item = edited[ui]["items"][ii]
        if item["kind"] != "text":
            raise ValueError("Diagnostic locator no longer identifies text")
        item["translated_text"] = text
    compiled, layout = text_layout.compile_units(edited, columns=COLUMNS, break_fragments=True)
    output = ROOT / "build/native-flow-probe/EBOOT.elf"
    with tempfile.TemporaryDirectory(prefix="native-flow-probe-") as temporary:
        scripts = Path(temporary) / "script"
        choice_text.copy_baseline(scripts)
        project.save(scripts / entry["json_filename"], edited)
        intermediate = Path(temporary) / "scenario.elf"
        rebuilt = project.build(scripts, intermediate, kit, meta, original, layout_columns=COLUMNS)
        build_report = project.load(intermediate.with_suffix(".report.json"))
    if project.digest(rebuilt) != FAILED_FLOW_SHA256:
        raise ValueError("Diagnostic no longer reproduces the failed flow image; A/B comparison refused")
    patched = bytearray(rebuilt)
    patched[BRANCH_OFFSET:BRANCH_OFFSET + 4] = TERMINAL_BRANCH
    rebuilt = bytes(patched)
    scanned = scenario_source.scan(rebuilt, kit)
    payload = next(row[1] for row in scanned if row[0].entry_index == entry["entry_index"])
    observed = kit.make_structured_units(payload, kit.read_text_records_structured(payload, "cp932", None),
                                        include_offsets=False, encoding="cp932", font_table=None, decode_gaps=False)
    if len(observed) != len(baseline):
        raise ValueError("Explicit breaks changed logical unit structure")
    for ui, (before, after) in enumerate(zip(baseline, observed)):
        if len(before["items"]) != len(after["items"]):
            raise ValueError("Text compilation changed bytecode/item structure")
        for ii, (old, new) in enumerate(zip(before["items"], after["items"])):
            if old["kind"] != new["kind"]:
                raise ValueError("Text compilation changed item kind")
            if old["kind"] != "text":
                if old != new:
                    raise ValueError("Text compilation changed a non-text control/opcode")
            elif (ui, ii) in samples:
                if new["original_text"] != compiled[ui]["items"][ii]["translated_text"]:
                    raise ValueError("Compiled text failed actual-container re-extraction")
                if new["original_text"].replace("\\n", "") != samples[ui, ii]:
                    raise ValueError("Visible diagnostic characters were lost")
                if new["control_suffix"] != old["control_suffix"]:
                    raise ValueError("Wait/page/terminal controls changed")
            elif new["original_text"] != old["original_text"] or new["control_suffix"] != old["control_suffix"]:
                raise ValueError("Untouched text changed")
    native_patch = {
        "virtual_address": "0x6E64C", "file_offset": hex(BRANCH_OFFSET),
        "before": ORIGINAL_BRANCH.hex(), "after": TERMINAL_BRANCH.hex(),
        "old_target": "0x6E9D8", "new_target": "0x6E318",
        "purpose": "Flush the last ordinary one-byte character span, as the existing two-byte path does",
        "scope": "Experimental opening diagnostic only; special engine-command paths are unchanged",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rebuilt)
    build_report.update(output=str(output), output_sha256=project.digest(rebuilt),
                        native_patch=native_patch, original_font_unchanged=True,
                        unpatched_diagnostic_sha256=FAILED_FLOW_SHA256)
    project.save(output.with_suffix(".report.json"), build_report)
    manifest = {
        "output": str(output), "sha256": project.digest(rebuilt), "source_name": entry["source_name"],
        "script": entry["json_filename"], "profile": layout, "verified_scenario_payloads": len(scanned),
        "original_wait_page_controls_preserved": True, "native_code_patched": True,
        "native_patch": native_patch, "original_font_unchanged": True,
        "previous_failed_probe_sha256": FAILED_FLOW_SHA256,
        "runtime_verified": False, "production_layout_enabled": False,
        "expected_first_page": compiled[0]["items"][0]["translated_text"] + compiled[0]["items"][1]["translated_text"],
        "manual_acceptance": ["F01 shows complete A-Z across its explicit line break",
                              "F02 appears on that same opening page, before advancing to F03",
                              "F05 sentence and F06 fragment both appear without loss",
                              "F07 shows complete lowercase alphabet and F08 follows",
                              "No clipping, extra waits, missing page indicators or backward/skip/backlog corruption"],
        "limits": "24 columns is an isolated diagnostic budget; production widths, page heights, word wrapping across all windows and growth remain gated",
    }
    project.save(output.parent / "manifest.json", manifest)
    print(json.dumps({"output": str(output), "sha256": manifest["sha256"],
                      "expected_first_page": manifest["expected_first_page"],
                      "verified_payloads": len(scanned), "runtime_verified": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f"ERROR: {error}")
