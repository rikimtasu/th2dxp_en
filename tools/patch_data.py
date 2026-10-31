"""Describe the English patch as small data, and rebuild the pair from it.

The staged v0.1 artifacts are one 10.7 MB executable and a 2.2 GB archive. Almost
none of that is new data: the executable is the pristine ELF plus 38 KB of edits
and one appended 3.9 MB segment, and the archive is the pristine DAT plus eleven
replacement chunks and eleven rewritten table rows. This module measures exactly
that difference once, writes it beside a manifest, and re-applies it to prove the
shipped patch data reproduces the staged files byte-for-byte.

Two shapes are written:

``elf.edits.z``     zlib of the concatenated changed runs, offsets in the manifest
``elf.tail.z``      zlib of the segment appended past the pristine image
``archive/NNNN.bin`` one pre-compressed replacement chunk per rewritten DAT row

Applying is file-based and streaming so the 2.2 GB archive never has to fit in
memory. Every application verifies the pristine input it was given and the pinned
output hash it must produce; nothing here decides whether a patch is acceptable,
and nothing writes outside the paths its caller names.

One archive field is recorded but is *not* a reproducible target: the encrypted
``data.sdat``. ``make_npdata-pack`` forges the NPD ``title_hash`` and ``dev_hash``
from the *path string* of the input DAT (``forge_npd_title_hash``), and the block
keys derive from ``dev_hash``, so two machines re-encrypting identical data get
byte-different archives. ``output_sdat_sha256`` therefore documents what this
build produced; the installer proves the rebuilt archive by authenticating it and
reading the pinned DAT back out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1
BLOCK = 4 * 1024 * 1024
ROW = 24
#: Changed bytes closer together than this are shipped as one edit run.
MERGE_GAP = 16

DEFAULT_ELF = ROOT / "build/english-v0.1/EBOOT.elf"
DEFAULT_PRISTINE_ELF = ROOT / "EBOOT.elf"
DEFAULT_DAT = ROOT / "build/english-v0.1/assets/data.dat"
DEFAULT_PRISTINE_DAT = ROOT / "work/assets/data.dat"
DEFAULT_SDAT = ROOT / "build/english-v0.1/assets/data.sdat"
DEFAULT_PRISTINE_SDAT = ROOT / "work/assets/data.sdat"
DEFAULT_OUTPUT = ROOT / "build/patch-data-v0.1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, progress=None):
    """Hash a file, reporting (done, total) bytes so a caller can show progress."""
    path = Path(path)
    total = path.stat().st_size
    digest = hashlib.sha256()
    done = 0
    with path.open("rb") as stream:
        while chunk := stream.read(BLOCK):
            digest.update(chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, total)
    return digest.hexdigest()


def _save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# DAT table rows
# ---------------------------------------------------------------------------

def read_table(path):
    """Return (entries_offset, count, [24-byte row bytes]) for one DAT file."""
    path = Path(path)
    size = path.stat().st_size
    require(size >= 16, f"DAT is too short for a header: {path}")
    with path.open("rb") as stream:
        count, _, _, entries_offset = struct.unpack(">4I", stream.read(16))
        end = entries_offset + count * ROW
        require(count and entries_offset >= 16 and end <= size,
                f"DAT table bounds are invalid: {path}")
        rows = []
        for index in range(count):
            stream.seek(entries_offset + index * ROW)
            row = stream.read(ROW)
            require(len(row) == ROW, f"DAT table row {index} is truncated: {path}")
            rows.append(row)
    return entries_offset, count, rows


def read_name(path, entries_offset, name_offset):
    """Read one NUL-terminated archive filename, bounded by the table start."""
    require(16 <= name_offset < entries_offset, "DAT filename offset is out of range")
    with Path(path).open("rb") as stream:
        stream.seek(name_offset)
        data = stream.read(min(entries_offset - name_offset, 512))
    text, separator, _ = data.partition(b"\0")
    require(separator, "DAT filename is unterminated")
    return text.decode("latin1")


def _row_fields(row):
    return struct.unpack(">6I", row)


def _row_bytes(name_offset, compressed_size, unknown0, raw_size, unknown1, offset):
    return struct.pack(">6I", name_offset, compressed_size, unknown0, raw_size, unknown1, offset)


def align4(value):
    return value + (-value) % 4


SDAT_HEADER = 144


def read_sdat_header(path):
    """Read the NPD header fields the encryptor must reproduce."""
    with Path(path).open("rb") as stream:
        header = stream.read(SDAT_HEADER)
    require(len(header) == SDAT_HEADER and header[:4] == b"NPD\0",
            f"Expected a complete NPD/SDAT header: {path}")
    version, license_type, data_type = struct.unpack_from(">3I", header, 4)
    flags, block, size = struct.unpack_from(">IIQ", header, 128)
    require(version in (1, 2, 3, 4) and license_type == 0 and flags & 0x01000000,
            "The archive is not a supported license-0 SDAT")
    require(block == 0x4000, "The archive block size is not the supported 16 KiB")
    content = header[16:64]
    text, separator, padding = content.partition(b"\0")
    require(separator and len(text) < 48 and not any(padding)
            and all(32 <= byte <= 126 for byte in text),
            "The archive content ID cannot be reproduced safely")
    return {"version": version, "license": license_type, "type": data_type,
            "content_id": text.decode("ascii"), "flags": flags,
            "block_size": block, "dat_size": size}


# ---------------------------------------------------------------------------
# Executable patch
# ---------------------------------------------------------------------------

def edit_runs(pristine, patched, *, gap=MERGE_GAP):
    """Return merged ``(offset, length)`` runs covering every changed prefix byte.

    Bytes past the pristine length are not edits: they are the appended segment
    and are shipped separately, so the runs always stay inside the source image.
    """
    runs = []
    for index in range(min(len(pristine), len(patched))):
        if pristine[index] == patched[index]:
            continue
        if runs and (index == runs[-1][1] or index - runs[-1][1] <= gap):
            runs[-1][1] = index + 1
        else:
            runs.append([index, index + 1])
    return [(start, end - start) for start, end in runs]


def build_elf_patch(pristine_path, patched_path, output_dir):
    """Write the executable diff and return its manifest section."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pristine = Path(pristine_path).read_bytes()
    patched = Path(patched_path).read_bytes()
    require(patched[:4] == b"\x7fELF" and pristine[:4] == b"\x7fELF",
            "Both executable inputs must be plain ELF images")
    require(len(patched) >= len(pristine), "The patched executable is shorter than the pristine image")
    edits = edit_runs(pristine, patched)
    payload = bytearray()
    for offset, length in edits:
        payload += patched[offset:offset + length]
    tail = patched[len(pristine):]
    (output_dir / "elf.edits.z").write_bytes(zlib.compress(bytes(payload), 9))
    (output_dir / "elf.tail.z").write_bytes(zlib.compress(tail, 9))
    return {
        "source_size": len(pristine), "source_sha256": sha256_bytes(pristine),
        "output_size": len(patched), "output_sha256": sha256_bytes(patched),
        "edits_file": "elf.edits.z",
        "edits_file_sha256": sha256_file(output_dir / "elf.edits.z"),
        "edits_bytes": len(payload), "edits_sha256": sha256_bytes(bytes(payload)),
        "edits": [[offset, length] for offset, length in edits],
        "tail_file": "elf.tail.z",
        "tail_file_sha256": sha256_file(output_dir / "elf.tail.z"),
        "tail_bytes": len(tail), "tail_sha256": sha256_bytes(tail),
    }


