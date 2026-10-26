#!/usr/bin/env python3
"""Index local Ittaku patch bytes; optionally decode a legally held PC SDT.PAK.

Raw VCDIFF ADD bytes are compressed archive fragments, NOT dialogue lines.
No game installation is ever patched. See docs/ittaku-reference.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reference" / "ittaku"
PATCH_DIR = ROOT / "[ittaku-subs]th2"
MAX_BYTES = 256 * 1024 * 1024


class FormatError(ValueError):
    pass


class Reader:
    def __init__(self, data: bytes, start: int = 0, end: int | None = None):
        self.data, self.pos = data, start
        self.end = len(data) if end is None else end
        if not 0 <= start <= self.end <= len(data):
            raise FormatError("Section outside input")

    def take(self, count: int) -> bytes:
        if count < 0 or self.pos + count > self.end:
            raise FormatError(f"Truncated input at byte {self.pos}")
        result = self.data[self.pos:self.pos + count]
        self.pos += count
        return result

    def byte(self) -> int:
        return self.take(1)[0]

    def integer(self) -> int:
        value = 0
        for _ in range(10):
            digit = self.byte()
            value = (value << 7) | (digit & 127)
            if not digit & 128:
                return value
        raise FormatError("Oversized VCDIFF integer")

    def finished(self) -> None:
        if self.pos != self.end:
            raise FormatError(f"Unconsumed section bytes at {self.pos}")


def default_table() -> list[list[tuple[str, int, int]]]:
    table = [[("RUN", 0, 0)]]
    table.extend([[("ADD", size, 0)] for size in range(18)])
    for mode in range(9):
        table.extend([[("COPY", size, mode)] for size in [0, *range(4, 19)]])
    for mode in range(6):
        for add in range(1, 5):
            for copy in range(4, 7):
                table.append([("ADD", add, 0), ("COPY", copy, mode)])
    for mode in range(6, 9):
        for add in range(1, 5):
            table.append([("ADD", add, 0), ("COPY", 4, mode)])
    for mode in range(9):
        table.append([("COPY", 4, mode), ("ADD", 1, 0)])
    return table


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def candidate_runs(data: bytes, minimum: int):
    # Strict ASCII only: never turn arbitrary bytes into guessed translations.
    for match in re.finditer(rb"[\x20-\x7e]{" + str(minimum).encode() + rb",}", data):
        if len(re.findall(rb"[A-Za-z]", match.group())) >= 4:
            yield match


def inspect_patch(data: bytes, minimum: int):
    reader = Reader(data)
    if reader.take(4) != b"\xd6\xc3\xc4\x00":
        raise FormatError("Expected VCDIFF version 0")
    header = reader.byte()
    if header & ~4:
        raise FormatError("Secondary compression/custom code tables are unsupported")
    application = reader.take(reader.integer()) if header & 4 else b""
    table = default_table()
    records, windows = [], []
    target_total = 0
    while reader.pos < reader.end:
        number = len(windows)
        indicator = reader.byte()
        if indicator & ~7 or indicator & 3 == 3:
            raise FormatError("Unsupported VCDIFF window indicator")
        source_length = reader.integer() if indicator & 3 else 0
        source_position = reader.integer() if indicator & 3 else 0
        delta_length = reader.integer()
        delta_end = reader.pos + delta_length
        delta = Reader(data, reader.pos, delta_end)
        target_length = delta.integer()
        if target_total + target_length > MAX_BYTES:
            raise FormatError("Target exceeds 256 MiB safety limit")
        if delta.byte() != 0:
            raise FormatError("Compressed VCDIFF sections are unsupported")
        lengths = [delta.integer() for _ in range(3)]
        checksum = delta.take(4).hex() if indicator & 4 else None
        sections = []
        for length in lengths:
            sections.append(Reader(data, delta.pos, delta.pos + length))
            delta.take(length)
        delta.finished()
        literals, instructions, addresses = sections
        target_cursor = 0
        counts = {"ADD": 0, "COPY": 0, "RUN": 0}
        while instructions.pos < instructions.end:
            opcode_offset = instructions.pos
            for kind, size, mode in table[instructions.byte()]:
                if size == 0:
                    size = instructions.integer()
                if size <= 0 or target_cursor + size > target_length:
                    raise FormatError("Instruction exceeds target window")
                counts[kind] += size
                literal_offset = literals.pos
                if kind == "ADD":
                    added = literals.take(size)
                    for match in candidate_runs(added, minimum):
                        start, end = match.span()
                        records.append({
                            "kind": "literal", "status": "fragment",
                            "line_complete": False,
                            "interpretation": "raw_compressed_archive_bytes_not_verified_dialogue",
                            "text": match.group().decode("ascii"),
                            "window": number,
                            "target_offset": target_total + target_cursor + start,
                            "patch_offset": literal_offset + start,
                            "byte_length": end - start,
                            "opcode_offset": opcode_offset,
                            "add_target_offset": target_total + target_cursor,
                            "add_byte_length": size,
                            "left_boundary": "add_edge" if start == 0 else "non_ascii_or_control",
                            "right_boundary": "add_edge" if end == size else "non_ascii_or_control",
                            "context_hex": added[max(0, start - 12):min(size, end + 12)].hex(),
                        })
                elif kind == "RUN":
                    literals.take(1)
                else:
                    # Addresses need not be resolved to identify literal origins.
                    if mode < 6:
                        addresses.integer()
                    else:
                        addresses.byte()
                target_cursor += size
        for section in sections:
            section.finished()
        if target_cursor != target_length:
            raise FormatError("Instruction sizes do not match target length")
        windows.append({
            "window": number, "target_offset": target_total,
            "target_length": target_length, "source_length": source_length,
            "source_position": source_position,
            "source_kind": "original" if indicator & 1 else "prior_target" if indicator & 2 else "none",
            "data_offset": sections[0].end - lengths[0],
            "data_length": lengths[0], "instruction_length": lengths[1],
            "address_length": lengths[2], "adler32": checksum,
            "instruction_target_bytes": counts,
        })
        target_total += target_length
        reader.pos = delta_end
    return records, {"application_header": application.decode("ascii", errors="backslashreplace"),
                     "target_length": target_total, "windows": windows}


def u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise FormatError("Truncated KCAP integer")
    return struct.unpack_from("<I", data, offset)[0]


def lzss(data: bytes, expected: int) -> bytes:
    """Leaf KCAP's 4 KiB ring, LSB-first flags; reject truncated streams."""
    if not 0 <= expected <= MAX_BYTES:
        raise FormatError("Unreasonable uncompressed entry size")
    source = Reader(data)
    ring = bytearray(4096)
    cursor = 0xFEE
    result = bytearray()
    while len(result) < expected:
        flags = source.byte()
        for bit in range(8):
            if len(result) == expected:
                break
            if flags & (1 << bit):
                values = [source.byte()]
            else:
                lo, hi = source.byte(), source.byte()
                offset = lo | ((hi & 0xF0) << 4)
                count = (hi & 15) + 3
                if len(result) + count > expected:
                    raise FormatError("LZSS reference exceeds declared entry size")
                # Copy sequentially: ring references may overlap their output.
                for index in range(count):
                    value = ring[(offset + index) & 4095]
                    result.append(value)
                    ring[cursor] = value
                    cursor = (cursor + 1) & 4095
                continue
            for value in values:
                result.append(value)
                ring[cursor] = value
                cursor = (cursor + 1) & 4095
    source.finished()
    return bytes(result)


