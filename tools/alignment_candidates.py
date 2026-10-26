"""Generate base-game message context-review candidates; never import text.

Closed native story ownership selects the ToHeart2 scope, independently of PC
availability. Equally sized, unique contiguous read-marker sequences permit an
offset hypothesis, not Japanese-context or route-feasibility approval. Native
choice captions require separate alignment and remain outside this report.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile

import project


ROOT = project.ROOT
REFERENCE = ROOT / "work/pc-reference/full-reference"
OUTPUT = ROOT / "work/alignment/base-game-message-candidates"
MEMBERSHIP = ROOT / "work/scenes/scenario-membership.json"
MARKER = re.compile(r"\\p([0-9A-Fa-f]{4})")


def base_memberships(meta, document):
    """Require a complete source/payload-bound ownership report before filtering."""
    if (document["schema_version"] != 1
            or document["source_sha256"] != meta["source_eboot_sha256"]
            or document["review"]["kind"] != "closed_native_dispatch_ownership_review"
            or document["totals"]["unresolved_membership_scenarios"] != 0):
        raise ValueError("Base review preparation requires resolved source-bound story ownership")
    expected = {entry["json_filename"]: entry for entry in meta["entries"]}
    rows = document["scenarios"]
    if (len(rows) != len(expected) or document["totals"]["scenarios"] != len(expected)
            or {row["script"] for row in rows} != set(expected)):
        raise ValueError("Story ownership does not cover every native scenario exactly once")
    included = {}
    for row in rows:
        entry = expected[row["script"]]
        if (row["source_name"] != entry["source_name"]
                or row["payload_sha256"] != entry["sha256_bin"]
                or row["proof_kind"] != "closed_native_normal_story_dispatch_ownership"
                or row["route_feasibility_proved"] is not False
                or row["status"] not in ("base_game", "shared", "anotherdays", "other")):
            raise ValueError("Story ownership identity/proof differs from the immutable baseline")
        base_owned = "base_game" in row["story_domains"]
        if base_owned != (row["status"] in ("base_game", "shared")):
            raise ValueError("Story ownership status contradicts its base-game owner")
        if base_owned:
            included[row["script"]] = row
    if not included:
        raise ValueError("Base review preparation cannot use an empty story scope")
    return included


def pc_pages(reference):
    manifest = project.load(reference / "manifest.json")
    if not manifest["coverage"]["all_scenario_bytecode_walked"]:
        raise ValueError("PC reference does not cover complete scenario bytecode")
    checksums = {name.replace("\\", "/"): value for name, value in manifest["output_sha256"].items()}
    for name in ("text-operands.jsonl", "entries.json", "parser-dump/metadata.tsv"):
        if project.digest((reference / name).read_bytes()) != checksums[name]:
            raise ValueError(f"PC reference changed: {name}")
    metadata = {}
    for line in (reference / "parser-dump/metadata.tsv").read_text(encoding="ascii").splitlines():
        opcode, name, types = line.split("\t")
        metadata[name] = (int(opcode), types)
    if metadata.get("SetMessage2") != (198, "4,7,8") or metadata.get("AddMessage2") != (202, "4,7"):
        raise ValueError("PC message count/append operand format differs")
    entries = project.load(reference / "entries.json")
    pages = defaultdict(list)
    active = {}
    cached_index, raw_entry = None, None
    counts = Counter()
    with (reference / "text-operands.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            name = record["opcode_name"]
            if name not in ("SetMessage2", "AddMessage2"):
                continue
            index = record["entry_index"]
            if index != cached_index:
                raw_entry = (reference / "parser-dump/entries" / f"{index}.bin").read_bytes()
                if project.digest(raw_entry) != entries[index]["decoded_sha256"]:
                    raise ValueError("Decoded PC entry differs from its verified source hash")
                cached_index = index
            start, size = record["text_entry_offset"], record["byte_length"]
            if raw_entry[start:start + size].hex() != record["raw_hex"]:
                raise ValueError("PC text operand differs from decoded source bytes")
            if record["argument_index"] != 0 or record["parameter_type"] != 4:
                raise ValueError("Unexpected primary message string argument")
            end = record["instruction_entry_offset"] + record["instruction_size"]
            wanted_end = start + size + (3 if name == "SetMessage2" else 1)
            if end != wanted_end or end > len(raw_entry):
                raise ValueError("PC message count/append bytes exceed its instruction")
            item = {key: record[key] for key in (
                "entry", "entry_index", "opcode_name", "instruction_offset", "text_entry_offset",
                "byte_length", "raw_sha256", "text")}
            counts[name] += 1
            if name == "SetMessage2":
                count = struct.unpack_from("<H", raw_entry, end - 2)[0]
                item.update(read_marker_id=count, append_mode=raw_entry[end - 3],
                            following_add_operands_unverified=[])
                pages[(Path(record["entry"]).stem, count)].append(item)
                active[index] = item
            else:
                item["append_mode"] = raw_entry[end - 1]
                if index in active:
                    # Source-order adjacency is NOT a proven executable page:
                    # reset/jump/choice commands may intervene. Never concatenate.
                    active[index]["following_add_operands_unverified"].append(item)
                else:
                    counts["orphan_add_operands"] += 1
    return pages, manifest, dict(counts)


def ps3_pages(entry, units):
    pending = []
    for ui, unit in enumerate(units):
        for ii, item in enumerate(unit["items"]):
            kind = item["kind"]
            if kind == "text":
                pending.append({"id": f'{entry["json_filename"]}:{ui}:{ii}',
                                "unit": ui, "item": ii, "original_text": item["original_text"],
                                "control_suffix": item["control_suffix"]})
                control = item["control_suffix"]
            elif kind == "control_text":
                control = item["control"]
            else:
                continue
            for marker in MARKER.finditer(control):
                yield {"read_marker_id": int(marker[1], 16), "marker": marker[0],
                       "marker_item": {"unit": ui, "item": ii, "control": control},
                       "records": pending}
                pending = []
    if pending:
        yield {"read_marker_id": None, "marker": None, "marker_item": None, "records": pending}


def generate(reference, destination):
    destination = destination.resolve()
    if not destination.is_relative_to((ROOT / "work/alignment").resolve()) or destination.exists():
        raise ValueError("Choose a new output directory under ignored work/alignment/")
    meta = project.baseline()
    if project.digest(project.source_bytes()) != meta["source_eboot_sha256"]:
        raise ValueError("Current source differs from the immutable extraction")
    membership_bytes = MEMBERSHIP.read_bytes()
    membership = json.loads(membership_bytes)
    included = base_memberships(meta, membership)
    pages, pc_manifest, pc_counts = pc_pages(reference)
    pc_ids = defaultdict(list)
    for native, marker in pages:
        pc_ids[native].append(marker)
    for markers in pc_ids.values():
        markers.sort()
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".candidates-", dir=destination.parent))
    counts = Counter()
    used = set()
    baseline_files = {}
    try:
        with (stage / "candidates.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for entry in meta["entries"]:
                if entry["json_filename"] not in included or not entry["text_count"]:
                    continue
                name = entry["json_filename"]
                baseline_files[name] = entry["json_sha256"]
                baseline_bytes = (project.BASELINE / name).read_bytes()
                if project.digest(baseline_bytes) != entry["json_sha256"]:
                    raise ValueError(f"Immutable message baseline changed: {name}")
                units = json.loads(baseline_bytes)
                groups = list(ps3_pages(entry, units))
                ids = [group["read_marker_id"] for group in groups]
                pc_markers = pc_ids.get(entry["source_name"], [])
                source_contiguous = (bool(ids) and None not in ids
                                     and ids == list(range(ids[0], ids[0] + len(ids))))
                pc_contiguous = (bool(pc_markers)
                                 and pc_markers == list(range(pc_markers[0], pc_markers[0] + len(pc_markers)))
                                 and all(len(pages[entry["source_name"], marker]) == 1 for marker in pc_markers))
                comparable = source_contiguous and pc_contiguous and len(ids) == len(pc_markers)
                offset = ids[0] - pc_markers[0] if comparable else None
                counts["structurally_comparable_files" if comparable else "structurally_unresolved_files"] += 1
                for ordinal, group in enumerate(groups):
                    lookup = group["read_marker_id"] - offset if offset is not None else None
                    key = (entry["source_name"], lookup)
                    candidates = pages.get(key, []) if lookup is not None else []
                    if group["read_marker_id"] is None:
                        status = "no_ps3_read_marker"
                    elif not pc_markers:
                        status = "no_pc_filename"
                    elif not comparable:
                        status = "nonisomorphic_read_marker_sequences"
                    elif not candidates:
                        status = "no_pc_normalized_count_match"
                    else:
                        status = "unique_structural_candidate_not_context_verified"
                        used.add(key)
                    counts[status] += 1
                    counts["ps3_groups"] += 1
                    counts["ps3_editable_records"] += len(group["records"])
                    record = {"id": f"{name}:page:{ordinal}", "script": name,
                              "native_name": entry["source_name"], "payload_sha256": entry["sha256_bin"],
                              "baseline_json_sha256": entry["json_sha256"], "status": status,
                              "ps3": group, "pc_candidates": candidates,
                              "structural_match": {"rule": "same_file_equal_contiguous_sequences_with_constant_offset",
                                                   "ps3_minus_pc_read_id": offset, "pc_read_id": lookup},
                              "context_verified": False,
                              "membership_status": included[name]["status"],
                              "story_domains": included[name]["story_domains"],
                              "route_feasibility_proved": False,
                              "automatic_import_allowed": False}
                    stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        report = {"schema_version": 3, "source_sha256": meta["source_eboot_sha256"],
                  "scope": {"kind": "normal_title_base_game_messages",
                            "membership_path": MEMBERSHIP.relative_to(ROOT).as_posix(),
                            "membership_sha256": project.digest(membership_bytes),
                            "definition": membership["scope_definition"],
                            "included_scenarios": len(included),
                            "excluded_scenarios": len(meta["entries"]) - len(included),
                            "native_choice_captions_included": False,
                            "route_feasibility_proved": False},
                  "baseline_files": baseline_files, "pc_archive_sha256": pc_manifest["archive_sha256"],
                  "pc_reference_manifest": str(reference / "manifest.json"),
                  "pc_reference_manifest_sha256": project.digest((reference / "manifest.json").read_bytes()),
                  "pc_message_operand_counts": pc_counts, "pc_file_and_count_keys": len(pages),
                  "unused_pc_file_and_count_keys": len(pages) - len(used), "counts": dict(counts),
                  "candidates_sha256": project.digest((stage / "candidates.jsonl").read_bytes()),
                  "limitations": [
                      "Story ownership is source-bound independently; file/count normalization is not sentence alignment or individual route-feasibility proof.",
                      "All candidates remain unverified and ineligible for automatic import.",
                      "Following AddMessage2 operands are source-order neighbors only; branches/resets may change runtime ownership.",
                      "Original PS3 controls and PC strings are retained separately, never silently normalized or concatenated.",
                      "The PS3 marker grouping is an analysis partition, not a claim about rendered page boundaries.",
                      "Native choice companion records have no message read-marker alignment and are not candidates in this report.",
                      "No editable scripts, reference inputs, installed games or runtime gates are changed."]}
        project.save(stage / "manifest.json", report)
        stage.rename(destination)
        return report
    except BaseException:
        shutil.rmtree(stage)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = generate(args.reference.resolve(), args.output)
    print(json.dumps({"output": str(args.output), "counts": report["counts"],
                      "pc_message_operand_counts": report["pc_message_operand_counts"],
                      "automatic_import_allowed": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
        raise SystemExit(f"ERROR: {error}")
