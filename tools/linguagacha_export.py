"""Export immutable PS3 Japanese text as LinguaGacha name/message JSON.

No translation, script insertion, executable/archive write or emulator operation.
One original native text item becomes one JSON row; native suffixes and record
identity remain in a separate sidecar. Unknown speaker names are never guessed.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import re
import tempfile

import project
import choice_text
import scenario_source

FORMAT_REFERENCE = "https://github.com/neavo/LinguaGacha/wiki/SupportedFileFormatEN"
FORMAT_SOURCE = (
    "https://github.com/neavo/LinguaGacha/blob/"
    "4c3bbe948c92eb8b30a9868cb9ec13d71794a74a/"
    "src/backend/file/messagejson/messagejson-format.ts"
)
DEFAULT_OUTPUT = project.ROOT / "work/linguagacha-original"
SAFE_NAME = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text_items(units, filename):
    require(isinstance(units, list), f"{filename}: expected native unit array")
    for ui, unit in enumerate(units):
        require(isinstance(unit, dict) and isinstance(unit.get("items"), list),
                f"{filename}:{ui}: malformed native unit")
        for ii, item in enumerate(unit["items"]):
            require(isinstance(item, dict) and item.get("kind") in
                    ("text", "control_text", "opcode_gap"),
                    f"{filename}:{ui}:{ii}: unknown native item")
            if item["kind"] == "text":
                yield ui, ii, item


def make_rows(units, filename):
    """Use original_text only, retaining blanks, repetitions and inline tokens."""
    rows, mapping = [], []
    for ui, ii, item in text_items(units, filename):
        original, suffix = item.get("original_text"), item.get("control_suffix")
        require(isinstance(original, str) and isinstance(suffix, str),
                f"{filename}:{ui}:{ii}: missing original text/suffix")
        require(original.encode("cp932").decode("cp932") == original,
                f"{filename}:{ui}:{ii}: non-roundtripping source CP932")
        rows.append({"name": "", "message": original})
        mapping.append({"row": len(rows) - 1, "record_id": f"{filename}:{ui}:{ii}",
                        "unit": ui, "item": ii, "control_suffix": suffix,
                        "protected_controls": project.engine_controls(original)})
    return rows, mapping


def restore_units(original, rows, filename):
    """Reconstitute editable units in memory, never write to script/ or infer names.

    Used for source round trips, not automatic translation insertion. Equal-length
    translated-row reordering cannot be detected by this positional JSON format.
    """
    require(isinstance(rows, list), f"{filename}: Message-JSON must be an array")
    positions = list(text_items(original, filename))
    require(len(rows) == len(positions), f"{filename}: Message-JSON row count changed")
    restored = copy.deepcopy(original)
    for row, (ui, ii, source) in zip(rows, positions):
        where = f"{filename}:{ui}:{ii}"
        require(isinstance(row, dict) and set(row) == {"name", "message"},
                f"{where}: expected exactly name/message fields")
        require(row["name"] == "", f"{where}: unverified speaker-name field changed")
        value = row["message"]
        require(isinstance(value, str), f"{where}: message must be a string")
        require(all(ord(c) >= 32 for c in value), f"{where}: literal control character")
        require(value.encode("cp932").decode("cp932") == value,
                f"{where}: message does not round-trip through CP932")
        if not source["original_text"].strip():
            require(value == source["original_text"], f"{where}: original blank carrier changed")
        else:
            require(value.strip(), f"{where}: original readable text was deleted")
        require(project.engine_controls(value) == project.engine_controls(source["original_text"]),
                f"{where}: ordered engine controls changed")
        require([c for c in value if 0xE000 <= ord(c) <= 0xF8FF] ==
                [c for c in source["original_text"] if 0xE000 <= ord(c) <= 0xF8FF],
                f"{where}: private glyphs changed")
        restored[ui]["items"][ii]["translated_text"] = value
    return restored


def membership_rows(meta, membership, source_sha256):
    require(membership.get("schema_version") == 1 and membership.get("source_sha256") == source_sha256,
            "Membership report identifies a different source/schema")
    expected = {entry["json_filename"]: entry for entry in meta["entries"]}
    result = {}
    for row in membership["scenarios"]:
        name = row["script"]
        require(name in expected and name not in result, "Duplicate/unknown membership scenario")
        entry = expected[name]
        require(row["source_name"] == entry["source_name"] and
                row["payload_sha256"] == entry["sha256_bin"], "Stale scenario membership binding")
        domains = row.get("story_domains")
        require(isinstance(domains, list) and all(isinstance(value, str) for value in domains),
                "Malformed story domains")
        require(row.get("status") in ("base_game", "anotherdays", "shared", "other"),
                "Unresolved scenario ownership; cannot define base-game export")
        result[name] = row
    require(set(result) == set(expected), "Membership report omits source scenarios")
    return result


def source_views(meta, choices, membership):
    """Read only the immutable baseline trees, not script/ or editorial drafts."""
    for entry in meta["entries"]:
        script = entry["json_filename"]
        owner = membership[script]
        if entry["text_count"]:
            yield {"script": script, "parent_script": script,
                   "native_name": entry["source_name"], "kind": "message",
                   "source_payload_sha256": entry["sha256_bin"],
                   "baseline_json_sha256": entry["json_sha256"],
                   "story_domains": owner["story_domains"],
                   "ownership_status": owner["status"],
                   "units": project.load(project.BASELINE / script)}
        companion = choice_text.companion_name(script)
        if companion in choices:
            choice = choices[companion]
            require(choice["payload_sha256"] == entry["sha256_bin"] and
                    choice["source_name"] == entry["source_name"], "Choice source binding differs")
            yield {"script": companion, "parent_script": script,
                   "native_name": entry["source_name"], "kind": "choice",
                   "source_payload_sha256": entry["sha256_bin"],
                   "baseline_json_sha256": choice["json_sha256"],
                   "story_domains": owner["story_domains"],
                   "ownership_status": owner["status"],
                   "units": project.load(choice_text.baseline_dir() / companion)}


def write_export(destination, views, source_info):
    """Publish fresh export trees atomically; existing outputs are never replaced."""
    destination = Path(destination)
    require(not destination.exists() and not destination.is_symlink(), "Existing export preserved; choose a new output directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts = {key: {"json_files": 0, "message_files": 0, "choice_files": 0,
                    "text_items": 0, "message_items": 0, "choice_items": 0,
                    "blank_items": 0} for key in ("base-game", "all-original")}
    files, used_names, used_ids, scenario_names = [], set(), set(), set()
    empty_views = []
    with tempfile.TemporaryDirectory(prefix=".linguagacha-export-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        for subset in counts:
            (stage / subset / "gt_input").mkdir(parents=True)
            (stage / subset / "gt_output").mkdir()
        for view in views:
            native, kind, script = view["native_name"], view["kind"], view["script"]
            require(isinstance(native, str) and SAFE_NAME.fullmatch(native), "Unsafe native scenario filename")
            require(kind in ("message", "choice"), "Unknown export view kind")
            output_name = native + ("_choices" if kind == "choice" else "") + ".json"
            require(output_name.casefold() not in used_names, "Duplicate/colliding native output filename")
            used_names.add(output_name.casefold())
            rows, mapping = make_rows(view["units"], script)
            require(restore_units(view["units"], rows, script) == view["units"],
                    f"{script}: original JSON round trip changed native units")
            ids = {row["record_id"] for row in mapping}
            require(not used_ids.intersection(ids), "Duplicate source record identity")
            used_ids.update(ids)
            if not rows:
                empty_views.append({"script": script, "native_name": native,
                                    "reason": "no editable text items; control/bytecode-only view"})
                continue
            scenario_names.add(view["parent_script"])
            subsets = ["all-original"]
            if "base_game" in view["story_domains"]:
                subsets.append("base-game")
            for subset in subsets:
                target = stage / subset / "gt_input" / output_name
                project.save(target, rows)
                # Verify the bytes actually written as Message-JSON, not just
                # the existence of a file or a converter's in-memory intent.
                reread = project.load(target)
                require(restore_units(view["units"], reread, script) == view["units"],
                        f"{script}: serialized Message-JSON changed original fragments")
                count = counts[subset]
                count["json_files"] += 1
                count[kind + "_files"] += 1
                count["text_items"] += len(rows)
                count[kind + "_items"] += len(rows)
                count["blank_items"] += sum(not row["message"].strip() for row in rows)
            sidecar = {key: value for key, value in view.items() if key != "units"}
            sidecar.update(output_file=output_name, name_policy="empty_unresolved_not_writable",
                           message_policy="one native editable text item per row; original_text only",
                           control_suffix_policy="kept here, never sent as translatable suffix text",
                           records=mapping)
            project.save(stage / "metadata/records" / output_name, sidecar)
            files.append({"output_file": output_name, "script": script,
                          "parent_script": view["parent_script"], "native_name": native,
                          "kind": kind, "story_domains": view["story_domains"],
                          "sets": subsets, "rows": len(rows)})
        manifest = {"schema_version": 1, "format": "LinguaGacha Message-JSON",
                    "format_reference": FORMAT_REFERENCE, "format_source_inspected": FORMAT_SOURCE,
                    "encoding": "UTF-8 without BOM; source text CP932",
                    "source": source_info, "counts": counts,
                    "source_scenarios_with_exported_items": len(scenario_names),
                    "unique_source_items": len(used_ids), "empty_views_not_exported": empty_views,
                    "speaker_names": "No verified native speaker mapping; all name fields deliberately empty, not asserted narration",
                    "files": files,
                    "limits": ["Names are not inferred from prose, voices, filenames, glossary or PC reference.",
                               "No merging/splitting/deduplication/stripping; original blank carrier rows remain in order.",
                               "Inline controls/name substitutions/private glyphs must be preserved during translation.",
                               "Native control_suffix and all other bytecode remain in immutable baselines/sidecars.",
                               "Pure name/message rows have no IDs; equal-count translated row reordering cannot be detected reliably.",
                               "Export is not insertion approval, translated coverage, runtime testing or redistribution permission."]}
        project.save(stage / "metadata/manifest.json", manifest)
        readme = """# Original PS3 Japanese → LinguaGacha Message-JSON

