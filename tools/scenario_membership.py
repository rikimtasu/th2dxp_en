"""Source-bound normal-story routing ownership, not a route feasibility proof.

Title entries, native calendar domains, all literal scenario/slot loads, month
writes and the base terminal barrier establish closed normal-story ownership.
Unentered packaged programs are retained as other/inactive, not guessed from
numeric names or PC availability. Replay/debug/custom-save entry is distinct
from normal title-story membership. No text is translated or imported here.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import struct

import project
import scenario_graph
import scenario_source

OUTPUT = project.ROOT / "work/scenes/scenario-membership.json"
TITLE_DOMAINS = {"base_game": 3, "anotherdays": 10,
                 "ikuno_story": 21, "konomi_tamaki_story": 20}
NATIVE_RANGES = {
    "all_title_story_choices": (0x93590, 0x93664),
    "name_entry_variant": (0x85C94, 0x85CC4),
    "name_entry_handoff": (0x868A0, 0x868DC),
    "calendar_initializers": (0x80C60, 0x80DEC),
    "calendar_advance": (0x7A6D4, 0x7A7E4),
    "numeric_entry": (0x5E16C, 0x5E200),
    "named_entry": (0x5E0E0, 0x5E154),
    "save_resume_entry": (0x5E21C, 0x5E28C),
    "native_vm_constructor": (0x44724, 0x4497C),
    "scenario_mode_entry": (0x8BC50, 0x8BCB0),
    "formatted_calendar_load": (0x810DC, 0x81178),
    "event_selection_load": (0x83FF8, 0x8403C),
    "local_to_global_copy": (0x78384, 0x7841C),
    "float_add_operator": (0x43B18, 0x43C18),
    "terminal_command": (0x7793C, 0x77978),
    "terminal_dialog": (0x8CC78, 0x8CCE8),
    "terminal_callback": (0x8D678, 0x8D7F0),
    "title_return_precedes_scheduler": (0x8BDF4, 0x8BE38),
}


def native_ingress(data):
    """Check every direct constructor/load entry and absence of OPD exports."""
    expected = {0x44724: {0x5E148, 0x5E1F4, 0x5E280},
                0x5E0E0: {0x8BCA8}, 0x5E16C: {0x72914, 0x8BC90},
                0x5E21C: {0x8BC68}}
    observed = {target: [] for target in expected}
    for offset in range(0, 0x10E3E8, 4):
        word = struct.unpack_from(">I", data, offset)[0]
        if word & 0xFC000002 != 0x48000000:
            continue
        displacement = word & 0x3FFFFFC
        if displacement & 0x2000000:
            displacement -= 0x4000000
        target = offset + 0x10000 + displacement
        if target in observed:
            observed[target].append({"va": offset + 0x10000, "file_offset": offset,
                                     "raw_hex": data[offset:offset + 4].hex(),
                                     "linked": bool(word & 1)})
    for target, entries in expected.items():
        if {row["va"] for row in observed[target]} != entries:
            raise ValueError("Native scenario-load ingress differs from its reviewed callers")
        if struct.pack(">I", target) in data:
            raise ValueError("An exported/indirect native load entry requires separate ownership review")
    return {hex(target): rows for target, rows in observed.items()}


def closure(nodes, edges, seeds):
    known = set(nodes)
    if not set(seeds) <= known:
        raise ValueError("Story ownership seed is outside the source index")
    adjacency = defaultdict(set)
    for edge in edges:
        if edge["kind"] not in ("load_scenario", "register_event_scenario"):
            continue
        if edge["resolution"] not in ("resolved_literal", "missing_native_target"):
            raise ValueError("Dynamic scenario ingress prevents closed story ownership")
        target = edge["target_script"]
        if target is not None:
            if target not in known or edge["source_script"] not in known:
                raise ValueError("Scenario ownership edge names an unknown program")
            adjacency[edge["source_script"]].add(target)
    reached, queue = set(seeds), deque(seeds)
    while queue:
        for target in adjacency[queue.popleft()]:
            if target not in reached:
                reached.add(target)
                queue.append(target)
    return reached


def ownership(nodes, edges, roots):
    """Classify routing ownership only after the source closure proof passes."""
    owners = defaultdict(list)
    for domain, seeds in roots.items():
        for script in closure(nodes, edges, seeds):
            owners[script].append(domain)
    rows = {}
    for script in nodes:
        domains = sorted(owners[script])
        if "base_game" in domains:
            status = "shared" if len(domains) > 1 else "base_game"
        elif "anotherdays" in domains:
            # Shared AD/standalone content is still not part of base scope.
            status = "anotherdays"
        else:
            status = "other"
        rows[script] = {"status": status, "story_domains": domains,
                        "inactive_normal_story_program": not domains,
                        "route_feasibility_proved": False,
                        "proof_kind": "closed_native_normal_story_dispatch_ownership"}
    return rows


def month_writes(graph, scripts):
    writes = []
    for effect in graph["state_effects"]:
        if effect["source_script"] not in scripts or effect["kind"] == "read_global_flag_to_local":
            continue
        index = effect["operands"][0]
        if index["status"] != "literal_number":
            raise ValueError("A dynamic global index can change the story calendar")
        if index["value"] != 0:
            continue
        value = effect["operands"][1]
        if effect["kind"] != "write_global_flag" or value["status"] != "literal_number":
            raise ValueError("A nonliteral month write prevents closed story ownership")
        month = value["value"]
        if not month.is_integer() or not 0 <= month <= 127:
            raise ValueError("Month write is outside the reviewed native byte domain")
        writes.append((effect, int(month)))
    return writes


def verify_base_barrier(scanned, graph, kit):
    by_name = {name: (entry, payload) for entry, payload, name, _ in scanned}
    root, root_payload = by_name["EV_0520MORNING"]
    terminal, terminal_payload = by_name["109901000"]
    proof = []
    for entry, payload in ((root, root_payload), (terminal, terminal_payload)):
        _, labels, sites, _ = scenario_graph.scan_sites(payload, kit)
        if labels or any(site["command_id"] in (0x61, 0x62, 0x63) for site in sites):
            raise ValueError("Base calendar terminal barrier has an unreviewed bypass")
        proof.append({"script": entry.json_filename, "payload_sha256": entry.sha256_bin,
                      "sites": sites})
    loads = [site for site in proof[0]["sites"] if site["command_id"] == 0x1F]
    if len(loads) != 1 or loads[0]["operands"][0].get("value") != "109901000":
        raise ValueError("Last base calendar event no longer loads its terminal script")
    month = next((site for site in proof[1]["sites"] if site["command_id"] == 0x1E
                  and site["operands"][0].get("value") == 0), None)
    if month is None or month["operands"][1].get("value") != 0:
        raise ValueError("Terminal script no longer clears the base calendar month")
    for row, next_name in zip(proof, ("109901000", "500000000")):
        loads = [site for site in row["sites"] if site["command_id"] == 0x1F]
        ends = [site for site in row["sites"] if site["command_id"] == 0x01]
        if (len(loads) != 1 or loads[0]["operands"][0].get("value") != next_name
                or len(ends) != 1 or ends[0]["payload_offset"] <= loads[0]["payload_offset"]):
            raise ValueError("Base terminal chain has an alternate load or early scheduler return")
    for name in ("500000000", "500000002"):
        entry, payload = by_name[name]
        _, labels, sites, _ = scenario_graph.scan_sites(payload, kit)
        ends = [site for site in sites if site["command_id"] == 0x01]
        loads = [site for site in sites if site["command_id"] == 0x1F]
        if len(ends) != 1:
            raise ValueError("Shared terminal has an unreviewed scheduler return")
        if name == "500000000":
            if len(loads) != 1 or loads[0]["operands"][0].get("value") != "500000002":
                raise ValueError("Credits no longer converge on the shared title exit")
            fence = loads[0]["payload_offset"]
        else:
            fence = ends[0]["framing_payload_offset"] - 4
            if loads or payload[fence:fence + 4] != b"\x02\x08\x77\x02":
                raise ValueError("Common terminal no longer invokes the native title barrier before end")
        label_map = {}
        for label in labels:
            label_map.setdefault(label["name"], label["payload_offset"])
        for site in sites:
            if site["command_id"] not in (0x61, 0x62, 0x63):
                continue
            target = label_map.get(site["operands"][-1].get("value"))
            if target is None or not site["payload_offset"] < target <= fence:
                raise ValueError("Shared terminal branch bypasses or loops across its title exit")
        if any(label["payload_offset"] > fence for label in labels):
            raise ValueError("A terminal label bypasses the common title barrier")
        proof.append({"script": entry.json_filename, "payload_sha256": entry.sha256_bin,
                      "labels": labels, "sites": sites, "exit_fence_payload_offset": fence,
                      "exit_span_hex": payload[fence - 1:ends[0]["payload_offset"] + 3].hex()})
    # A later scripted date jump must not bypass that terminal morning. Every
    # nonzero base day assignment is paired with its April/May month write;
    # the one dynamic assignment is the source-bound April25 day+1 path.
    base_roots = {row["target_script"] for row in graph["native_date_scheduler"]["formatted_dispatches"]
                  if row["flag_equalities"]["0"] in (3, 4, 5)}
    base = closure([node["script"] for node in graph["nodes"]], graph["edges"], base_roots)
    for effect in graph["state_effects"]:
        if effect["source_script"] not in base or effect["kind"] == "read_global_flag_to_local":
            continue
        index, value = effect["operands"]
        if index.get("value") != 1:
            continue
        if value["status"] == "literal_number" and value["value"] == 0:
            continue
        if effect["kind"] != "write_global_flag":
            raise ValueError("Unreviewed copy can bypass the terminal base date")
        preceding = [row for row in graph["state_effects"]
                     if row["source_script"] == effect["source_script"]
                     and row["kind"] == "write_global_flag"
                     and row["operands"][0].get("value") == 0
                     and row["framing_payload_offset"] < effect["framing_payload_offset"]]
        if value["status"] == "literal_number":
            if not preceding:
                raise ValueError("Explicit base day jump lacks its reviewed month assignment")
            latest = max(preceding, key=lambda row: row["framing_payload_offset"])
            pair = (latest["operands"][1].get("value"), value["value"])
            if pair not in ((4, 16), (4, 18), (4, 19), (4, 20), (4, 26), (5, 7)):
                raise ValueError("Explicit base date jump escapes the reviewed terminal barrier")
            node = next(node for node in graph["nodes"] if node["script"] == effect["source_script"])
            if any(latest["payload_offset"] < label["payload_offset"] <= effect["payload_offset"]
                   for label in node["labels"]):
                raise ValueError("A label bypasses the month part of a base date assignment")
        else:
            if effect["source_name"] != "080425000" or value["raw_hex"] != "060009040000803f1702":
                raise ValueError("Unreviewed dynamic base day assignment")
            inbound = [edge for edge in graph["edges"] if edge["target_script"] == effect["source_script"]
                       and edge["source_script"] in base and edge["source_script"] != effect["source_script"]]
            calendar = {row["target_script"]: row for row in graph["native_date_scheduler"]["formatted_dispatches"]}
            if not inbound or any(calendar.get(edge["source_script"], {}).get("flag_equalities") != {"0": 4, "1": 25, "2": 0}
                                  for edge in inbound):
                raise ValueError("Dynamic day increment is not confined to the April25 morning entry")
            code_start = next(node["code_payload_offset"] for node in graph["nodes"]
                              if node["script"] == effect["source_script"])
            if any(edge["source_script"] == effect["source_script"]
                   and edge["kind"].endswith("local_jump")
                   and edge["target_code_offset"] is not None
                   and edge["target_code_offset"] + code_start
                       <= effect["payload_offset"] < edge["payload_offset"]
                   for edge in graph["edges"]):
                raise ValueError("Dynamic base day increment is crossed by a backwards local jump")
    return proof


def resolve(data, scanned, graph, kit):
    source_hash = project.digest(data)
    if graph["source_sha256"] != source_hash or len(scanned) != len(graph["nodes"]):
        raise ValueError("Story ownership graph is not bound to the complete source index")
    if graph["totals"]["unreconciled_raw_frames"]:
        raise ValueError("Unmatched supported frames prevent story ownership resolution")
    proof = scenario_graph.title_startup_evidence(data, scanned)
    ingress = native_ingress(data)
    barriers = verify_base_barrier(scanned, graph, kit)
    nodes = [node["script"] for node in graph["nodes"]]
    formatted = graph["native_date_scheduler"]["formatted_dispatches"]
    roots, domains, month_proof = {}, {}, {}
    for domain, initial in TITLE_DOMAINS.items():
        months = {3, 4, 5} if domain == "base_game" else {initial}
        while True:
            seeds = {row["target_script"] for row in formatted if row["flag_equalities"]["0"] in months}
            reached = closure(nodes, graph["edges"], seeds)
            writes = month_writes(graph, reached)
            added = {month for _, month in writes if month}
            if domain == "base_game" and not added <= {3, 4, 5}:
                raise ValueError("Base source writes a month outside its terminal-bounded calendar")
            if added <= months:
                break
            months |= added
        roots[domain], domains[domain] = sorted(seeds), sorted(months)
        month_proof[domain] = [dict(effect, assigned_month=month) for effect, month in writes]
    classified = ownership(nodes, graph["edges"], roots)
    native_ranges = {}
    for name, (begin, end) in NATIVE_RANGES.items():
        raw = data[begin - 0x10000:end - 0x10000]
        native_ranges[name] = {"va": begin, "file_offset": begin - 0x10000,
                               "raw_hex": raw.hex(), "sha256": project.digest(raw)}
    rows = []
    for entry, payload, name, chunks in scanned:
        row = classified[entry.json_filename]
        rows.append({"script": entry.json_filename, "source_name": name,
                     "payload_sha256": entry.sha256_bin, **row})
    return {"schema_version": 1, "source_sha256": source_hash,
            "scope_definition": "Normal title-story source routing ownership; conditional paths/slot selection retained, not individual route execution proof",
            "review": {"kind": "closed_native_dispatch_ownership_review", "reviewer": "assistant source/atlas review",
                       "runtime_execution_claimed": False,
                       "rationale": "Original title rows4..7 and native initializers establish four stories; complete literal loader/slot ingress, closed month writes and the May20 terminal barrier separate their normal routing domains. No PC/name-range classification is used."},
            "title_atlas": proof["atlas"],
            "title_rows": {"base_game": 4, "anotherdays": 5, "ikuno_story": 6, "konomi_tamaki_story": 7},
            "initial_months": TITLE_DOMAINS, "closed_month_domains": domains,
            "calendar_roots": roots, "month_write_proof": month_proof,
            "base_terminal_barrier": barriers, "native_ranges": native_ranges,
            "native_loader_ingress": ingress,
            "totals": {"scenarios": len(rows), "membership_counts": dict(Counter(row["status"] for row in rows)),
                       "unresolved_membership_scenarios": 0,
                       "inactive_normal_story_programs": sum(row["inactive_normal_story_program"] for row in rows)},
            "limitations": [
                "Ownership is not a witness that each conditional branch or deferred event slot is executable on a particular route.",
                "Shared AD/standalone content without base ownership remains anotherdays for base-first deferral; story_domains retains every owner.",
                "Inactive normal-story programs are retained as other; this does not authorize deletion or claim they cannot be loaded by debug, replay, modified saves or explicit numeric boot.",
                "No membership classification approves translation reuse, runtime layout, production growth or bulk import."],
            "scenarios": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    data, kit = project.source_bytes(), project.codec()
    scanned = scenario_source.scan(data, kit)
    graph = scenario_graph.graph(data, scanned, kit)
    report = resolve(data, scanned, graph, kit)
    project.save(OUTPUT, report)
    print({"output": OUTPUT.relative_to(project.ROOT).as_posix(), "totals": report["totals"]})


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error) as error:
        raise SystemExit(f"ERROR: {error}")
