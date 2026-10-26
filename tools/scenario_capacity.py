"""Experimental appended scenario segment; never enables production relocation."""
import struct

import project
import scenario_source


PAGE = 0x10000
ALLOCATION = 64


def _align(value, alignment):
    return (value + alignment - 1) & -alignment


def append_load_segment(image, payload):
    """Populate one unused RW PT_LOAD without extending an existing BSS range."""
    if image[:6] != b"\x7fELF\x02\x02" or not payload:
        raise ValueError("Expected ELF64 big-endian input and a nonempty segment")
    phoff = struct.unpack_from(">Q", image, 0x20)[0]
    size, count = struct.unpack_from(">HH", image, 0x36)
    if size != 56 or phoff + size * count > len(image):
        raise ValueError("Invalid ELF64 program-header table")
    headers = [struct.unpack_from(">IIQQQQQQ", image, phoff + n * size) for n in range(count)]
    unused = [n for n, row in enumerate(headers)
              if row[0] == 1 and row[1] == 6 and row[3] == row[4] == row[5] == row[6] == 0
              and row[7] == PAGE]
    if len(unused) != 1:
        raise ValueError("Expected exactly one unused ordinary RW PT_LOAD")
    mapped = [row for row in headers if row[0] == 1 and row[6]]
    if not mapped or any(row[5] > row[6] or row[2] + row[5] > len(image) for row in mapped):
        raise ValueError("Invalid existing load-segment bounds")
    # Account for memory size, NOT file size: existing BSS must remain untouched.
    address = _align(max(row[3] + row[6] for row in mapped), PAGE)
    offset = _align(len(image), PAGE)
    if address + len(payload) > 0x100000000:
        raise ValueError("Scenario segment exceeds the engine's 32-bit address space")
    if any(address < row[3] + row[6] and row[3] < address + len(payload) for row in mapped):
        raise ValueError("Appended segment overlaps existing mapped memory")
    index = unused[0]
    header_offset = phoff + index * size
    output = bytearray(image)
    output.extend(b"\0" * (offset - len(output)))
    output.extend(payload)
    # The pinned source uses zero p_paddr for its empty load headers. For the
    # new mapping use the standard matching virtual/physical address pair.
    struct.pack_into(">IIQQQQQQ", output, header_offset,
                     1, 6, offset, address, address, len(payload), len(payload), PAGE)
    if output[:header_offset] != image[:header_offset] or output[header_offset + size:len(image)] != image[header_offset + size:]:
        raise ValueError("Segment allocation changed bytes outside its unused header")
    return bytes(output), {
        "program_header_index": index, "program_header_offset": header_offset,
        "file_offset": offset, "virtual_address": address,
        "file_size": len(payload), "memory_size": len(payload),
        "alignment": PAGE, "flags": 6,
        "previous_mapped_memory_end": max(row[3] + row[6] for row in mapped),
        "original_file_size": len(image), "output_file_size": len(output),
    }


def relocate(image, replacements, kit, meta):
    """Relocate ALL scenarios into a new bounded segment, preserving 64-byte starts.

    replacements maps extracted JSON filenames to fully rebuilt payload bytes.
    Callers are responsible for reviewing the scenario codec's VM relocations.
    This validates the container, not loader acceptance or VM/runtime behavior.
    """
    scanned = scenario_source.scan(image, kit)
    expected_names = {entry.json_filename for entry, *_ in scanned}
    if set(replacements) - expected_names:
        raise ValueError("Replacement names are outside the complete scenario index")
    if len(scanned) != len(meta["entries"]):
        raise ValueError("Source index differs from extraction metadata")
    arena = bytearray()
    locations = []
    expected = {}
    for entry, original, name, chunks in scanned:
        start = _align(len(arena), ALLOCATION)
        arena.extend(b"\0" * (start - len(arena)))
        raw = replacements.get(entry.json_filename, original)
        if not isinstance(raw, bytes) or not raw:
            raise ValueError("Replacement scenario payload must be nonempty bytes")
        if entry.json_filename in replacements:
            packed = scenario_source.pack(raw, kit)
        else:
            packed = image[entry.file_offset:entry.file_offset + entry.comp_size_table]
        arena.extend(packed)
        locations.append((entry, start, len(raw), len(packed)))
        expected[entry.json_filename] = project.digest(raw)
    output, allocation = append_load_segment(image, bytes(arena))
    changed = bytearray(output)
    for entry, offset, raw_size, packed_size in locations:
        table = meta["table_start"] + entry.entry_index * 16
        struct.pack_into(">III", changed, table + 4,
                         allocation["virtual_address"] + offset, raw_size, packed_size)
    result = bytes(changed)
    # Read actual new pointers through the complete container reader. This also
    # checks all chunk flags, continuation data and neighboring slot boundaries.
    rescanned = scenario_source.scan(result, kit)
    if len(rescanned) != len(scanned):
        raise ValueError("Relocation changed the scenario count")
    for (old, before, old_name, _), (new, after, new_name, _) in zip(scanned, rescanned):
        if (old.entry_index, old.name_ptr, old_name) != (new.entry_index, new.name_ptr, new_name):
            raise ValueError("Relocation changed scenario identity")
        if new.file_offset % ALLOCATION or project.digest(after) != expected[old.json_filename]:
            raise ValueError("Relocated payload or original allocation alignment differs")
        if not allocation["file_offset"] <= new.file_offset < new.file_offset + new.comp_size_table <= len(result):
            raise ValueError("Relocated slot is outside the appended arena")
    # Original compressed data and every other original byte remain intact.
    allowed = bytearray(len(image))
    h = allocation["program_header_offset"]
    allowed[h:h + 56] = b"\1" * 56
    for entry, *_ in scanned:
        table = meta["table_start"] + entry.entry_index * 16
        allowed[table + 4:table + 16] = b"\1" * 12
    if any(a != b and not allowed[n] for n, (a, b) in enumerate(zip(image, result))):
        raise ValueError("Relocation changed an unapproved original byte")
    return result, {
        "segment": allocation, "scenario_count": len(scanned),
        "verified_payloads": len(rescanned), "scenario_start_alignment": ALLOCATION,
        "replacement_scenarios": sorted(replacements),
        "original_scenario_arena_retained": True,
        "runtime_verified": False, "production_growth_enabled": False,
        "limits": ["New PT_LOAD acceptance requires manual PS3 loader evidence",
                   "Container preservation does not prove VM growth/branch/save behavior",
                   "This does not correct proportional ASCII layout or flower placement"],
    }