def decoded_records(archive: bytes, minimum: int):
    if archive[:4] != b"KCAP":
        raise FormatError("Decoded archive is not a supported Leaf KCAP file")
    # Known KCAP layouts, in the same detection order as the format reference.
    layouts = [(8, 32, 0, 24, 4), (8, 36, 4, 28, 4),
               (12, 36, 4, 28, 8), (16, 44, 4, 36, 12)]
    layout = None
    for base, stride, name_at, offset_at, count_at in layouts:
        count = u32(archive, count_at)
        if 0 < count <= 100000 and base + count * stride <= len(archive):
            if u32(archive, base + offset_at) == base + count * stride:
                layout = (base, stride, name_at, offset_at, count)
                break
    if layout is None:
        raise FormatError("Unrecognized KCAP directory layout")
    base, stride, name_at, offset_at, count = layout
    records = []
    unpacked_total = 0
    for index in range(count):
        entry = base + index * stride
        name_bytes = archive[entry + name_at:entry + name_at + 24].split(b"\0", 1)[0]
        name = name_bytes.decode("cp932", errors="backslashreplace")
        offset, size = u32(archive, entry + offset_at), u32(archive, entry + offset_at + 4)
        if size == 0:
            continue
        if offset < base + count * stride or offset + size > len(archive):
            raise FormatError("KCAP entry outside archive")
        packed = stride == 32 or u32(archive, entry) != 0
        content = archive[offset:offset + size]
        if packed:
            if size < 8:
                raise FormatError("Truncated KCAP packed entry")
            expected = u32(content, 4)
            unpacked_total += expected
            if unpacked_total > MAX_BYTES:
                raise FormatError("Uncompressed archive exceeds 256 MiB safety limit")
            content = lzss(content[8:], expected)
        for match in candidate_runs(content, minimum):
            start, end = match.span()
            records.append({
                "kind": "decoded", "status": "bounded_text_run",
                "line_complete": None,
                "interpretation": "decompressed_ascii_run_not_script_aligned",
                "text": match.group().decode("ascii"),
                "entry": name, "entry_index": index,
                "entry_archive_offset": offset, "entry_archive_size": size,
                "entry_uncompressed_offset": start, "byte_length": end - start,
                "left_boundary": "entry_edge" if start == 0 else "non_ascii_or_control",
                "right_boundary": "entry_edge" if end == len(content) else "non_ascii_or_control",
                "context_hex": content[max(0, start - 12):min(len(content), end + 12)].hex(),
            })
    return records


