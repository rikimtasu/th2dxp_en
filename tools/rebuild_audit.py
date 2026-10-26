"""Offline full-index growth experiment. Produces diagnostic ELF, never production approval."""
import copy
import json
from pathlib import Path
import struct

import project
import scenario_source

ROOT = Path(__file__).resolve().parents[1]


def main():
    original = project.source_bytes()
    kit = project.codec()
    meta = project.baseline()
    scanned = scenario_source.scan(original, kit)
    ordered = sorted(scanned, key=lambda row: row[0].file_offset)
    start = ordered[0][0].file_offset
    end = max(row[0].file_offset + row[0].comp_size_table for row in ordered)
    gaps = [(a[0].file_offset + a[0].comp_size_table, b[0].file_offset) for a, b in zip(ordered, ordered[1:])]
    if any(any(original[a:b]) for a, b in gaps):
        raise ValueError("Occupied arena gaps: refusing relocation")
    # File-backed PT_LOAD membership, not just BSS/memory size.
    phoff = struct.unpack_from(">Q", original, 0x20)[0]
    phsize, phcount = struct.unpack_from(">HH", original, 0x36)
    containing = []
    for index in range(phcount):
        row = phoff + index * phsize
        if struct.unpack_from(">I", original, row)[0] != 1:
            continue
        fileoff, vaddr, _, filesz = struct.unpack_from(">QQQQ", original, row + 8)
        if fileoff <= start and end <= fileoff + filesz:
            containing.append((fileoff, vaddr))
    if len(containing) != 1:
        raise ValueError("Scenario arena is not inside exactly one file-backed load segment")
    base_offset, base_vaddr = containing[0]
    entry, payload, source_name, chunks = scanned[0]
    units = project.load(project.BASELINE / entry.json_filename)
    edited = copy.deepcopy(units)
    item = next(i for unit in edited for i in unit["items"] if i["kind"] == "text")
    old_length = len(item["original_text"].encode("cp932"))
    marker = "[GROWTH TEST] " + "Abcdefghijklmnopqrstuvwxyz 0123456789 " * 3
    item["translated_text"] = marker
    grown = kit.rebuild_scenario_from_structured_json(payload, edited, encoding="cp932", font_table=None, allow_growth=True)
    if len(grown) <= len(payload) or len(marker.encode("cp932")) <= old_length:
        raise ValueError("Experiment does not actually grow a record")
    rebuilt_units = kit.make_structured_units(grown, kit.read_text_records_structured(grown, "cp932", None),
                                             include_offsets=False, encoding="cp932", font_table=None, decode_gaps=False)
    if rebuilt_units[0]["items"][0]["original_text"] != marker:
        raise ValueError("Grown text did not survive structured decoding")
    data = bytearray(original)
    cursor = start
    expected = {}
    for current, raw, name, chunk_info in ordered:
        # Match the upstream container's four-byte chunk alignment; original
        # allocation gaps were 64-byte aligned. Runtime acceptance is NOT assumed.
        cursor = (cursor + 3) & ~3
        replacement = grown if current.entry_index == entry.entry_index else raw
        packed = scenario_source.pack(replacement, kit) if current.entry_index == entry.entry_index else original[current.file_offset:current.file_offset + current.comp_size_table]
        if cursor + len(packed) > end:
            raise ValueError("All-entry diagnostic exceeds original arena; nothing written")
        data[cursor:cursor + len(packed)] = packed
        table = meta["table_start"] + current.entry_index * 16
        address = base_vaddr + cursor - base_offset
        struct.pack_into(">III", data, table + 4, address, len(replacement), len(packed))
        expected[current.json_filename] = project.digest(replacement)
        cursor += len(packed)
    project.verify_payloads(bytes(data), expected, meta, kit)
    # No writes outside indexed table fields and the bounded original arena.
    allowed = bytearray(len(original))
    allowed[start:end] = b"\1" * (end - start)
    for current, *_ in scanned:
        pos = meta["table_start"] + current.entry_index * 16 + 4
        allowed[pos:pos + 12] = b"\1" * 12
    if any(a != b and not allowed[i] for i, (a, b) in enumerate(zip(original, data))):
        raise ValueError("Unexpected write outside scenario arena/index")
    output = ROOT / "build/growth-probe/EBOOT.elf"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    report = {"scenario_entries": len(scanned), "multi_chunk_entries": sum(len(r[3]) > 1 for r in scanned),
              "arena_start": start, "arena_end": end, "arena_bytes": end-start,
              "original_slot_bytes": sum(r[0].comp_size_table for r in scanned),
              "zero_gap_bytes": sum(b-a for a,b in gaps), "used_bytes": cursor-start,
              "remaining_bytes": end-cursor, "growth_bytes": len(grown)-len(payload),
              "diagnostic_alignment": 4, "original_allocation_alignment": 64,
              "marker": {"script": entry.json_filename, "source_name": source_name, "unit": 0, "item": 0, "text": marker},
              "verified_payloads": len(scanned), "output": str(output), "output_sha256": project.digest(data),
              "runtime_verified": False, "production_growth_enabled": False,
              "limits": ["Label-table shifts handled by upstream codec; non-label bytecode offsets not fully reversed",
                         "Diagnostic compacts original 64-byte allocations to 4-byte chunk alignment; requires manual validation",
                         "Relocated table pointers and every decompressed payload verified offline only",
                         "Manual boot, branching, page controls, layout and save/load evidence required"]}
    project.save(ROOT / "build/growth-probe/report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f"ERROR: {error}")