def _checked_edits(spec, edits):
    require(len(edits) == spec["edits_bytes"], "Shipped edit payload length differs from the manifest")
    require(sha256_bytes(edits) == spec["edits_sha256"], "Shipped edit payload hash differs from the manifest")
    position, previous_end = 0, -1
    for offset, length in spec["edits"]:
        require(isinstance(offset, int) and isinstance(length, int) and offset >= 0 and length > 0,
                "Manifest edit run is malformed")
        require(offset >= previous_end, "Manifest edit runs overlap or are unordered")
        require(offset + length <= spec["source_size"], "Manifest edit run exceeds the pristine image")
        previous_end = offset + length
        position += length
    require(position == len(edits), "Manifest edit runs do not cover the edit payload")


def _decompress(path, what):
    try:
        return zlib.decompress(Path(path).read_bytes())
    except zlib.error as error:
        raise ValueError(f"Shipped {what} is corrupt: {error}") from error


def apply_elf_patch(source, target, patch_dir, spec):
    """Rebuild the patched executable from ``source``; verify both ends."""
    patch_dir, source, target = Path(patch_dir), Path(source), Path(target)
    pristine = source.read_bytes()
    require(len(pristine) == spec["source_size"],
            f"Pristine executable size differs from the patch data ({len(pristine)} bytes)")
    require(sha256_bytes(pristine) == spec["source_sha256"],
            "Pristine executable does not match the patch data; this is not BLJM60381's EBOOT")
    edits = _decompress(patch_dir / spec["edits_file"], "executable edit payload")
    _checked_edits(spec, edits)
    tail = _decompress(patch_dir / spec["tail_file"], "appended segment")
    require(len(tail) == spec["tail_bytes"], "Shipped appended segment length differs from the manifest")
    require(sha256_bytes(tail) == spec["tail_sha256"], "Shipped appended segment hash differs from the manifest")
    image = bytearray(pristine)
    position = 0
    for offset, length in spec["edits"]:
        image[offset:offset + length] = edits[position:position + length]
        position += length
    image += tail
    require(len(image) == spec["output_size"], "Rebuilt executable length differs from the pinned image")
    require(sha256_bytes(image) == spec["output_sha256"],
            "Rebuilt executable does not match the pinned patched image")
    Path(target).write_bytes(image)
    return {"output": str(target), "output_size": len(image),
            "output_sha256": spec["output_sha256"], "edits": len(spec["edits"])}