def root_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def index(args: argparse.Namespace) -> None:
    patch_dir = root_path(args.patch_dir)
    patch_path = patch_dir / "sdt.vcdiff"
    patch = patch_path.read_bytes()
    records, structure = inspect_patch(patch, args.min_length)
    manifest = {
        "schema_version": 1, "patch_path": str(patch_path),
        "patch_sha256": digest(patch), "patch_bytes": len(patch),
        "credit": "Ittaku-subs; Conman and staff credited in supplied README.TXT (2017-09-24)",
        "reuse_permission": "not_established", "structure": structure,
        "minimum_ascii_length": args.min_length, "source": None,
        "limitations": ["PC Xrated is not PS3 DX PLUS", "No PS3 alignments or imports",
                        "Raw ADD runs include compression bytes and are not verified dialogue",
                        "Readable reference requires the matching original or a verified patched PC SDT.PAK",
                        "ASCII-only candidates omit non-ASCII punctuation and text"],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.source_sdt:
        source = root_path(args.source_sdt)
        destination = OUTPUT / "SDT.PAK"
        if source == destination.resolve() or source == patch_path.resolve():
            raise ValueError("Source must be an original input, not a generated output or patch")
        original_hash = digest(source.read_bytes())
        executable = patch_dir / "xdelta3.exe"
        with tempfile.TemporaryDirectory(prefix="decode-", dir=OUTPUT) as temporary:
            decoded = Path(temporary) / "SDT.PAK"
            command = [str(executable), "-d", "-s", str(source), str(patch_path), str(decoded)]
            result = subprocess.run(command, capture_output=True, text=True, errors="replace", check=False)
            if result.returncode:
                raise FormatError(f"xdelta decode failed ({result.returncode}): {result.stderr.strip()}")
            archive = decoded.read_bytes()
            if len(archive) != structure["target_length"]:
                raise FormatError("Decoded target length differs from patch header")
            records.extend(decoded_records(archive, args.min_length))
            if digest(source.read_bytes()) != original_hash:
                raise FormatError("Source changed during decoding; outputs not published")
            manifest["source"] = {"path": str(source), "sha256": original_hash,
                                  "decoded_sha256": digest(archive), "decoded_path": str(destination),
                                  "xdelta_sha256": digest(executable.read_bytes()), "command": command}
            decoded.replace(destination)
    elif args.patched_sdt:
        source = root_path(args.patched_sdt)
        archive = source.read_bytes()
        if len(archive) != structure["target_length"]:
            raise FormatError("Patched archive length differs from the Ittaku target")
        for window in structure["windows"]:
            if not window["adler32"]:
                raise FormatError("Patch has no target checksum; cannot verify a pre-patched input")
            start = window["target_offset"]
            checksum = zlib.adler32(archive[start:start + window["target_length"]])
            if checksum != int(window["adler32"], 16):
                raise FormatError("Patched archive checksum differs from the Ittaku target")
        records.extend(decoded_records(archive, args.min_length))
        manifest["source"] = {
            "path": str(source), "kind": "verified_patched_archive",
            "sha256": digest(archive), "decoded_sha256": digest(archive),
            "target_checksums_verified": True,
        }
    for number, record in enumerate(records, 1):
        record["id"] = number
        record["patch_sha256"] = manifest["patch_sha256"]
    manifest["record_counts"] = {kind: sum(row["kind"] == kind for row in records)
                                  for kind in ("literal", "decoded")}
    # Temporary files keep an interrupted write from truncating an existing index.
    with tempfile.TemporaryDirectory(prefix="index-", dir=OUTPUT) as temporary:
        directory = Path(temporary)
        (directory / "index.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
        (directory / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for name in ("index.jsonl", "manifest.json"):
            (directory / name).replace(OUTPUT / name)
    print(json.dumps({"output": str(OUTPUT), "record_counts": manifest["record_counts"],
                      "full_pc_archive_decoded": manifest["source"] is not None}, indent=2))


def search(args: argparse.Namespace) -> None:
    query = args.query.casefold()
    matches = []
    total = 0
    with (OUTPUT / "index.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if (args.kind == "all" or record["kind"] == args.kind) and query in record["text"].casefold():
                total += 1
                if len(matches) < args.limit:
                    matches.append(record)
    if args.format == "json":
        print(json.dumps({"query": args.query, "total": total, "results": matches}, ensure_ascii=False, indent=2))
    else:
        print(f"{total} exact-substring matches; showing {len(matches)}. No PS3 alignment is implied.")
        for row in matches:
            location = (f"patch@0x{row['patch_offset']:x} target@0x{row['target_offset']:x}"
                        if row["kind"] == "literal" else
                        f"{row['entry']}+0x{row['entry_uncompressed_offset']:x}")
            print(f"[{row['id']}] {row['kind']}/{row['status']} {location}\n  {row['text']}")
        if any(row["kind"] == "literal" for row in matches):
            print("WARNING: literal results are raw compressed fragments, not verified dialogue.")


def positive(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Must be positive")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("index", help="Index VCDIFF ADD fragments, optionally decode original PC archive")
    build.add_argument("--patch-dir", default=str(PATCH_DIR), help="Patch folder; relative paths use project root")
    sources = build.add_mutually_exclusive_group()
    sources.add_argument("--source-sdt", help="Legally held ORIGINAL PC Xrated SDT.PAK (read-only input)")
    sources.add_argument("--patched-sdt", help="Already-patched PC SDT.PAK; verified against patch target checksums")
    build.add_argument("--min-length", type=positive, default=6, help="Minimum ASCII run length (default: 6)")
    build.set_defaults(handler=index)
    find = commands.add_parser("search", help="Case-insensitive exact substring search of local index")
    find.add_argument("query")
    find.add_argument("--format", choices=("text", "json"), default="text")
    find.add_argument("--kind", choices=("all", "literal", "decoded"), default="all")
    find.add_argument("--limit", type=positive, default=20)
    find.set_defaults(handler=search)
    args = parser.parse_args()
    try:
        args.handler(args)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Ittaku reference error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
