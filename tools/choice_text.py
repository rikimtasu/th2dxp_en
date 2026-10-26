"""Native command22 choice captions, separate from immutable opcode-gap views.

Existing script/baseline files are never rewritten. New companion files expose
only translated_text; the compiler changes bounded string operands and relocates
label-table offsets, retaining commands, expressions and branch targets.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import struct
import tempfile

import project
import scenario_graph
import scenario_source


def baseline_dir():
    return project.BASELINE.parent / "original-choice-text"


def companion_name(script):
    return script.removesuffix(".json") + "_choices.json"


def records(payload, kit):
    _, _, sites, _ = scenario_graph.scan_sites(payload, kit, commands={0x22: 1})
    result = []
    for site in sites:
        argument = site["operands"][0]
        if argument["status"] != "literal_string":
            raise ValueError("Native choice caption is not a bounded literal string")
        start, end = argument["offset"], argument["end"]
        raw = payload[start + 3:end]
        text = raw.decode("cp932", errors="strict")
        result.append({"operand_offset": start, "end": end, "text": text,
                       "raw_hex": payload[start:end].hex(),
                       "framing_offset": site["framing_payload_offset"]})
    return result


def units(payload, kit):
    return [{"end_reason": "native_choice_operand", "command_id": 0x22,
             "choice_index": index, "source_payload_offset": record["operand_offset"],
             "items": [{"kind": "text", "length": record["end"] - record["operand_offset"] - 3,
                        "original_text": record["text"], "translated_text": record["text"],
                        "control_suffix": "", "editable": True}]}
            for index, record in enumerate(records(payload, kit))]


def baseline():
    directory = baseline_dir()
    if not directory.exists():
        return {}
    manifest = project.load(directory / "manifest.json")
    if (manifest["schema_version"] != 1 or
            manifest["source_sha256"] != project.CONFIG["source_sha256"]):
        raise ValueError("Choice baseline source/schema differs")
    result = {}
    for entry in manifest["entries"]:
        name = entry["json_filename"]
        if name != companion_name(entry["script"]) or name in result:
            raise ValueError("Duplicate or malformed choice companion identity")
        path = directory / name
        if project.digest(path.read_bytes()) != entry["json_sha256"]:
            raise ValueError(f"Immutable choice baseline changed: {name}")
        result[name] = entry
    if (sum(entry["text_count"] for entry in result.values()) != manifest["choice_count"] or
            len(result) != manifest["script_count"]):
        raise ValueError("Choice baseline counts differ")
    return result


def copy_baseline(destination):
    """Create a complete source-only workspace for identity/diagnostic builds."""
    shutil.copytree(project.BASELINE, destination)
    for name in baseline():
        shutil.copy2(baseline_dir() / name, destination / name)


def prepare():
    """Add new source-identical companion records, never replace existing files."""
    if baseline_dir().exists():
        raise ValueError("Existing immutable choice baseline preserved; extraction is not repeated")
    source = project.source_bytes()
    kit = project.codec()
    meta = project.baseline()
    # Bind command22/23 to the original native implementations, not PC opcodes.
    for command, expected in ((0x22, 0x729B4), (0x23, 0x72A04)):
        descriptor = struct.unpack_from(">I", source, scenario_graph.COMMAND_TABLE_FILE + command * 4)[0]
        offset = kit.vaddr_to_fileoff(descriptor, kit.read_elf_program_headers(source))
        if struct.unpack_from(">I", source, offset)[0] != expected:
            raise ValueError("Native choice command dispatch differs")
    scanned = scenario_source.scan(source, kit)
    if len(scanned) != len(meta["entries"]):
        raise ValueError("Choice extraction requires the complete scenario baseline")
    entries, views = [], {}
    for entry, payload, native_name, _ in scanned:
        view = units(payload, kit)
        if not view:
            continue
        name = companion_name(entry.json_filename)
        if (project.SCRIPTS / name).exists():
            raise ValueError(f"Existing editable choice file preserved: {name}")
        views[name] = view
        entries.append({"json_filename": name, "script": entry.json_filename,
                        "source_name": native_name, "payload_sha256": entry.sha256_bin,
                        "text_count": len(view)})
    manifest = {"schema_version": 1, "source_sha256": project.digest(source),
                "script_count": len(entries), "choice_count": sum(row["text_count"] for row in entries),
                "command": "0x22 -> 0x729b4 -> 0x5e78c -> 0x6c94c; 0x23 -> 0x72a04",
                "scope": "All bounded literal command22 captions; no route/translation approval",
                "existing_baseline_and_script_files_modified": False, "entries": entries}
    created = []
    with tempfile.TemporaryDirectory(prefix="choice-extract-", dir=project.ROOT / "work") as temporary:
        stage = Path(temporary) / "baseline"
        for entry in entries:
            name = entry["json_filename"]
            project.save(stage / name, views[name])
            entry["json_sha256"] = project.digest((stage / name).read_bytes())
        project.save(stage / "manifest.json", manifest)
        try:
            for name in views:
                with (project.SCRIPTS / name).open("xb") as stream:
                    created.append(name)
                    stream.write((stage / name).read_bytes())
            stage.rename(baseline_dir())
        except Exception:
            # Only outputs created by this attempt, and only if still identical.
            for name in created:
                path = project.SCRIPTS / name
                if path.read_bytes() == (stage / name).read_bytes():
                    path.unlink()
            raise
    return manifest


def splice_literals(payload, changes):
    """Replace typed string operands and keep their symbolic label destinations."""
    code_size, label_count = struct.unpack_from("<II", payload, 4)
    code_start = 16 + label_count * 36
    if payload[:2] != b"VE" or len(payload) != code_start + code_size:
        raise ValueError("Invalid native scenario header")
    result = bytearray()
    cursor = 0
    spans = []
    for start, end, encoded in sorted(changes):
        if (not code_start <= start < end <= len(payload) or start < cursor or
                payload[start] != 10 or end != start + 3 + struct.unpack_from("<H", payload, start + 1)[0]):
            raise ValueError("Invalid or overlapping native choice operand")
        if len(encoded) > 0xFFFF:
            raise ValueError("Native choice literal exceeds its 16-bit format")
        replacement = b"\x0a" + struct.pack("<H", len(encoded)) + encoded
        result.extend(payload[cursor:start])
        result.extend(replacement)
        spans.append((start - code_start, end - code_start, len(replacement) - (end - start)))
        cursor = end
    result.extend(payload[cursor:])
    for index in range(label_count):
        field = 16 + index * 36 + 32
        target = struct.unpack_from("<I", payload, field)[0]
        if target >= code_size:
            raise ValueError("Source label target exceeds code")
        shift = 0
        for start, end, delta in spans:
            if target >= end:
                shift += delta
            elif start < target < end:
                raise ValueError("Label targets the interior of a resized choice operand")
        struct.pack_into("<I", result, field, target + shift)
    struct.pack_into("<I", result, 4, code_size + sum(delta for _, _, delta in spans))
    return bytes(result)


def rebuild(payload, edited, kit, *, allow_growth):
    """Apply validated companion translated_text fields after message rebuilding."""
    original = units(payload, kit)
    if len(original) != len(edited):
        raise ValueError("Choice caption count changed")
    source_records = records(payload, kit)
    changes = []
    for before, after, record in zip(original, edited, source_records):
        old, new = before["items"][0], after["items"][0]
        # Message growth may move these offsets; identities/order/text stay fixed.
        if (old["original_text"] != new["original_text"] or
                before["choice_index"] != after["choice_index"]):
            raise ValueError("Choice companion no longer matches source operand order/text")
        text = new["translated_text"]
        encoded = text.encode("cp932", errors="strict")
        if encoded.decode("cp932") != text or project.engine_controls(text) != project.engine_controls(old["original_text"]):
            raise ValueError("Choice encoding or native inline controls changed")
        if not allow_growth and len(encoded) > old["length"]:
            raise ValueError("Native choice growth requires complete manual engine acceptance")
        if text != old["original_text"]:
            changes.append((record["operand_offset"], record["end"], encoded))
    if not changes:
        return payload
    # Retain the kit's conservative guard against unmodeled embedded pointers.
    spans = [(row.offset_int, row.end_int) for row in kit.read_text_records_structured(payload, "cp932", None)]
    spans.extend((row["operand_offset"], row["end"]) for row in source_records)
    references = kit._find_label_name_operand_spans(payload, spans)
    if kit._scan_exact_le32_label_offset_hits(payload, text_spans=spans, label_ref_spans=references):
        raise ValueError("Unmodeled direct label offset prevents safe choice growth")
    rebuilt = splice_literals(payload, changes)
    observed = records(rebuilt, kit)
    if [row["text"] for row in observed] != [unit["items"][0]["translated_text"] for unit in edited]:
        raise ValueError("Re-extracted choice captions differ from complete translations")
    return rebuilt
