"""Synthetic archives and executables shared by the installer tests.

Nothing here reads game data: the DAT, SDAT and ELF shapes are the smallest
structures the real code accepts, so the tests can exercise table rewrites,
appended chunks and hash pins without 2 GB of assets.
"""
import hashlib
import struct


def sha(data):
    return hashlib.sha256(data).hexdigest()


def make_dat(entries):
    """Build a tiny DAT: header, filenames, 24-byte rows, payloads."""
    names = bytearray()
    name_offsets = []
    for name, _ in entries:
        name_offsets.append(16 + len(names))
        names += name.encode("latin1") + b"\0"
    entries_offset = 16 + len(names)
    table_end = entries_offset + 24 * len(entries)
    payload = bytearray()
    rows = bytearray()
    for (name, data), name_offset in zip(entries, name_offsets):
        rows += struct.pack(">6I", name_offset, 0, 0, len(data), 0, table_end + len(payload))
        payload += data
    header = struct.pack(">4I", len(entries), 0, 0, entries_offset)
    return bytes(header) + bytes(names) + bytes(rows) + bytes(payload)


def patched_dat(pristine, replacements):
    """Append replacement chunks in filename order and rewrite their rows."""
    pristine = bytearray(pristine)
    count, _, _, entries_offset = struct.unpack_from(">4I", pristine, 0)
    rows = {}
    for index in range(count):
        base = entries_offset + index * 24
        rows[index] = struct.unpack_from(">6I", pristine, base)
    order = []
    for index in range(count):
        name_offset = rows[index][0]
        end = pristine.find(b"\0", name_offset)
        order.append((pristine[name_offset:end].decode("latin1"), index, name_offset))
    out = bytearray(pristine)
    for name, index, name_offset in order:
        if name not in replacements:
            continue
        raw = replacements[name]
        padding = (-len(out)) % 4
        out += b"\0" * padding
        offset = len(out)
        out += raw
        _, _, unknown0, _, unknown1, _ = rows[index]
        struct.pack_into(">6I", out, entries_offset + index * 24,
                         name_offset, len(raw), unknown0, len(raw) * 3, unknown1, offset)
    return bytes(out)


def make_sdat(dat_bytes, version=3, content_id=b"", dat_size=None):
    """A synthetic NPD archive header followed by its plaintext DAT."""
    header = bytearray(144)
    header[0:4] = b"NPD\0"
    struct.pack_into(">3I", header, 4, version, 0, 0)
    header[16:16 + len(content_id)] = content_id
    struct.pack_into(">IIQ", header, 128, 0x0100000C, 0x4000,
                     len(dat_bytes) if dat_size is None else dat_size)
    return bytes(header) + dat_bytes


def elf_like(tag, length=512, seed=0):
    """A plain ELF-like image whose bytes differ per ``tag``/``seed``."""
    body = bytearray(seed.to_bytes(4, "big") + tag)
    while len(body) < length:
        body.append((len(body) * 7 + seed) & 0xFF)
    return b"\x7fELF" + bytes(body)
