"""Source-bound PS3 transfer-site graph; never infer edition membership from names.

Run ``python -X utf8 tools/scenario_graph.py`` to write
work/scenes/scenario-graph.json. This is a static transfer-site graph, NOT a
whole-VM control-flow proof. Native title startup and date/event-slot dispatch
are source-bound; path feasibility, slot lifetime and exclusive/shared scope remain
unresolved. The reviewed original-atlas proof under work/scenes is required.
The kit gap decoder is diagnostic only (its 07-cstring interpretation does not
match the native 07/36 variable-assignment path). PC bytecode is not used here.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, deque
import json
import struct

import project
import scenario_source

OUTPUT = project.ROOT / "work/scenes/scenario-graph.json"
COMMAND_TABLE_FILE = 0xF709C
TITLE_PROOF = project.ROOT / "work/scenes/title-startup-proof.json"
COMMAND_ARITY = {0x01: 0, 0x1D: 2, 0x1E: 2, 0x1F: 1,
                 0x61: 2, 0x62: 2, 0x63: 1, 0x74: 4, 0x86: 2}
# Exact source disassembly ranges inspected for this revision. Addresses are VAs,
# not compressed scenario offsets. project.source_bytes rejects other revisions.
NATIVE_RANGES = {
    "vm_dispatch": (0x44330, 0x444A4),
    "command_registration": (0x8BCB0, 0x8BCC8),
    "command_registration_wrapper": (0x5A9A8, 0x5A9F4),
    "command_registration_store": (0x44E54, 0x44E60),
    "load_decimal_name": (0x728C8, 0x72928),
    "load_format": (0x5E16C, 0x5E200),
    "scenario_table_lookup": (0x44838, 0x44950),
    "conditional_jump": (0x75E00, 0x75EB0),
    "counted_jump": (0x75EC8, 0x75FA8),
    "unconditional_jump": (0x75FC0, 0x76040),
    "label_operand_resolution": (0x43F64, 0x4406C),
    "expression_dispatch": (0x43590, 0x43654),
    "expression_termination": (0x43E28, 0x43E80),
    "operand_advance": (0x44098, 0x440CC),
    "assignment_expression": (0x44104, 0x44154),
    "expression_variable": (0x43804, 0x438F4),
    "native_start_selector": (0x8BC50, 0x8BCB0),
    "native_start_by_name": (0x5E0E0, 0x5E154),
    "native_resume": (0x5E21C, 0x5E28C),
    "title_asset_reference": (0x933DC, 0x93408),
    "global_flag_read_command": (0x72760, 0x72848),
    "global_flag_write_command": (0x72848, 0x728C8),
    "global_flag_copy_local_command": (0x78384, 0x7841C),
    "global_flag_write": (0x79020, 0x7905C),
    "event_registration_command": (0x773F0, 0x774DC),
    "event_registration_slot_store": (0x78F9C, 0x79020),
    "event_selection_slot_pointer": (0x81778, 0x817A4),
    "event_selection_dispatch": (0x83FF8, 0x8403C),
    "scheduler_phase_selection": (0x81058, 0x81178),
    "scheduler_phase_advance": (0x80DEC, 0x81008),
    "scheduler_reentry": (0x8BE38, 0x8BEB4),
    "calendar_lookup": (0x7A608, 0x7A660),
    "calendar_special_days": (0x7A660, 0x7A6D4),
    "calendar_advance": (0x7A6D4, 0x7A7E4),
    "calendar_mode_predicate": (0x7A7E4, 0x7A820),
    "script_end_command": (0x71F38, 0x71F78),
    "vm_end_state": (0x44EF4, 0x44F00),
}


def native_evidence(data, kit):
    try:
        import capstone
    except ImportError as error:
        raise ValueError("Read-only native audit needs capstone==5.0.7") from error
    headers = kit.read_elf_program_headers(data)
    decoder = capstone.Cs(capstone.CS_ARCH_PPC,
                          capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    decoder.skipdata = True
    ranges = {}
    for name, (start, end) in NATIVE_RANGES.items():
        offset = kit.vaddr_to_fileoff(start, headers)
        raw = data[offset:offset + end - start]
        ranges[name] = {"va": start, "file_offset": offset, "byte_length": len(raw),
                        "raw_hex": raw.hex(), "sha256": project.digest(raw),
                        "disassembly": [f"{item.address:08x} {item.mnemonic} {item.op_str}".rstrip()
                                        for item in decoder.disasm(raw, start)]}
    commands = {}
    for command, expected in ((0x01, 0x71F38), (0x1D, 0x72760), (0x1E, 0x72848),
                              (0x1F, 0x728C8), (0x61, 0x75E00),
                              (0x62, 0x75EC8), (0x63, 0x75FC0),
                              (0x74, 0x773F0), (0x86, 0x78384)):
        offset = COMMAND_TABLE_FILE + 4 * command
        descriptor = struct.unpack_from(">I", data, offset)[0]
        desc_offset = kit.vaddr_to_fileoff(descriptor, headers)
        address, toc = struct.unpack_from(">II", data, desc_offset)
        if address != expected:
            raise ValueError(f"Native command {command:#x} dispatch changed")
        commands[f"0x{command:02x}"] = {
            "table_file_offset": offset, "table_raw_hex": data[offset:offset + 4].hex(),
            "descriptor_va": descriptor, "descriptor_file_offset": desc_offset,
            "descriptor_raw_hex": data[desc_offset:desc_offset + 8].hex(),
            "handler_va": address, "toc": toc,
        }
    strings = {}
    for name, literal in (("scenario_format", b"%09d.bin"), ("title_asset", b"sys/title.tpl"),
                          ("opening_movie", b"movie/th2op.pam"),
                          ("anotherdays_movie", b"movie/th2adop.pam")):
        offset = data.index(literal + b"\0")
        raw = data[offset:offset + len(literal) + 1]
        strings[name] = {"file_offset": offset, "raw_hex": raw.hex(),
                         "ascii": literal.decode("ascii")}
    return {"capstone_version": capstone.__version__, "ranges": ranges,
            "command_table_file_offset": COMMAND_TABLE_FILE,
            "commands": commands, "strings": strings,
            "findings": [
                "08 dispatches a command-table descriptor; registration supplies 0x8d commands at VA 0x8bcbc.",
                "Command 0x1f reads an operand, strtol(base 10), then formats %09d.bin and looks up the native scenario table. This is not the PC VM.",
                "Commands0x61/0x62 resolve their second operand as a conditional/counted local label;0x63 resolves its sole operand as an unconditional local jump. Branch feasibility is not evaluated.",
                "Command0x86 reads a VM-local index then copies its signed-byte value to the selected global flag; its second operand is not the assigned literal value.",
                "0x8bc50 chooses resume, numeric scenario, or supplied scenario name. The incoming mode/date/name state is tied to original title atlas choices by title-startup-proof.json; only positive seed inclusion follows.",
                "The two opening-movie asset names establish two native assets, not a scenario partition.",
                "Command0x74 stores one of24 event slots; 0x83ff8 later consumes selected_index*24+8 and stages a decimal scenario load. It is deferred/conditional, not an immediate jump.",
                "Commands0x1d/0x1e read/write byte global flags through0x799e4/0x79020; scheduler flag effects are separate from VM-local variable assignments.",
                "Expression06 consumes its following local-variable index at0x4388c; that index is not another token. Expression43550 leaves its02 terminator for the caller; operand43ed8 advances it, direct assignment44148 does not.",
            ]}


def operand(payload, start, end):
    """Read one bounded native operand without evaluating expression bytecode."""
    if start >= end:
        return {"status": "missing", "offset": start}, start
    kind = payload[start]
    if kind in (5, 10):
        prefix = 2 if kind == 5 else 3
        if start + prefix > end:
            return {"status": "truncated", "offset": start}, end
        length = payload[start + 1] if kind == 5 else struct.unpack_from("<H", payload, start + 1)[0]
        stop = start + prefix + length
        if stop > end:
            return {"status": "truncated", "offset": start}, end
        raw = payload[start + prefix:stop]
        # A literal label name has a native label-table lookup, not a string's
        # numerical value. Keep that distinction even though both store bytes.
        return {"status": "literal_label" if kind == 5 else "literal_string",
                "offset": start, "end": stop, "raw_hex": payload[start:stop].hex(),
                "value": raw.decode("cp932", errors="backslashreplace")}, stop
    if kind in (2, 0x12):
        return {"status": "omitted", "offset": start, "end": start + 1,
                "raw_hex": payload[start:start + 1].hex()}, start + 1
    if (kind == 9 and start + 7 <= end and payload[start + 1] == 4
            and payload[start + 6] == 2):
        number = struct.unpack_from("<f", payload, start + 2)[0]
        if number == number and abs(number) != float("inf"):
            return {"status": "literal_number", "offset": start, "end": start + 7,
                    "raw_hex": payload[start:start + 7].hex(), "value": number}, start + 7
    # Numeric/expression operands end at 02. The native expression parser gives
    # 06/36 a one-byte index, 08 a one-byte function ID and 09 a length byte.
    # Do not mistake index 05 or float bytes for names or statement markers.
    pos = start
    while pos < end:
        byte = payload[pos]
        if byte == 2:
            stop = pos + 1
            return {"status": "dynamic_expression", "offset": start, "end": stop,
                    "raw_hex": payload[start:stop].hex()}, stop
        if byte in (6, 8, 0x36):
            pos += 2
        elif byte == 9 and pos + 1 < end:
            pos += 2 + payload[pos + 1]
        elif byte == 10 and pos + 2 < end:
            pos += 3 + struct.unpack_from("<H", payload, pos + 1)[0]
        else:
            pos += 1
    return {"status": "unterminated_expression", "offset": start,
            "raw_hex": payload[start:end].hex()}, end


def scan_sites(payload, kit, *, commands=None):
    """Decode bounded 02/08 transfer sites, excluding length-delimited operands.

    Unknown top-level bytes remain one-byte opaque regions. Accordingly this is
    not a claimed complete instruction decoder or an executable basic-block CFG.
    Every emitted site's precise framing/bytes can be independently inspected.
    """
    arities = COMMAND_ARITY if commands is None else commands
    code_size, label_count = struct.unpack_from("<II", payload, 4)
    start = 16 + label_count * 36
    end = start + code_size
    if payload[:2] != b"VE" or end != len(payload):
        raise ValueError("Malformed native VE scenario header")
    labels = []
    for index in range(label_count):
        offset = 16 + index * 36
        code_offset = struct.unpack_from("<I", payload, offset + 32)[0]
        if code_offset >= code_size:
            raise ValueError("Scenario label exceeds native code")
        labels.append({"name": payload[offset:offset + 32].split(b"\0", 1)[0].decode("cp932"),
                       "code_offset": code_offset, "payload_offset": start + code_offset,
                       "table_payload_offset": offset, "raw_hex": payload[offset:offset + 36].hex()})
    sites, references = [], []
    pos = start
    # The kit parser's text records supply independently extracted byte spans;
    # handling non-CP932 records below also excludes their full raw text payload.
    text_records = kit.read_text_records_structured(payload, project.CONFIG["encoding"], None)
    text_starts = {record.offset_int: record.end_int for record in text_records}
    while pos < end:
        if pos in text_starts:
            pos = text_starts[pos]
            continue
        if payload[pos:pos + 4] == kit.TEXT_OPCODE and pos + 6 <= end:
            stop = pos + 6 + struct.unpack_from("<H", payload, pos + 4)[0]
            if stop > end:
                raise ValueError("Truncated native text record")
            pos = stop
            continue
        if payload[pos:pos + 2] == b"\x02\x08" and pos + 3 <= end:
            command = payload[pos + 2]
            if command in arities:
                args, stop = [], pos + 3
                for _ in range(arities[command]):
                    item, stop = operand(payload, stop, end)
                    args.append(item)
                sites.append({"payload_offset": pos + 1, "code_offset": pos + 1 - start,
                              "framing_payload_offset": pos, "command_id": command,
                              "raw_hex": payload[pos:stop].hex(), "operands": args})
                pos = stop
                continue
            pos += 3
            continue
        if payload[pos] == 8 and pos + 1 < end:
            # A command ID is never an operand's type/length byte.
            pos += 2
            continue
        # Skip bounded literal payloads before searching further command frames.
        if payload[pos] in (5, 10):
            item, stop = operand(payload, pos, end)
            if item["status"] in ("literal_label", "literal_string"):
                if item["status"] == "literal_string":
                    references.append(item)
                pos = stop
                continue
        if payload[pos] == 9 and pos + 1 < end:
            stop = pos + 2 + payload[pos + 1]
            if stop <= end:
                pos = stop
                continue
        if payload[pos:pos + 2] == b"\x07\x36":
            item, pos = operand(payload, pos + 2, end)
            # Direct assignment44148 calls43550, which leaves02 under the VM
            # cursor. That same byte may frame the following08 command.
            if item["status"] == "dynamic_expression":
                pos -= 1
            continue
        if payload[pos] == 6:
            _, pos = operand(payload, pos, end)
            continue
        pos += 1
    return start, labels, sites, references


def frame_census(payload, code_start, sites, kit):
    """Expose unmatched raw frames instead of silently claiming a complete parse."""
    records = kit.read_text_records_structured(payload, project.CONFIG["encoding"], None)
    starts = [record.offset_int for record in records]
    parsed = {site["framing_payload_offset"] for site in sites}
    counts = Counter()
    unmatched = []
    for command in COMMAND_ARITY:
        pattern = bytes((2, 8, command))
        pos = code_start
        while True:
            pos = payload.find(pattern, pos)
            if pos < 0:
                break
            index = bisect_right(starts, pos) - 1
            if index >= 0 and pos < records[index].end_int:
                counts["inside_extracted_text"] += 1
            elif pos in parsed:
                counts["decoded_site"] += 1
            else:
                counts["unreconciled_raw_frame"] += 1
                unmatched.append({"framing_payload_offset": pos, "command_id": command,
                                  "raw_context_hex": payload[pos:min(len(payload), pos + 48)].hex(),
                                  "status": "raw_pattern_not_proved_instruction_boundary"})
            pos += len(pattern)
    return {"counts": dict(sorted(counts.items())), "unmatched": unmatched}


def title_startup_evidence(data, scanned):
    """Ingest the inspected original-atlas/native startup proof, not PC labels."""
    proof = project.load(TITLE_PROOF)
    if (proof["schema_version"] != 1 or proof["source_sha256"] != project.digest(data)
            or proof["review"]["kind"] != "native_title_selector_and_original_atlas_context"
            or proof["review"]["runtime_execution_claimed"] is not False):
        raise ValueError("Title startup proof lacks exact-source/offline-review provenance")
    atlas = proof["atlas"]
    for key, hash_key in (("decoded_image", "decoded_image_sha256"),
                          ("crop_image", "crop_image_sha256"),
                          ("decryption_manifest", "decryption_manifest_sha256")):
        path = (project.ROOT / atlas[key]).resolve()
        if not path.is_relative_to(project.ROOT / "work"):
            raise ValueError("Title proof artifact is outside local work outputs")
        if project.digest(path.read_bytes()) != atlas[hash_key]:
            raise ValueError(f"Title proof artifact changed: {atlas[key]}")
    manifest = project.load(project.ROOT / atlas["decryption_manifest"])
    if manifest["output_sha256"] != atlas["decrypted_archive_sha256"]:
        raise ValueError("Title atlas no longer identifies the reviewed recovered archive")
    for row in [*proof["native_ranges"].values(), proof["mode_table"], proof["suffix_table"]]:
        offset, raw = row["file_offset"], bytes.fromhex(row["raw_hex"])
        if offset < 0 or not raw or data[offset:offset + len(raw)] != raw:
            raise ValueError("Title startup instruction/table evidence differs from source")
    identities = {entry.json_filename: (entry, name) for entry, _, name, _ in scanned}
    for seed in proof["seed_inclusions"]:
        entry, name = identities[seed["script"]]
        if (seed["source_name"] != name or seed["payload_sha256"] != entry.sha256_bin
                or seed["scope"] not in ("base_game", "anotherdays")
                or seed["claim"] != "positive_title_startup_inclusion_only"
                or seed["exclusive_membership_proved"] is not False):
            raise ValueError("Unbound or overclaimed title startup inclusion")
    return {
        "path": TITLE_PROOF.relative_to(project.ROOT).as_posix(),
        "sha256": project.digest(TITLE_PROOF.read_bytes()),
        "review": proof["review"], "atlas": atlas,
        "native_ranges": proof["native_ranges"],
        "mode_table": proof["mode_table"], "suffix_table": proof["suffix_table"],
        "seed_inclusions": proof["seed_inclusions"], "interpretation": proof["interpretation"],
        "asset_verification_scope": "Recorded DAT entry decompression/title hash and inspected decoded pixels; current proof/PNG/manifest hashes checked, not a new whole-DAT or installed-SDAT hash replay",
    }


def scheduler_evidence(data, kit, nodes, edges, effects):
    """Recover native formatted event dispatch and queued-event state contracts."""
    headers = kit.read_elf_program_headers(data)
    suffixes = []
    for phase in range(7):
        offset = 0x6415C0 + phase * 4
        pointer = struct.unpack_from(">I", data, offset)[0]
        string_offset = kit.vaddr_to_fileoff(pointer, headers)
        end = data.index(0, string_offset)
        suffixes.append({"phase": phase, "pointer_file_offset": offset,
                         "pointer_raw_hex": data[offset:offset + 4].hex(),
                         "string_va": pointer, "string_file_offset": string_offset,
                         "raw_hex": data[string_offset:end + 1].hex(),
                         "suffix": data[string_offset:end].decode("ascii"),
                         "dispatch": "slot_selection_instead_of_formatted_scenario" if phase == 5 else "formatted_scenario"})
    calendar = []
    for month in (3, 4, 5):
        offset = 0x641134 + 62 * month
        raw = data[offset:offset + 64]
        calendar.append({"flag0": month, "file_offset": offset, "raw_hex": raw.hex(),
                         "values_by_flag1_index": list(struct.unpack(">32h", raw)),
                         "address_formula": "VA 0x651134 + flag0*62 + flag1*2",
                         "note": "Neighboring rows overlap at index31/index0; this preserves the native addressing rather than imposing a PC/calendar layout"})
    special = []
    offset = 0x64145C
    while True:
        month, day = struct.unpack_from(">hh", data, offset)
        if month == -1:
            sentinel = {"file_offset": offset, "raw_hex": data[offset:offset + 2].hex()}
            break
        raw = data[offset:offset + 20]
        special.append({"flag0": month, "flag1": day, "file_offset": offset,
                        "raw_hex": raw.hex(), "name": raw[4:].split(b"\0", 1)[0].decode("cp932")})
        offset += 20
        if offset > 0x6415C0:
            raise ValueError("Special-day table did not terminate before native phase suffixes")
    mappings = []
    for node in nodes:
        name = node["source_name"]
        if not name.startswith("EV_"):
            continue
        fields = name[3:7]
        if len(fields) != 4 or not fields.isascii() or not fields.isdecimal():
            raise ValueError(f"Unresolved native formatted-event identity: {name}")
        month, day = int(fields[:2]), int(fields[2:])
        matches = [row for row in suffixes if row["phase"] != 5
                   and f"EV_{month:02d}{day:02d}{row['suffix']}" == name]
        if len(matches) != 1:
            raise ValueError(f"Event name does not resolve uniquely through native suffix table: {name}")
        phase = matches[0]["phase"]
        mappings.append({"target_script": node["script"], "target_name": name,
                         "payload_sha256": node["payload_sha256"],
                         "flag_equalities": {"0": month, "1": day, "2": phase},
                         "native_dispatch_va": 0x81140,
                         "condition": "Mode5 completes with these byte flags and no title/save/resume interruption; native EV format dispatch, not filename membership inference",
                         "native_calendar_alternate_mode": month >= 10,
                         "membership_proved": False})
    mapping_by_script = {row["target_script"]: row for row in mappings}
    conditioned_targets = []
    for edge in edges:
        mapping = mapping_by_script.get(edge["source_script"])
        if mapping is None or edge["kind"] not in ("load_scenario", "register_event_scenario"):
            continue
        conditioned_targets.append({
            "edge_id": edge["id"], "event_script": edge["source_script"],
            "event_flags": mapping["flag_equalities"], "kind": edge["kind"],
            "target_script": edge["target_script"], "target_name": edge.get("target_name"),
            "condition": edge["activation"], "membership_proved": False,
        })
    relevant_effects = []
    for effect in effects:
        index = effect["operands"][0]
        if index["status"] != "literal_number" or index["value"] in (0, 1, 2, 3, 4, 9):
            relevant_effects.append(effect["id"])
    return {
        "node_id": "@native/date-scheduler",
        "status": "source_bound_parametric_dispatch_not_whole_route_feasibility",
        "mode_callback_table": {"va": 0x65046C, "file_offset": 0x64046C, "stride": 28,
                                "scheduler_mode": 5, "scenario_mode": 6, "event_selection_mode": 7},
        "state": {"storage_va": 0x667628, "read_va": 0x799E4, "write_va": 0x79020,
                  "flag0": "first EV format field; native alternate-mode predicate flag0>=10",
                  "flag1": "second EV format field",
                  "flag2": "phase/suffix index; phase5 takes event-slot selection",
                  "flag3": "phase override (-1 means phase2+1 when flag4==1)",
                  "flag4": "enable phase advancement on scheduler entry",
                  "flag9": "scheduler initialization early-exit guard"},
        "suffixes": suffixes, "calendar_rows": calendar,
        "special_days": special, "special_days_sentinel": sentinel,
        "transition_contract": [
            "Scenario-mode cleanup 0x8be38..0x8beac may stage scheduler-mode5 with argument6 or7, unless title/other interruption paths take precedence.",
            "At 0x80e1c..0x80e50, flag4==1 selects phase=flag3 when override!=-1, otherwise phase=flag2+1; flag4!=1 preserves phase.",
            "Phase5 is changed to6 for the native calendar/special-day restrictions and March25..31/April1..7 exclusions; other paths keep5.",
            "Phase>6 clears all24 event slots, advances date through the native calendar routine, and resets phase0; later flag3=-1 and flag4=0 are stored.",
            "Phase5 at 0x81068 transfers to mode7 with the 24-slot registry pointer, not to an EV name with an empty suffix.",
            "Other phase values index the native suffix pointer table and format EV_%02d%02d%s.BIN; 0x81170 stages scenario-mode6 with that name.",
            "Calendar advancement increments day; for flag0<10 it rolls day>=32 to the next month/day1 and skips native invalid/sentinel dates; flag0>=10 takes the alternate rule with no day31 month rollover.",
        ],
        "event_registry": {"base_va": 0x667F68, "slot_count": 24, "stride": 24,
                           "fields": {"0": "second command74 operand, signed integer",
                                      "4": "third command74 operand, signed integer",
                                      "8": "copied scenario-name string"},
                           "register_command": "0x74", "register_handler_va": 0x773F0,
                           "store_va": 0x78F9C, "selected_dispatch_va": 0x83FF8,
                           "selection_semantics": "Mode7 stores the registry pointer at context+0x50, reads selected_index*24+8, strtol(base10), stages mode6. Registration/selection/overwrite conditions remain explicit."},
        "formatted_dispatches": mappings,
        "calendar_conditioned_targets": conditioned_targets,
        "scheduler_flag_effect_ids": relevant_effects,
        "unresolved": [
            "Path feasibility of conditional VM jumps, source global/local state and choices is not solved.",
            "Registered events can be overwritten/cleared and selection can be cancelled; a registration is not immediate scenario execution.",
            "Native calendar predicate flag0>=10 describes engine behavior, not an unconditional class assigned from a numeric scenario name.",
            "Route scripts may explicitly change scheduler flags; all decoded reads/writes are retained, including dynamic indices.",
            "Unknown command handlers, save/resume and native early-return paths prevent a complete exclusive/shared scenario partition.",
        ],
    }


def graph(data=None, scanned=None, kit=None):
    if data is None:
        data = project.source_bytes()
    if kit is None:
        kit = project.codec()
    if scanned is None:
        scanned = scenario_source.scan(data, kit)
    by_name = {name: entry for entry, _, name, _ in scanned}
    if len(by_name) != len(scanned):
        raise ValueError("Duplicate source scenario identities")
    nodes, edges, cross_references, state_effects = [], [], [], []
    for entry, payload, name, chunks in scanned:
        code_start, labels, sites, references = scan_sites(payload, kit)
        # Native 0x43fdc/0x44008 scans in table order and takes the first match.
        label_map = {}
        for label in labels:
            label_map.setdefault(label["name"], label)
        census = frame_census(payload, code_start, sites, kit)
        nodes.append({"script": entry.json_filename, "source_name": name,
                      "entry_index": entry.entry_index, "payload_sha256": entry.sha256_bin,
                      "table_file_offset": scenario_source.TABLE_START + entry.entry_index * 16,
                      "source_slot_file_offset": entry.file_offset, "chunks": chunks,
                      "code_payload_offset": code_start, "labels": labels, "frame_census": census})
        for site in sites:
            command = site["command_id"]
            if command in (0x1D, 0x1E, 0x86):
                state_effects.append(dict(
                    site, id=f"{entry.json_filename}:{site['payload_offset']:x}",
                    source_script=entry.json_filename, source_name=name,
                    payload_sha256=entry.sha256_bin,
                    kind={0x1D: "read_global_flag_to_local", 0x1E: "write_global_flag",
                          0x86: "write_global_flag_from_local"}[command],
                    semantics="Operands are native numeric expressions; literal values retained, dynamic expressions not guessed",
                    activation="conditional_on_reaching_site; local branches are not solved"))
                continue
            edge = dict(site, id=f"{entry.json_filename}:{site['payload_offset']:x}",
                        source_script=entry.json_filename, source_name=name,
                        payload_sha256=entry.sha256_bin,
                        native_command_evidence=f"0x{command:02x}",
                        activation="conditional_on_reaching_site; path/choice/state not evaluated",
                        target_script=None, target_code_offset=None)
            if command == 0x01:
                edge.update(kind="return_to_native_scheduler", target_node="@native/date-scheduler",
                            resolution="native_dynamic_scheduler",
                            activation="VM end-state9; native cleanup/title/save/resume conditions still apply")
                edges.append(edge)
                continue
            arg = site["operands"][3 if command == 0x74 else 0 if command in (0x1F, 0x63) else 1]
            if command in (0x1F, 0x74):
                edge["kind"] = "load_scenario" if command == 0x1F else "register_event_scenario"
                if command == 0x74:
                    edge["slot_operands"] = site["operands"][:3]
                    edge["activation"] = ("Registration site must execute; slot index0..23 survives later overwrites/clears; "
                                          "native phase5 selection reaches and selects this slot")
                    edge["native_consumer_va"] = 0x83FF8
                value = arg.get("value", "")
                if arg["status"] == "literal_string" and value.isascii() and value.isdecimal():
                    canonical = f"{int(value):09d}"
                    target = by_name.get(canonical)
                    edge.update(target_name=canonical, target_script=target.json_filename if target else None,
                                resolution="resolved_literal" if target else "missing_native_target")
                else:
                    edge["resolution"] = "dynamic_or_unhandled_load_operand"
            else:
                edge["kind"] = {0x61: "conditional_local_jump", 0x62: "counted_local_jump",
                                0x63: "unconditional_local_jump"}[command]
                if command != 0x63:
                    edge["condition"] = site["operands"][0]
                label = label_map.get(arg.get("value")) if arg["status"] == "literal_label" else None
                if label:
                    edge.update(target_script=entry.json_filename, target_name=name,
                                target_code_offset=label["code_offset"], resolution="resolved_label",
                                target_label=label["name"])
                else:
                    edge["resolution"] = "dynamic_or_missing_local_target"
            edges.append(edge)
        for item in references:
            if item.get("value") in by_name:
                cross_references.append(dict(item, source_script=entry.json_filename,
                                             target_script=by_name[item["value"]].json_filename,
                                             status="literal_reference_not_proved_transfer"))
    adjacency = {}
    for edge in edges:
        if edge["kind"] == "load_scenario" and edge["resolution"] == "resolved_literal":
            adjacency.setdefault(edge["source_script"], set()).add(edge["target_script"])
    # An observed source opening is a useful graph seed, not an edition selector.
    seed = by_name["010301000"].json_filename
    reached, queue = {seed}, deque([seed])
    while queue:
        for target in sorted(adjacency.get(queue.popleft(), ())):
            if target not in reached:
                reached.add(target)
                queue.append(target)
    startup = title_startup_evidence(data, scanned)
    scheduler = scheduler_evidence(data, kit, nodes, edges, state_effects)
    return {
        "schema_version": 2, "source_sha256": project.digest(data),
        "graph_kind": "source_bound_transfer_sites_not_complete_vm_cfg",
        "native_evidence": native_evidence(data, kit),
        "edition_selector": {"status": "title_startup_source_bound",
                             "native_selector_va": 0x8BC50,
                             "proof": startup,
                             "complete_partition_proved": False,
                             "reason": "Original title atlas rows are tied through native mode/date dispatch to positive startup seeds; full path feasibility and exclusive/shared scope remain unresolved"},
        "native_date_scheduler": scheduler,
        "totals": {"scenarios": len(nodes), "transfer_sites": len(edges),
                   "edge_kinds": dict(sorted(Counter(e["kind"] for e in edges).items())),
                   "edge_resolutions": dict(sorted(Counter(e["resolution"] for e in edges).items())),
                   "non_transfer_scenario_references": len(cross_references),
                   "state_effect_sites": len(state_effects),
                   "unreconciled_raw_frames": sum(len(node["frame_census"]["unmatched"]) for node in nodes)},
        "opening_static_closure": {"seed_script": seed, "seed_source_name": "010301000",
                                   "scripts": sorted(reached), "membership_proved": False,
                                   "semantics": "May-reach closure of literal load sites ignoring path conditions; neither inclusion nor exclusion proves edition membership"},
        "limitations": [
            "Not a full VM instruction decoder: bounded load/local-jump/end/event-registration/global-flag sites are decoded; opaque bytes and other native command handlers are not executed.",
            "Local jumps do not establish executable paths to load sites. Label anchors can point at TEXT+1, as the native VM expects.",
            "Native calendar dispatch and 24-slot event registration/selection are decoded parametrically; path feasibility, slot lifetime and all other command effects remain unresolved.",
            "An independent raw-frame census lists every unmatched frame for the supported commands outside kit-extracted text; these remain unresolved patterns, not fabricated graph edges.",
            "Only source/native/original-title-atlas reviewed seeds establish positive edition inclusion; neither numbers, PC matches nor a static closure establish exclusivity or route feasibility.",
            "Compressed-source provenance is a slot/chunk plus uncompressed payload offset, not a fictitious direct ELF byte address.",
        ],
        "nodes": nodes, "edges": edges, "state_effects": state_effects,
        "non_transfer_references": cross_references,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    report = graph()
    project.save(OUTPUT, report)
    print(json.dumps({"output": OUTPUT.relative_to(project.ROOT).as_posix(),
                      "totals": report["totals"],
                      "edition_selector_status": report["edition_selector"]["status"],
                      "positive_startup_inclusions": report["edition_selector"]["proof"]["seed_inclusions"],
                      "complete_partition_proved": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error) as error:
        raise SystemExit(f"ERROR: {error}")
