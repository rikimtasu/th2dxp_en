"""Strict PS3 scenario container codec, including continuation chunks omitted upstream."""
import hashlib
import lzma
import struct

TABLE_START = 0xEE8B4
MAX_ENTRIES = 2000
CHUNK_SIZE = 32768


def read_chunks(data, offset, slot_size, expected_size):
    end = offset + slot_size
    if offset < 0 or slot_size < 4 or end > len(data):
        raise ValueError("Scenario slot outside executable")
    position = offset
    output = bytearray()
    chunks = []
    terminal = False
    while position < end:
        prefix = struct.unpack_from(">I", data, position)[0]
        flag, size = prefix >> 24, prefix & 0xFFFFFF
        if flag not in (0x00, 0x80, 0x40) or size == 0 or position + 4 + size > end:
            raise ValueError(f"Invalid scenario chunk at 0x{position:X}")
        payload = data[position + 4:position + 4 + size]
        decoded = payload if flag == 0x40 else lzma.decompress(payload, format=lzma.FORMAT_ALONE)
        if len(decoded) > CHUNK_SIZE:
            raise ValueError("Scenario chunk exceeds 32768-byte engine chunk")
        output.extend(decoded)
        if len(output) > expected_size:
            raise ValueError("Scenario chunks exceed declared uncompressed size")
        chunks.append({"offset": position, "flag": flag, "compressed_size": size, "uncompressed_size": len(decoded)})
        position = (position + 4 + size + 3) & ~3
        if flag == 0x80 and len(output) == expected_size:
            raise ValueError("Continuation flag set on final scenario chunk")
        if flag == 0 or len(output) == expected_size:
            terminal = True
            break
    if not terminal or len(output) != expected_size or position > end or any(data[position:end]):
        raise ValueError("Scenario continuation/size/trailing data mismatch")
    return bytes(output), chunks


def read_entry(data, entry, kit, headers=None):
    if headers is None:
        headers = kit.read_elf_program_headers(data)
    offset = kit.vaddr_to_fileoff(entry.data_ptr, headers)
    return read_chunks(data, offset, entry.comp_size_table, entry.uncomp_size)[0]


def scan(data, kit):
    headers = kit.read_elf_program_headers(data)
    result = []
    for index in range(MAX_ENTRIES):
        table = TABLE_START + index * 16
        name_ptr, data_ptr, size, slot = struct.unpack_from(">IIII", data, table)
        if name_ptr == data_ptr == size == slot == 0:
            break
        if not name_ptr or not data_ptr or not size or not slot:
            raise ValueError(f"Malformed scenario index entry {index}")
        name_offset = kit.vaddr_to_fileoff(name_ptr, headers)
        name_end = data.index(0, name_offset, name_offset + 64)
        name = data[name_offset:name_end].decode("ascii", errors="strict")
        offset = kit.vaddr_to_fileoff(data_ptr, headers)
        payload, chunks = read_chunks(data, offset, slot, size)
        entry = kit.ScenarioEntry(entry_index=index, filename=f"script_{index:04d}.bin",
                                  json_filename=f"script_{index:04d}.json", name_ptr=name_ptr,
                                  data_ptr=data_ptr, file_offset=offset, uncomp_size=size,
                                  comp_size_table=slot, comp_size_actual=sum(c["compressed_size"] for c in chunks),
                                  raw_chunk_size=slot, sha256_bin=hashlib.sha256(payload).hexdigest())
        result.append((entry, payload, name, chunks))
    else:
        raise ValueError("Scenario index did not terminate within supported limit")
    ordered = sorted(result, key=lambda row: row[0].file_offset)
    for left, right in zip(ordered, ordered[1:]):
        if left[0].file_offset + left[0].comp_size_table > right[0].file_offset:
            raise ValueError("Scenario slots overlap")
    return result


def pack(payload, kit):
    output = bytearray()
    for offset in range(0, len(payload), CHUNK_SIZE):
        part = payload[offset:offset + CHUNK_SIZE]
        compressed = kit.compress_lzma_alone(part, compressor="pylzma")
        flag = 0x80 if offset + CHUNK_SIZE < len(payload) else 0
        output.extend(struct.pack(">I", flag << 24 | len(compressed)))
        output.extend(compressed)
        output.extend(b"\0" * (-len(output) % 4))
    return bytes(output)