# ---------------------------------------------------------------------------
# Archive patch
# ---------------------------------------------------------------------------

def build_archive_patch(pristine_dat, patched_dat, output_dir, *, source_sdat=None,
                        output_sdat=None):
    """Write one chunk per rewritten row and describe the appended region."""
    output_dir = Path(output_dir)
    (output_dir / "archive").mkdir(parents=True, exist_ok=True)
    pristine_dat, patched_dat = Path(pristine_dat), Path(patched_dat)
    pristine_offset, pristine_count, pristine_rows = read_table(pristine_dat)
    patched_offset, patched_count, patched_rows = read_table(patched_dat)
    require((pristine_offset, pristine_count) == (patched_offset, patched_count),
            "The patched DAT table moved; this patch data cannot describe it")
    pristine_size, patched_size = pristine_dat.stat().st_size, patched_dat.stat().st_size
    require(patched_size >= pristine_size, "The patched DAT is shorter than the pristine DAT")

    replacements, row_offsets = [], []
    position = align4(pristine_size)
    with patched_dat.open("rb") as stream:
        for index, (before, after) in enumerate(zip(pristine_rows, patched_rows)):
            if before == after:
                continue
            row_offset = patched_offset + index * ROW
            name_offset, compressed, unknown0, raw_size, unknown1, file_offset = _row_fields(after)
            old_name, old_compressed, old_unknown0, old_raw, old_unknown1, old_offset = _row_fields(before)
            require((name_offset, unknown0, unknown1) == (old_name, old_unknown0, old_unknown1),
                    f"DAT row {index} changed more than its sizes and payload offset")
            require(file_offset >= position,
                    f"DAT row {index} payload is not in the appended region")
            require(file_offset == position,
                    f"DAT row {index} payload is not contiguous with the appended region")
            require(file_offset + compressed <= patched_size,
                    f"DAT row {index} payload exceeds the patched DAT")
            require(compressed > 0 and raw_size > 0, f"DAT row {index} has an empty replacement")
            stream.seek(file_offset)
            chunk = stream.read(compressed)
            require(len(chunk) == compressed, f"DAT row {index} payload is truncated")
            name = read_name(pristine_dat, pristine_offset, name_offset)
            require(name == read_name(patched_dat, patched_offset, name_offset),
                    f"DAT row {index} changed its filename")
            path = output_dir / "archive" / f"{index:04d}.bin"
            path.write_bytes(chunk)
            replacements.append({
                "name": name, "index": index, "row_offset": row_offset,
                "name_offset": name_offset, "unknown0": unknown0, "unknown1": unknown1,
                "original_compressed_size": old_compressed, "original_raw_size": old_raw,
                "original_file_offset": old_offset,
                "file_offset": file_offset, "raw_size": raw_size, "compressed_size": compressed,
                "compressed_sha256": sha256_bytes(chunk),
                "chunk": f"archive/{index:04d}.bin",
                "chunk_sha256": sha256_file(path),
            })
            row_offsets.append(row_offset)
            position = align4(file_offset + compressed)
    require(replacements, "The patched DAT differs from the pristine DAT in no table row")
    require(patched_size == replacements[-1]["file_offset"] + replacements[-1]["compressed_size"],
            "The patched DAT carries data outside the described appended region")
    _verify_dat_shape(pristine_dat, patched_dat, pristine_size, row_offsets)

    section = {
        "source_dat_size": pristine_size, "source_dat_sha256": sha256_file(pristine_dat),
        "output_dat_size": patched_size, "output_dat_sha256": sha256_file(patched_dat),
        "entries_offset": pristine_offset, "entry_count": pristine_count,
        "replacements": replacements,
    }
    if source_sdat is not None and output_sdat is not None:
        source_header = read_sdat_header(source_sdat)
        output_header = read_sdat_header(output_sdat)
        require(source_header["dat_size"] == pristine_size,
                "The pristine SDAT header does not describe the pristine DAT")
        require(output_header["dat_size"] == patched_size,
                "The paired SDAT header does not describe the patched DAT")
        for field in ("version", "license", "type", "content_id", "block_size"):
            require(source_header[field] == output_header[field],
                    f"The paired SDAT changed its {field}")
        section["header"] = {field: output_header[field] for field in
                             ("version", "license", "type", "content_id", "block_size", "flags")}
    # ``*_sdat_sha256`` below are this build's own archives, not reproducible
    # targets: see the module docstring. ``source_sdat_sha256`` still identifies
    # the retail archive the user must supply.
    for key, path in (("source", source_sdat), ("output", output_sdat)):
        if path is None:
            continue
        path = Path(path)
        section[f"{key}_sdat_size"] = path.stat().st_size
        section[f"{key}_sdat_sha256"] = sha256_file(path)
    return section


