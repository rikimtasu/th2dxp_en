"""Inventory source-bound normal-story scope and reviewed translation coverage.

Run with ``inventory`` (default) to write ignored reports, or ``check`` to
exit1 until base-game text has completeness reviews. Story ownership is derived
by scenario_membership; conditional route feasibility is a separate limitation.
Neither command translates, rebuilds, launches, or changes source/script inputs.

Optional --review-evidence accepts schema_version=1, source_sha256, a review
object (kind="source_bound_scope_and_translation_review", reviewer, rationale),
memberships and translations lists. Membership claims bind script, source_name,
payload_sha256, status (base_game/anotherdays/shared/other), rationale and exact
native_spans ({file_offset, raw_hex}) and/or scenario_spans
({payload_offset, raw_hex}). These are attributed semantic reviews, not classes
inferred by byte matching. Translation claims bind record_id, original_text_sha256
and translated_text_sha256 (UTF-8), review_kind="translation_completeness" and
rationale. Optional unchanged_exceptions bind the same hashes, review_kind=
"unchanged_token_exception", exception_category="proper_name" or
"nonlinguistic_token", and rationale. Unchanged text cannot use generic
translation completeness. Assistant context reviews are not coverage approval.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import struct

import project
import scenario_source
import scenario_graph
import scenario_membership
import choice_text

ROOT = project.ROOT
OUTPUT = ROOT / "work/scenes/base-game-inventory.json"
INDEX = ROOT / "reference/ittaku/index.jsonl"
MANIFEST = ROOT / "reference/ittaku/manifest.json"
UNCHANGED_EXCEPTION_CATEGORIES = frozenset(("proper_name", "nonlinguistic_token"))


def file_hash(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reference_inventory():
    """Read candidate IDs, never promote archive names to sentence alignments."""
    if not INDEX.exists() and not MANIFEST.exists():
        return {}, {"status": "not_available", "decoded_candidate_count": 0}
    if not INDEX.exists() or not MANIFEST.exists():
        raise ValueError("PC reference index and provenance manifest must both exist")
    manifest = project.load(MANIFEST)
    counts = Counter()
    references = {}
    with INDEX.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            record = json.loads(line)
            if record["id"] != number or record["patch_sha256"] != manifest["patch_sha256"]:
                raise ValueError(f"PC reference provenance/ID mismatch at line {number}")
            kind = record["kind"]
            if kind not in ("decoded", "literal"):
                raise ValueError(f"Unknown PC reference kind at line {number}")
            counts[kind] += 1
            if kind != "decoded":
                continue
            if record["status"] != "bounded_text_run" or record["line_complete"] is not None:
                raise ValueError(f"Unexpected decoded reference classification at line {number}")
            entry = record["entry"]
            # Match the complete native name to the complete archive-entry stem;
            # do not use prefixes, numeric ranges, case folding, or fuzzy names.
            native_name = Path(entry).stem
            references.setdefault(native_name, []).append({
                "id": record["id"], "entry": entry,
                "entry_index": record["entry_index"],
                "entry_uncompressed_offset": record["entry_uncompressed_offset"],
                "byte_length": record["byte_length"],
                "text_sha256": project.digest(record["text"].encode("ascii")),
            })
    if {kind: counts[kind] for kind in ("literal", "decoded")} != manifest["record_counts"]:
        raise ValueError("PC reference record counts differ from the manifest")
    if counts["decoded"] and not manifest.get("source"):
        raise ValueError("Decoded PC candidates lack archive provenance")
    return references, {
        "status": "decoded_index_available" if counts["decoded"] else "raw_fragments_only",
        "index": INDEX.relative_to(ROOT).as_posix(), "index_sha256": file_hash(INDEX),
        "manifest": MANIFEST.relative_to(ROOT).as_posix(), "manifest_sha256": file_hash(MANIFEST),
        "patch_sha256": manifest["patch_sha256"],
        "archive_provenance": manifest.get("source"),
        "decoded_candidate_count": counts["decoded"],
        "decoded_entry_count": len({row["entry"] for rows in references.values() for row in rows}),
        "verification_scope": "Manifest provenance and index IDs/counts checked; archive checksum verification is recorded by the reference indexer, not replayed here",
        "sentence_alignment": "No alignment inferred from this index; separately recorded context reviews are inventoried below",
        "limitations": manifest["limitations"],
    }


def opening_alignment_review(originals, references, reference_report):
    """Inventory the existing review without promoting it to import approval."""
    path = ROOT / "work/alignment/opening-reviewed.json"
    if not path.exists():
        return []
    review = project.load(path)
    if review["review"]["kind"] != "assistant_japanese_context_review":
        raise ValueError("Unsupported opening alignment review kind")
    ps3, pc = review["ps3"], review["ittaku"]
    unit = originals[ps3["script"]][ps3["unit"]]
    matched = []
    for item in ps3["text_items"]:
        original = unit["items"][item["item"]]
        if original["kind"] != "text" or original["original_text"] != item["original_text"]:
            raise ValueError("Opening alignment no longer matches PS3 source")
        matched.append(original["original_text"])
    if "".join(matched) != review["review"]["japanese"]:
        raise ValueError("Opening alignment source sentence differs from reviewed Japanese")
    if [item for item in unit["items"] if item["kind"] != "text"] != ps3["controls_preserved"]:
        raise ValueError("Opening alignment source controls differ from baseline")
    provenance = reference_report.get("archive_provenance") or {}
    if provenance.get("decoded_sha256") != pc["archive_sha256"]:
        raise ValueError("Opening alignment PC archive differs from reference provenance")
    candidates = [row for row in references.get(ps3["native_name"], [])
                  if row["entry"] == pc["entry"]
                  and row["entry_uncompressed_offset"] == pc["entry_text_start"]
                  and row["byte_length"] == pc["entry_text_end"] - pc["entry_text_start"]
                  and row["text_sha256"] == project.digest(pc["text_as_stored"].encode("ascii"))]
    if len(candidates) != 1:
        raise ValueError("Opening alignment does not identify exactly one indexed PC candidate")
    return [{
        "path": path.relative_to(ROOT).as_posix(), "sha256": file_hash(path),
        "kind": review["review"]["kind"], "script": ps3["script"],
        "source_name": ps3["native_name"], "unit": ps3["unit"],
        "record_ids": [f'{ps3["script"]}:{ps3["unit"]}:{item["item"]}' for item in ps3["text_items"]],
        "pc_reference_id": candidates[0]["id"], "pc_entry": pc["entry"],
        "review_status": "assistant_context_review_only",
        "source_and_index_items_checked": True, "user_reviewed": False,
        "import_approved": False, "membership_proved": False,
    }]


def navigation_evidence(source_hash, source_units):
    observations = {}
    for path in sorted((ROOT / "work/qa/observations").glob("*.json")):
        observation = project.load(path)
        if observation["source_sha256"] != source_hash:
            raise ValueError(f"Observation source mismatch: {path}")
        name = observation["script"]
        units = source_units.get(name)
        if units is None:
            raise ValueError(f"Observation names an unknown text script: {path}")
        matched = "".join(units[pos["unit"]]["items"][pos["item"]]["original_text"]
                          for pos in observation["matched_items"]).replace("\u3000", "")
        if matched != observation["observed_japanese"]:
            raise ValueError(f"Observation does not match source text: {path}")
        observations.setdefault(name, []).append({
            "path": path.relative_to(ROOT).as_posix(), "sha256": file_hash(path),
            "source_name": observation["source_name"],
            "navigation_reported_by_user": observation["navigation_reported_by_user"],
            "new_game_first_scene_observed": observation["new_game_first_scene_observed"],
            "matched_items": observation["matched_items"],
            "proves": "Recorded source-page match and reported navigation only",
            "does_not_prove": "Base-game/AnotherDays edition selection or complete scenario membership",
        })
    return observations


def script_records(name, original, edited):
    """Check immutable structure without imposing the unvalidated byte budget."""
    if not isinstance(edited, list) or len(edited) != len(original):
        raise ValueError(f"{name}: unit count changed")
    restored = copy.deepcopy(edited)
    records = []
    native_record_index = 0
    for ui, (before, after) in enumerate(zip(original, edited)):
        if not isinstance(after, dict) or not isinstance(after.get("items"), list) or len(after["items"]) != len(before["items"]):
            raise ValueError(f"{name}:{ui}: item structure changed")
        for ii, (old, new) in enumerate(zip(before["items"], after["items"])):
            if old["kind"] not in ("text", "control_text"):
                continue
            ordinal = native_record_index
            native_record_index += 1
            if old["kind"] != "text":
                continue
            if not isinstance(new, dict) or not isinstance(new.get("translated_text"), str):
                raise ValueError(f"{name}:{ui}:{ii}: translated_text must be a string")
            value = new["translated_text"]
            restored[ui]["items"][ii]["translated_text"] = old["translated_text"]
            changed = value != old["translated_text"]
            nonblank = bool(value.strip())
            records.append({
                "id": f"{name}:{ui}:{ii}", "unit_id": f"{name}:{ui}",
                "unit": ui, "item": ii, "native_text_record_index": ordinal,
                "translation_status": "changed_unreviewed" if changed and nonblank else "unchanged" if not changed else "blank",
                "translation_changed": changed, "translation_nonblank": nonblank,
                "verified_sentence_alignment": False,
            })
    if restored != original:
        raise ValueError(f"{name}: only text.translated_text may change")
    return records


def reviewed_evidence(data, scanned, path):
    """Validate exact-source bindings, retaining attribution of semantic claims."""
    if path is None:
        return {}, {}, {"status": "not_supplied"}
    path = Path(path).resolve()
    document = project.load(path)
    review = document["review"]
    if (document["schema_version"] != 1 or document["source_sha256"] != project.digest(data)
            or review["kind"] != "source_bound_scope_and_translation_review"
            or not isinstance(review["reviewer"], str) or not review["reviewer"].strip()
            or not isinstance(review["rationale"], str) or not review["rationale"].strip()):
        raise ValueError("Review evidence lacks source identity or attributed semantic review")
    identities = {entry.json_filename: (entry, payload, name)
                  for entry, payload, name, _ in scanned}
    memberships = {}
    for claim in document["memberships"]:
        script = claim["script"]
        if script in memberships or script not in identities:
            raise ValueError(f"Duplicate/unknown reviewed membership: {script}")
        entry, payload, name = identities[script]
        if (claim["source_name"] != name or claim["payload_sha256"] != entry.sha256_bin
                or claim["status"] not in ("base_game", "anotherdays", "shared", "other")
                or not isinstance(claim["rationale"], str) or not claim["rationale"].strip()):
            raise ValueError(f"Unbound or unsupported membership claim: {script}")
        if not claim.get("native_spans") and not claim.get("scenario_spans"):
            raise ValueError(f"Membership claim needs exact native/bytecode evidence: {script}")
        for key, image, offset_key in (("native_spans", data, "file_offset"),
                                       ("scenario_spans", payload, "payload_offset")):
            for span in claim.get(key, []):
                offset = span[offset_key]
                raw = bytes.fromhex(span["raw_hex"])
                if (not raw or not isinstance(offset, int) or offset < 0
                        or image[offset:offset + len(raw)] != raw):
                    raise ValueError(f"Reviewed {key} bytes differ from immutable source: {script}")
        memberships[script] = claim
    translations = {}
    for claim in document["translations"]:
        record_id = claim["record_id"]
        if (record_id in translations or claim["review_kind"] != "translation_completeness"
                or not isinstance(claim["rationale"], str) or not claim["rationale"].strip()):
            raise ValueError(f"Duplicate/unsupported translation-completeness review: {record_id}")
        translations[record_id] = claim
    exceptions = document.get("unchanged_exceptions", [])
    for claim in exceptions:
        record_id = claim["record_id"]
        if (record_id in translations or claim["review_kind"] != "unchanged_token_exception"
                or claim["exception_category"] not in UNCHANGED_EXCEPTION_CATEGORIES
                or not isinstance(claim["rationale"], str) or not claim["rationale"].strip()):
            raise ValueError(f"Duplicate/unsupported unchanged-token exception: {record_id}")
        translations[record_id] = claim
    return memberships, translations, {
        "status": "attributed_source_bound_review", "path": str(path),
        "sha256": file_hash(path), "review": review,
        "membership_claims": len(memberships), "translation_claims": len(document["translations"]),
        "unchanged_exception_claims": len(exceptions),
        "verification_scope": "Exact immutable bytes, identities and record hashes checked; semantic completeness/exception legitimacy are attributed reviewer claims, never inferred",
    }


def apply_record_reviews(name, original, edited, records, reviews):
    for record in records:
        claim = reviews.pop(record["id"], None)
        record["verified_translation_complete"] = False
        record["verified_unchanged_exception"] = False
        record["coverage_complete"] = False
        if claim is None:
            continue
        ui, ii = record["unit"], record["item"]
        before = original[ui]["items"][ii]["original_text"]
        after = edited[ui]["items"][ii]["translated_text"]
        if (claim["original_text_sha256"] != project.digest(before.encode("utf-8"))
                or claim["translated_text_sha256"] != project.digest(after.encode("utf-8"))
                or not after.strip()):
            raise ValueError(f"Reviewed translation no longer matches source/current text: {record['id']}")
        kind = claim["review_kind"]
        if kind == "translation_completeness":
            if not record["translation_changed"] or after == before:
                raise ValueError(f"Unchanged text requires an explicit name/token exception: {record['id']}")
            record["verified_translation_complete"] = True
            record["translation_status"] = "changed_reviewed"
        elif kind == "unchanged_token_exception":
            if (record["translation_changed"] or after != before
                    or claim["exception_category"] not in UNCHANGED_EXCEPTION_CATEGORIES):
                raise ValueError(f"Unchanged-token exception does not match an unchanged record: {record['id']}")
            record["verified_unchanged_exception"] = True
            record["translation_status"] = "unchanged_exception"
            record["exception_category"] = claim["exception_category"]
        else:
            raise ValueError(f"Unsupported coverage review kind: {kind}")
        record["coverage_complete"] = True
        record["coverage_review_kind"] = kind
        record["coverage_review_rationale"] = claim["rationale"]


def inventory(review_path=None):
    data = project.source_bytes()
    source_hash = project.digest(data)
    kit = project.codec()
    meta = project.baseline()
    scanned = scenario_source.scan(data, kit)
    if len(scanned) != len(meta["entries"]):
        raise ValueError("Native source table and extraction baseline have different entry counts")
    paths = {row["json_filename"]: project.BASELINE / row["json_filename"]
             for row in meta["entries"] if row["text_count"]}
    choice_baseline = choice_text.baseline()
    paths.update({name: choice_text.baseline_dir() / name for name in choice_baseline})
    expected = set(paths)
    actual = {path.name for path in project.SCRIPTS.glob("*.json")} - {"scenario_meta.json"}
    if actual != expected or project.load(project.SCRIPTS / "scenario_meta.json") != meta:
        raise ValueError("Editable script set/metadata differs from the immutable baseline")
    references, reference_report = reference_inventory()
    originals = {name: project.load(paths[name]) for name in sorted(expected)}
    reviews = opening_alignment_review(originals, references, reference_report)
    observations = navigation_evidence(source_hash, originals)
    memberships, record_reviews, review_report = reviewed_evidence(data, scanned, review_path)
    graph_report = scenario_graph.graph(data, scanned, kit)
    project.save(scenario_graph.OUTPUT, graph_report)
    scope_report = scenario_membership.resolve(data, scanned, graph_report, kit)
    project.save(scenario_membership.OUTPUT, scope_report)
    scope_rows = {row["script"]: row for row in scope_report["scenarios"]}
    outgoing = {}
    for edge in graph_report["edges"]:
        outgoing.setdefault(edge["source_script"], []).append(edge["id"])
    startup_inclusions = {}
    for inclusion in graph_report["edition_selector"]["proof"]["seed_inclusions"]:
        startup_inclusions.setdefault(inclusion["script"], []).append(inclusion)
    calendar_contexts = {}
    for context in graph_report["native_date_scheduler"]["calendar_conditioned_targets"]:
        if context["target_script"] is not None:
            calendar_contexts.setdefault(context["target_script"], []).append(context)
    scenarios = []
    for (entry, payload, source_name, chunks), baseline in zip(scanned, meta["entries"]):
        # Compare only fields populated by the raw scan. JSON hashes and unit
        # counts are derived during extraction, not present in the native table.
        for key in ("entry_index", "filename", "json_filename", "name_ptr", "data_ptr",
                    "file_offset", "uncomp_size", "comp_size_table", "comp_size_actual",
                    "raw_chunk_size", "sha256_bin"):
            if baseline.get(key) != getattr(entry, key):
                raise ValueError(f"Source/baseline scenario metadata mismatch: {entry.json_filename}:{key}")
        if baseline["source_name"] != source_name or baseline["chunks"] != chunks:
            raise ValueError(f"Source/baseline identity mismatch: {entry.json_filename}")
        name = entry.json_filename
        units = originals.get(name, [])
        if len(units) != baseline["text_count"]:
            raise ValueError(f"Baseline unit count mismatch: {name}")
        edited = project.load(project.SCRIPTS / name) if units else []
        records = script_records(name, units, edited) if units else []
        apply_record_reviews(name, units, edited, records, record_reviews)
        choice_name = choice_text.companion_name(name)
        choice_units = originals.get(choice_name, [])
        if choice_units:
            binding = choice_baseline[choice_name]
            if binding["payload_sha256"] != entry.sha256_bin or binding["source_name"] != source_name:
                raise ValueError(f"Choice baseline refers to another source scenario: {choice_name}")
            choice_edited = project.load(project.SCRIPTS / choice_name)
            choice_records = script_records(choice_name, choice_units, choice_edited)
            apply_record_reviews(choice_name, choice_units, choice_edited, choice_records, record_reviews)
            for record in choice_records:
                record["text_surface"] = "native_choice_caption"
            records.extend(choice_records)
        context_reviews = [row for row in reviews if row["script"] == name]
        if any(row["source_name"] != source_name for row in context_reviews):
            raise ValueError(f"Alignment review source-name mismatch: {name}")
        for record in records:
            record["context_review_paths"] = [row["path"] for row in context_reviews if record["id"] in row["record_ids"]]
        labels = []
        label_count = struct.unpack_from("<I", payload, 8)[0]
        if 16 + label_count * 36 > len(payload):
            raise ValueError(f"Scenario label table exceeds payload: {name}")
        for index in range(label_count):
            offset = 16 + index * 36
            labels.append({"name": payload[offset:offset + 32].split(b"\0", 1)[0].decode("cp932", errors="backslashreplace"),
                           "code_offset": struct.unpack_from("<I", payload, offset + 32)[0]})
        navigation = observations.get(name, [])
        if any(row["source_name"] != source_name for row in navigation):
            raise ValueError(f"Observation source-name mismatch: {name}")
        counts = Counter(record["translation_status"] for record in records)
        positive = startup_inclusions.get(name, [])
        scopes = sorted({row["scope"] for row in positive})
        claim = memberships.get(name)
        source_scope = scope_rows[name]
        if claim is not None and claim["status"] != source_scope["status"]:
            raise ValueError(f"Reviewed membership contradicts closed native story ownership: {name}")
        if any(scope not in source_scope["story_domains"] for scope in scopes):
            raise ValueError(f"Closed story ownership contradicts native title inclusion: {name}")
        membership = {
            "status": source_scope["status"], "partition_status": "source_bound_dispatch",
            "story_domains": source_scope["story_domains"],
            "inactive_normal_story_program": source_scope["inactive_normal_story_program"],
            "route_feasibility_proved": False,
            "evidence_ids": ["native_table", "scenario_graph", "closed_native_story_ownership"],
            "reason": scope_report["scope_definition"],
        }
        if claim is not None:
            membership["additional_review"] = claim["rationale"]
        membership["positive_scope_inclusions"] = scopes
        membership["startup_inclusion_evidence"] = positive
        scenarios.append({
            "script": name, "source_name": source_name, "entry_index": entry.entry_index,
            "payload_sha256": entry.sha256_bin, "chunk_count": len(chunks),
            "editable_script_sha256": file_hash(project.SCRIPTS / name) if units else None,
            "choice_script": choice_name if choice_units else None,
            "choice_script_sha256": file_hash(project.SCRIPTS / choice_name) if choice_units else None,
            "unit_count": len(units) + len(choice_units), "message_unit_count": len(units),
            "choice_unit_count": len(choice_units), "editable_text_record_count": len(records),
            "translated_candidate_records": counts["changed_unreviewed"] + counts["changed_reviewed"],
            "unchanged_records": counts["unchanged"] + counts["unchanged_exception"], "blank_records": counts["blank"],
            "verified_translated_records": sum(record["verified_translation_complete"] for record in records),
            "verified_unchanged_exception_records": sum(record["verified_unchanged_exception"] for record in records),
            "covered_records": sum(record["coverage_complete"] for record in records),
            "membership": membership,
            "conditional_calendar_evidence": calendar_contexts.get(name, []),
            "graph_outgoing_edge_ids": outgoing.get(name, []),
            "labels": labels, "navigation_observations": navigation,
            "pc_reference": {"exact_name_available": bool(references.get(source_name)),
                             "match_rule": "native_name_equals_archive_entry_stem",
                             "candidates": references.get(source_name, []),
                             "verified_sentence_alignments": [],
                             "assistant_context_reviews": context_reviews},
            "records": records,
        })
    if record_reviews:
        raise ValueError(f"Review names unknown/noneditable records: {sorted(record_reviews)[:5]}")
    membership_counts = Counter(row["membership"]["status"] for row in scenarios)
    included = [row for row in scenarios
                if row["membership"]["status"] in ("base_game", "shared")
                or "base_game" in row["membership"]["positive_scope_inclusions"]]
    unresolved = [row for row in scenarios if row["membership"]["partition_status"] == "unresolved"]
    anotherdays_included = [row for row in scenarios
                           if row["membership"]["status"] in ("anotherdays", "shared")
                           or "anotherdays" in row["membership"]["positive_scope_inclusions"]]
    included_records = sum(row["editable_text_record_count"] for row in included)
    uncovered_included = sum(row["editable_text_record_count"] - row["covered_records"] for row in included)
    totals = {
        "scenarios": len(scenarios), "scripts_with_text": len(expected),
        "units": sum(row["unit_count"] for row in scenarios),
        "editable_text_records": sum(row["editable_text_record_count"] for row in scenarios),
        "native_choice_records": sum(row["choice_unit_count"] for row in scenarios),
        "translated_candidate_records": sum(row["translated_candidate_records"] for row in scenarios),
        "unchanged_records": sum(row["unchanged_records"] for row in scenarios),
        "blank_records": sum(row["blank_records"] for row in scenarios),
        "exact_pc_name_scenarios": sum(row["pc_reference"]["exact_name_available"] for row in scenarios),
        "verified_sentence_alignments": 0,
        "verified_translated_records": sum(row["verified_translated_records"] for row in scenarios),
        "verified_unchanged_exception_records": sum(row["verified_unchanged_exception_records"] for row in scenarios),
        "covered_records": sum(row["covered_records"] for row in scenarios),
        "assistant_context_reviewed_sentences": len(reviews),
        "assistant_context_reviewed_records": sum(len(row["record_ids"]) for row in reviews),
        "proved_base_game_scenarios": membership_counts["base_game"],
        "proved_anotherdays_scenarios": membership_counts["anotherdays"],
        "proved_shared_scenarios": membership_counts["shared"],
        "proved_other_scenarios": membership_counts["other"],
        "proved_base_game_inclusion_scenarios": len(included),
        "proved_base_game_inclusion_records": included_records,
        "proved_anotherdays_inclusion_scenarios": len(anotherdays_included),
        "calendar_conditioned_target_scenarios": len(calendar_contexts),
        "unresolved_membership_scenarios": len(unresolved),
        "unresolved_membership_records": sum(row["editable_text_record_count"] for row in unresolved),
    }
    # No unresolved scenario (including no-text event scripts) may disappear
    # from the denominator. Nor may an empty included scope pass vacuously.
    denominator_known = not unresolved and bool(included) and included_records > 0
    blockers = []
    if not denominator_known:
        blockers.append("Unresolved or empty scenario scope; no complete base-game denominator")
    if uncovered_included:
        blockers.append("Included text lacks exact-text-bound translation reviews or explicit unchanged name/token exceptions; context reviews are not approval")
    complete = denominator_known and uncovered_included == 0
    coverage = {
        "complete": complete, "scope": "extracted editable scenario messages and native choice captions",
        "included_base_game_records": included_records,
        "uncovered_base_game_records": uncovered_included,
        "included_base_game_reviewed_translation_records": sum(row["verified_translated_records"] for row in included),
        "included_base_game_unchanged_exception_records": sum(row["verified_unchanged_exception_records"] for row in included),
        "included_base_game_denominator_known": denominator_known,
        "blockers": blockers, "exit_status": 0 if complete else 1,
        "runtime_and_bulk_gates_unchanged": True,
    }
    evidence = {
        "native_table": {"path": "tools/scenario_source.py", "table_offset": scenario_source.TABLE_START,
                         "proves": "Complete ordered scenario identities, pointers, sizes and payloads",
                         "does_not_prove": "The table has no decoded base-game/AnotherDays membership field"},
        "scene_labels": {"path": "tools/scene_catalog.py", "proves": "Raw per-scenario label names and code offsets",
                         "does_not_prove": "Labels alone do not establish story ownership or executable route paths"},
        "pc_reference_scope": {"path": "[ittaku-subs]th2/README.TXT", "lines": [177, 182],
                               "proves": "The PC translator explicitly declined Another Days",
                               "does_not_prove": "PC entry availability, absence, or a shared name partitions PS3 content"},
        "scenario_graph": {"path": scenario_graph.OUTPUT.relative_to(ROOT).as_posix(),
                           "sha256": file_hash(scenario_graph.OUTPUT), "totals": graph_report["totals"],
                           "edition_selector": graph_report["edition_selector"],
                           "proves": "Exact source-bound load/conditional/count-jump sites with raw bytecode and native descriptor/handler provenance",
                           "does_not_prove": "Whole-VM path feasibility or an edition partition; static opening closure is not scope proof"},
        "native_title_startup": {"path": scenario_graph.TITLE_PROOF.relative_to(ROOT).as_posix(),
                                 "sha256": file_hash(scenario_graph.TITLE_PROOF),
                                 "proves": "Positive edition startup inclusion from original title-atlas rows through native callback/date dispatch; no exclusive/shared partition"},
        "source_bound_review": review_report,
        "closed_native_story_ownership": {
            "path": scenario_membership.OUTPUT.relative_to(ROOT).as_posix(),
            "sha256": file_hash(scenario_membership.OUTPUT), "totals": scope_report["totals"],
            "closed_month_domains": scope_report["closed_month_domains"],
            "proves": "Normal title-story source routing ownership from complete loader/slot ingress, month effects and the base terminal barrier",
            "does_not_prove": "Individual route feasibility, debug/replay/custom-save reachability, translation or runtime acceptance"},
    }
    return {
        "schema_version": 3, "source_sha256": source_hash,
        "baseline_meta_sha256": file_hash(project.BASELINE / "scenario_meta.json"),
        "record_id_convention": "script filename:zero-based unit:zero-based item; native_text_record_index counts text and control_text records in source order",
        "count_semantics": "Changed nonblank text is only a candidate until completeness-reviewed. Unchanged text needs a separately attributed exact-hash name/token exception and never counts as translated. Covered records are reviewed translations plus explicit exceptions. Membership is normal title-story ownership, not route feasibility. AD/standalone shared content without base ownership is deferred; every owner is retained. Alignment/approval is never inferred.",
        "limitations": ["Numeric native names, exact PC names and cast membership never establish PS3 membership",
                        "Inactive normal-story programs and separate Ikuno/Konomi-Tamaki stories remain other, not deleted or claimed globally unreachable",
                        "No original/translated/reference dialogue text is copied into this report",
                        "Native/UI/graphical text outside extracted editable records is not covered",
                        "Inventory/check do not authorize bulk translation or alter runtime gates"],
        "evidence": evidence, "pc_reference": reference_report, "alignment_reviews": reviews,
        "totals": totals, "coverage": coverage, "scenarios": scenarios,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("inventory", "check"), default="inventory")
    parser.add_argument("--check", action="store_true", help="Exit 1 when scope or base-game translation completeness is unproved")
    parser.add_argument("--review-evidence", type=Path,
                        help="Exact-source attributed membership/translation-completeness reviews; see module schema")
    args = parser.parse_args()
    report = inventory(args.review_evidence)
    project.save(OUTPUT, report)
    print(json.dumps({"output": OUTPUT.relative_to(ROOT).as_posix(),
                      "totals": report["totals"], "coverage": report["coverage"]}, ensure_ascii=False, indent=2))
    return report["coverage"]["exit_status"] if args.check or args.command == "check" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error) as error:
        raise SystemExit(f"ERROR: {error}")