Import **base-game/gt_input** into LinguaGacha for the base-game-first project.
**all-original/gt_input** is the complete extracted PS3 scenario-message/choice
set, including AnotherDays and other packaged stories/programs. Do not import
both sets into one project: the base subset is intentionally duplicated there.

Each file is UTF-8 and contains an ordered array of {"name":"","message":"..."}.
Filenames use actual native scenario names. *_choices.json contains native choice
captions, not duplicated opcode-gap strings. Empty source carriers and repeated
lines are retained. No English drafts or Ittaku reference translations are used.

Speaker names are empty because native speaker bindings are not verified. Empty
does NOT mean every row is narration. Do not invent names; keep translated-name
output disabled. Do not delete blank rows or change row/file order or counts.
Preserve inline tokens such as \\k, \\n, <S10>, *nnk and private-use glyphs.
End-of-item engine suffixes are stored separately, never lost or translated.

Save translated files under the corresponding gt_output with identical filenames
and row order. Do not overwrite gt_input. metadata/records maps every array row
to its exact original script:unit:item and suffix; it is not translator input.
Source baselines already remain immutable in work/original-script and
work/original-choice-text; no extra copy of that whole workspace is required.

Start with base-game/gt_input/010301000.json, the previously identified New Game
opening. One source fragment stays one translated fragment, including unfinished
continuations. Future validated translations can become private structured
drafts; no automatic script insertion, game build or deployment is authorized.