def _verify_dat_shape(pristine_dat, patched_dat, pristine_size, row_offsets):
    """Every byte outside the rewritten rows must survive, and only data is appended."""
    allowed = set()
    for row_offset in row_offsets:
        allowed.update(range(row_offset, row_offset + ROW))
    with Path(pristine_dat).open("rb") as before, Path(patched_dat).open("rb") as after:
        position = 0
        while True:
            chunk = before.read(BLOCK)
            if not chunk:
                break
            other = after.read(len(chunk))
            if other != chunk:
                for index, (original, replacement) in enumerate(zip(chunk, other)):
                    if original != replacement and position + index not in allowed:
                        raise ValueError(
                            "The patched DAT changed bytes outside its rewritten table rows "
                            f"(offset {position + index:#x})")
            position += len(chunk)
        require(after.tell() == pristine_size, "The patched DAT prefix length changed")


def apply_archive_patch(source, target, patch_dir, spec, progress=None):
    """Copy ``source``, append the replacement chunks, rewrite the rows, verify."""
    source, target, patch_dir = Path(source), Path(target), Path(patch_dir)
    require(source.stat().st_size == spec["source_dat_size"],
            "The installed archive is not the size of the pristine BLJM60381 DAT")
    require(not Path(target).exists(), f"Refusing to overwrite an existing file: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = spec["source_dat_size"]
    done = 0
    with source.open("rb") as reader, target.open("xb") as writer:
        while chunk := reader.read(BLOCK):
            writer.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, total)
        require(digest.hexdigest() == spec["source_dat_sha256"],
                "The installed archive does not match the pristine BLJM60381 DAT")
        position = source.stat().st_size
        for replacement in spec["replacements"]:
            padding = (-position) % 4
            if padding:
                writer.write(b"\0" * padding)
                position += padding
            require(position == replacement["file_offset"],
                    f"Patch data offset for {replacement['name']} is not reproducible")
            chunk = (patch_dir / replacement["chunk"]).read_bytes()
            require(len(chunk) == replacement["compressed_size"],
                    f"Shipped chunk for {replacement['name']} has the wrong length")
            require(sha256_bytes(chunk) == replacement["compressed_sha256"],
                    f"Shipped chunk for {replacement['name']} was modified")
            writer.write(chunk)
            position += len(chunk)
            reader.seek(replacement["row_offset"])
            original = reader.read(ROW)
            require(len(original) == ROW,
                    f"Pristine table row for {replacement['name']} is missing")
            require(_row_fields(original) == (
                replacement["name_offset"], replacement["original_compressed_size"],
                replacement["unknown0"], replacement["original_raw_size"],
                replacement["unknown1"], replacement["original_file_offset"]),
                f"Pristine table row for {replacement['name']} differs from the patch data")
            row = _row_bytes(replacement["name_offset"], replacement["compressed_size"],
                             replacement["unknown0"], replacement["raw_size"],
                             replacement["unknown1"], replacement["file_offset"])
            writer.seek(replacement["row_offset"])
            writer.write(row)
            writer.seek(position)
        writer.truncate()
    require(target.stat().st_size == spec["output_dat_size"],
            "Rebuilt archive length differs from the pinned image")
    require(sha256_file(target, progress) == spec["output_dat_sha256"],
            "Rebuilt archive does not match the pinned patched DAT")
    return {"output": str(target), "output_size": spec["output_dat_size"],
            "output_sha256": spec["output_dat_sha256"],
            "replacements": len(spec["replacements"])}