Validation covers JSON serialization and original structured-unit round trips.
Native codec sample results are in metadata/manifest.json. No LinguaGacha GUI,
emulator, game installation or save was launched/modified. Proprietary original
text and these exports must remain private and out of version control/releases.
"""
        (stage / "README.md").write_text(readme, encoding="utf-8", newline="\n")
        require(not destination.exists() and not destination.is_symlink(), "Export target appeared; existing output preserved")
        stage.rename(destination)
    return manifest


def native_identity_samples(source, meta):
    """Actual original-text message/choice writer samples, no ELF staging."""
    kit = project.codec()
    results = []
    for filename in ("script_0000.json", "script_0006.json"):
        entry = next(row for row in meta["entries"] if row["json_filename"] == filename)
        payload = scenario_source.read_entry(source, kit.normalize_entry(entry), kit)
        units = project.load(project.BASELINE / filename)
        rows, _ = make_rows(units, filename)
        restored = restore_units(units, rows, filename)
        rebuilt = kit.rebuild_scenario_from_structured_json(payload, restored, encoding="cp932",
                                                           font_table=None, allow_growth=False)
        require(rebuilt == payload, f"{filename}: original Message-JSON native codec identity failed")
        result = {"script": filename, "message_items": len(rows), "payload_bytes": len(payload),
                  "original_message_native_identity": True}
        companion = choice_text.companion_name(filename)
        if (choice_text.baseline_dir() / companion).is_file():
            choices = project.load(choice_text.baseline_dir() / companion)
            choice_rows, _ = make_rows(choices, companion)
            restored_choices = restore_units(choices, choice_rows, companion)
            require(choice_text.rebuild(rebuilt, restored_choices, kit, allow_growth=False) == payload,
                    f"{filename}: original choice native codec identity failed")
            result.update(choice_items=len(choice_rows), original_choice_native_identity=True)
        results.append(result)
    return results


def export_original(destination):
    destination = Path(destination).resolve()
    work = (project.ROOT / "work").resolve()
    require(work in destination.parents, "Exports must be written into a new work/ subdirectory")
    require(not destination.exists() and not destination.is_symlink(), "Existing export preserved; choose a new output directory")
    source = project.source_bytes()
    meta = project.baseline()
    choice_manifest = project.load(choice_text.baseline_dir() / "manifest.json")
    choices = {entry["json_filename"]: entry for entry in choice_manifest["entries"]}
    membership = membership_rows(meta, project.load(project.ROOT / "work/scenes/scenario-membership.json"),
                                 project.digest(source))
    info = {"title_id": project.CONFIG["title_id"], "source_eboot_sha256": project.digest(source),
            "native_scenario_count": len(meta["entries"]),
            "message_baseline": "work/original-script", "choice_baseline": "work/original-choice-text",
            "original_native_codec_samples": native_identity_samples(source, meta)}
    manifest = write_export(destination, source_views(meta, choices, membership), info)
    print(f"Exported original Japanese to {destination}")
    for subset, counts in manifest["counts"].items():
        print(f"{subset}: {counts['json_files']} JSON files, {counts['text_items']} items "
              f"({counts['message_items']} messages, {counts['choice_items']} choices)")
    print("No script insertion, translation, game build, deployment or runtime acceptance.")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="New private output directory beneath work/; refuses overwrites")
    args = parser.parse_args()
    export_original(args.output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"ERROR: {error}")