# ---------------------------------------------------------------------------
# Whole patch folder
# ---------------------------------------------------------------------------

def load_manifest(patch_dir):
    patch_dir = Path(patch_dir)
    path = patch_dir / MANIFEST_NAME
    require(path.is_file(), f"Not a patch folder (no {MANIFEST_NAME}): {patch_dir}")
    manifest = _load_json(path)
    require(manifest.get("schema") == SCHEMA_VERSION,
            f"Unsupported patch data schema: {manifest.get('schema')!r}")
    require(isinstance(manifest.get("elf"), dict) and isinstance(manifest.get("archive"), dict),
            "Patch manifest is incomplete")
    return manifest


def summary(manifest):
    elf, archive = manifest["elf"], manifest["archive"]
    return {"patch": manifest.get("patch", {}),
            "elf_source_size": elf["source_size"], "elf_output_size": elf["output_size"],
            "elf_edits": len(elf["edits"]),
            "elf_payload_bytes": elf["edits_bytes"] + elf["tail_bytes"],
            "archive_replacements": len(archive["replacements"]),
            "archive_output_size": archive["output_dat_size"]}


def build(pristine_elf, patched_elf, pristine_dat, patched_dat, output_dir, *,
          pristine_sdat=None, patched_sdat=None, patch=None, log=print):
    """Write a complete patch folder and prove it rebuilds the staged artifacts."""
    output_dir = Path(output_dir)
    require(not output_dir.exists(), f"Refusing to overwrite an existing patch folder: {output_dir}")
    output_dir.mkdir(parents=True)
    elf_section = build_elf_patch(pristine_elf, patched_elf, output_dir)
    log(f"executable: {len(elf_section['edits'])} edit runs, "
        f"{elf_section['edits_bytes']} B of edits and a {elf_section['tail_bytes']} B appended segment")
    archive_section = build_archive_patch(pristine_dat, patched_dat, output_dir,
                                          source_sdat=pristine_sdat, output_sdat=patched_sdat)
    log(f"archive: {len(archive_section['replacements'])} rows "
        f"({sum(r['compressed_size'] for r in archive_section['replacements'])} B of chunks)")

    manifest = {"schema": SCHEMA_VERSION,
                "patch": patch or {"name": "th2dxp-en", "version": "0.1",
                                   "game": "ToHeart2 DX PLUS (BLJM60381)"},
                "elf": elf_section, "archive": archive_section}
    _save_json(output_dir / MANIFEST_NAME, manifest)

    # Prove the shipped data rebuilds both staged artifacts exactly.
    verify(output_dir, pristine_elf, pristine_dat, log=log)
    sizes = [path.stat().st_size for path in output_dir.rglob("*") if path.is_file()]
    log(f"patch data: {sum(sizes)} B in {len(sizes)} files")
    return manifest


def verify(patch_dir, pristine_elf, pristine_dat, *, log=print):
    """Rebuild both artifacts from the patch folder and compare their hashes."""
    patch_dir = Path(patch_dir)
    manifest = load_manifest(patch_dir)
    with tempfile.TemporaryDirectory(prefix="th2dxp-patch-") as temporary:
        temporary = Path(temporary)
        elf_target = temporary / "EBOOT.elf"
        elf = apply_elf_patch(pristine_elf, elf_target, patch_dir, manifest["elf"])
        log(f"verified executable: {elf['output_sha256']}")
        dat_target = temporary / "data.dat"
        dat = apply_archive_patch(pristine_dat, dat_target, patch_dir, manifest["archive"])
        log(f"verified archive: {dat['output_sha256']}")
    return elf, dat


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build or verify the shipped patch data.")
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pristine-elf", type=Path, default=DEFAULT_PRISTINE_ELF)
    parser.add_argument("--patched-elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--pristine-dat", type=Path, default=DEFAULT_PRISTINE_DAT)
    parser.add_argument("--patched-dat", type=Path, default=DEFAULT_DAT)
    parser.add_argument("--pristine-sdat", type=Path, default=DEFAULT_PRISTINE_SDAT)
    parser.add_argument("--patched-sdat", type=Path, default=DEFAULT_SDAT)
    args = parser.parse_args(argv)
    try:
        if args.action == "build":
            build(args.pristine_elf, args.patched_elf, args.pristine_dat, args.patched_dat,
                  args.output, pristine_sdat=args.pristine_sdat, patched_sdat=args.patched_sdat)
        else:
            verify(args.output, args.pristine_elf, args.pristine_dat)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
