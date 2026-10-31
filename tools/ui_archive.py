"""Append-only UI archive staging; never deploys or grants runtime acceptance.

stage({archive_name: complete_replacement_bytes}, new_output_directory) writes
verified data.dat, data.sdat, encryption/decryption logs and report.json. The
output must be a new directory under this checkout's build/ or work/ui-staging/.
The lower-level stage_dat API accepts isolated archives for asset-free tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import mmap
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

import assets
import build_sdat_tool
import scenario_source

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/assets/data.dat"
MANIFEST = ROOT / "work/assets/decryption.json"
DAT_TOOL = ROOT / "vendor/TH2DXP_KIT/dat_tool.py"
SCENARIO_TOOL = ROOT / "vendor/TH2DXP_KIT/scenario_eboot_tool.py"
# Native 0x28D28 reads the 13-byte ALONE header; 0x28FBC..0x28FC4
# advances compressed output by 32768. The pinned scenario compressor uses
# dictionary=13, fastBytes=273, eos=0 and writes the explicit little-endian size.
NATIVE_PROPS = b"\x5d\x00\x20\x00\x00"
LIMIT = 0xFFFFFFFF
BLOCK = 4 * 1024 * 1024
# Separately identified fresh-dump source, never a replacement for MANIFEST.
SOURCE_VARIANTS = {
    "389bf3cabdb9cdf3044b5be1dd4789c43be351f24bfa70a22e0d2e2fca5aa0f1": {
        "name": "fresh-bljm60381",
        "source_size": 2185195888,
        "dat_size": 2180935968,
        "dat_sha256": "324d93e49a620c3b2d0dab8451aba0106ce2b36762d4ecd42287d5ca8dc230c7",
        "changed_entries": tuple(f"n/{code:04x}.bin" for code in range(0x8000, 0x8210, 0x10)),
    },
}
LEGACY_SOURCE_WARNINGS = ("WARNING: Header hash is invalid!",
                          "WARNING: Metadata section hash is invalid!")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _installed_root():
    """The operator's configured installation, or None when project.json has none."""
    config_path = ROOT / "project.json"
    if not config_path.is_file():
        return None
    config = json.loads(config_path.read_text(encoding="utf-8"))
    value = str(config.get("game_usrdir") or "").strip()
    return Path(value).resolve() if value else None


def _reject_installed(path: Path) -> None:
    installed = _installed_root()
    if installed is not None and _inside(path, installed):
        raise ValueError("Staging must not target installed game paths")


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _name(name: str) -> None:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError(f"Invalid archive filename: {name!r}")
    for part in name.split("/"):
        if (not part or part in (".", "..") or part.endswith((" ", "."))
                or any(ord(c) < 32 or ord(c) == 127 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)):
            raise ValueError(f"Invalid archive filename: {name!r}")


def _validate_replacements(replacements: dict[str, bytes]) -> None:
    if not isinstance(replacements, dict) or not replacements:
        raise ValueError("At least one replacement is required")
    for name, raw in replacements.items():
        _name(name)
        if not isinstance(raw, bytes):
            raise ValueError(f"Replacement {name} must be complete bytes")
        if len(raw) > LIMIT:
            raise ValueError(f"Replacement {name} exceeds 32-bit size bounds")


def _dat_module():
    return assets.module("th2_ui_archive_dat", DAT_TOOL)


def _native_kit():
    return assets.module("th2_ui_archive_scenario", SCENARIO_TOOL)


def validate_native_chunks(payload: bytes, expected_size: int) -> list[dict]:
    """Validate packed replacements against the pinned native consumer contract.

    This is deliberately stricter than the vendor/Python ALONE header reader:
    unknown usize, a different dictionary, short continuation output and ignored
    padding/trailing records are not native-compatible substitutes.
    Empty table-level raw entries have no chunk records at all.
    """
    if expected_size < 0 or expected_size > LIMIT:
        raise ValueError("Native chunk total raw size exceeds 32-bit bounds")
    if not payload:
        if expected_size:
            raise ValueError("Native chunk total raw size mismatch")
        return []
    if not expected_size:
        raise ValueError("Native chunks cannot encode an empty table-level entry")
    position, total = 0, 0
    chunks = []
    while position < len(payload):
        if position + 4 > len(payload):
            raise ValueError("Native chunk prefix exceeds payload bounds")
        prefix = struct.unpack_from(">I", payload, position)[0]
        flag, size = prefix >> 24, prefix & 0xFFFFFF
        if flag not in (0, 0x80):
            raise ValueError("Native replacement chunk has unsupported flag")
        end = position + 4 + size
        padded_end = (end + 3) & ~3
        if size < 13 or padded_end > len(payload):
            raise ValueError("Native chunk header/payload/padding exceeds bounds")
        start = position + 4
        if payload[start:start + 5] != NATIVE_PROPS:
            raise ValueError("Native chunk properties/dictionary must be 5d/8192")
        usize = struct.unpack_from("<Q", payload, start + 5)[0]
        if usize == 0xFFFFFFFFFFFFFFFF:
            raise ValueError("Native chunk requires explicit usize, not unknown size")
        if not 0 < usize <= scenario_source.CHUNK_SIZE:
            raise ValueError("Native chunk usize exceeds 32768-byte output bounds")
        if flag == 0x80 and usize != scenario_source.CHUNK_SIZE:
            raise ValueError("Native continuation chunk must output exactly 32768 bytes")
        total += usize
        if total > expected_size:
            raise ValueError("Native chunk total raw size exceeds table size")
        if (flag == 0x80) != (total < expected_size):
            raise ValueError("Native chunk continuation/final flag mismatches total raw size")
        if any(payload[end:padded_end]):
            raise ValueError("Native chunk padding must be zero")
        # The native decoder stops at its declared output size. An EOS-free
        # range coder's final flush can produce another symbol if an unbounded
        # RAW reader is asked for usize+1; that is not an extra native byte.
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
            "id": lzma.FILTER_LZMA1, "dict_size": 8192, "lc": 3, "lp": 0, "pb": 2,
        }])
        try:
            decoded = decoder.decompress(payload[start + 13:end], max_length=usize)
        except lzma.LZMAError as error:
            raise ValueError("Native chunk compressed payload is invalid") from error
        if len(decoded) != usize:
            raise ValueError("Native chunk decoded size differs from explicit usize")
        chunks.append({"offset": position, "flag": flag, "compressed_size": size,
                       "uncompressed_size": usize})
        position = padded_end
        if flag == 0:
            break
    if total != expected_size or position != len(payload):
        raise ValueError("Native chunk total raw size/trailing records mismatch")
    return chunks


def _table(source: Path, dat, expected_count: int | None = None):
    size = source.stat().st_size
    if size < 16 or size > LIMIT:
        raise ValueError("DAT length exceeds 32-bit address bounds or lacks a header")
    with source.open("rb") as stream:
        header = stream.read(16)
        count, _, _, offset = struct.unpack(">4I", header)
        end = offset + count * 24
        if not count or count > 200000 or offset < 16 or end > size:
            raise ValueError("DAT table bounds are invalid")
        if expected_count is not None and count != expected_count:
            raise ValueError(f"Expected {expected_count} DAT entries, found {count}")
        # Validate names before invoking the vendor's unbounded C-string reader.
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as blob:
            seen = set()
            for index in range(count):
                row = struct.unpack_from(">6I", blob, offset + index * 24)
                name_offset, compressed, _, raw_size, _, payload_offset = row
                if name_offset < 16 or name_offset >= offset:
                    raise ValueError(f"Entry {index}: filename offset is outside the name region")
                terminator = blob.find(b"\0", name_offset, offset)
                if terminator < 0:
                    raise ValueError(f"Entry {index}: unterminated filename")
                name = blob[name_offset:terminator].decode("latin1")
                _name(name)
                if name in seen:
                    raise ValueError(f"Duplicate archive filename: {name}")
                seen.add(name)
                length = compressed or raw_size
                if payload_offset < end or payload_offset + length > size:
                    raise ValueError(f"Entry {name}: payload bounds overlap metadata or exceed DAT")
    meta, entries = dat.parse_archive_table(source)
    return meta, entries


def _verify_prefix(source: Path, staged: Path, patches: dict[int, bytes], expected_sha: str) -> None:
    """Compare every original byte, except precisely the authorized table rows."""
    digest = hashlib.sha256()
    with source.open("rb") as original, staged.open("rb") as result:
        position = 0
        while True:
            chunk = original.read(BLOCK)
            if not chunk:
                break
            digest.update(chunk)
            expected = bytearray(chunk)
            for offset, row in patches.items():
                left = max(position, offset)
                right = min(position + len(chunk), offset + len(row))
                if left < right:
                    expected[left - position:right - position] = row[left - offset:right - offset]
            if result.read(len(chunk)) != expected:
                raise ValueError("DAT preservation failed: original bytes changed outside authorized table rows")
            position += len(chunk)
    if digest.hexdigest() != expected_sha:
        raise ValueError("Source DAT changed during staging")


def stage_dat(source: Path, replacements: dict[str, bytes], output_path: Path, *,
              expected_sha256: str | None = None, expected_entry_count: int | None = None) -> dict:
    """Copy a DAT and append replacements, preserving all other original bytes.

    This asset-independent primitive requires an absent output file and an
    existing parent directory. It does not encrypt, install, or approve a build.
    """
    source, output_path = Path(source).resolve(), Path(output_path).resolve()
    if source == output_path or output_path.exists():
        raise ValueError("Staged DAT must not overwrite any existing file")
    _validate_replacements(replacements)
    dat = _dat_module()
    _reject_installed(output_path)
    meta, entries = _table(source, dat, expected_entry_count)
    names = {entry.name for entry in entries}
    missing = replacements.keys() - names
    if missing:
        raise ValueError(f"Unknown replacement archive filenames: {sorted(missing)}")
    source_sha = assets.sha(source)
    if expected_sha256 is not None and source_sha != expected_sha256:
        raise ValueError("Source DAT SHA-256 differs from the immutable decryption manifest")
    if shutil.disk_usage(output_path.parent).free < source.stat().st_size + sum(map(len, replacements.values())) + BLOCK:
        raise ValueError("Insufficient free space for staged DAT")
    kit = _native_kit()
    patches, changes = {}, []
    # Exclusive creation prevents an accidentally repeated stage from overwriting.
    with source.open("rb") as original, output_path.open("x+b") as result:
        shutil.copyfileobj(original, result, BLOCK)
        for entry in entries:
            if entry.name not in replacements:
                continue
            raw = replacements[entry.name]
            compressed = scenario_source.pack(raw, kit)
            chunks = validate_native_chunks(compressed, len(raw))
            result.seek(0, 2)
            start = result.tell()
            padding = (-start) % 4
            offset = start + padding
            if len(compressed) > LIMIT or offset > LIMIT or offset + len(compressed) > LIMIT:
                raise ValueError(f"Replacement {entry.name} exceeds DAT 32-bit address bounds")
            result.write(b"\0" * padding)
            result.write(compressed)
            row = struct.pack(">6I", entry.name_offset, len(compressed), entry.unknown0,
                              len(raw), entry.unknown1, offset)
            row_offset = meta["entries_offset"] + entry.index * 24
            patches[row_offset] = row
            result.seek(row_offset)
            result.write(row)
            changes.append({"name": entry.name, "index": entry.index, "raw_size": len(raw),
                            "raw_sha256": _digest(raw), "compressed_size": len(compressed),
                            "compressed_sha256": _digest(compressed), "file_offset": offset,
                            "native_chunks": chunks,
                            "original_file_offset": entry.file_offset,
                            "original_compressed_size": entry.compressed_size,
                            "original_raw_size": entry.uncompressed_size})
    _verify_prefix(source, output_path, patches, source_sha)
    _, staged_entries = _table(output_path, dat, len(entries))
    with output_path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as blob:
        for entry in staged_entries:
            if entry.name in replacements:
                payload = blob[entry.file_offset:entry.file_offset + entry.compressed_size]
                validate_native_chunks(payload, entry.uncompressed_size)
                actual, _ = dat.decompress_archive_entry(blob, entry)
                if actual != replacements[entry.name]:
                    raise ValueError(f"Replacement verification failed: {entry.name}")
    return {"source": str(source), "source_size": source.stat().st_size,
            "source_sha256": source_sha, "output": str(output_path),
            "output_size": output_path.stat().st_size, "output_sha256": assets.sha(output_path),
            "entry_count": len(entries), "replacements": changes,
            "verification": {"replacements_reextracted_exactly": True,
                             "native_chunk_contract_validated": True,
                             "unchanged_table_rows_preserved": len(entries) - len(changes),
                             "all_original_payload_bytes_preserved": True,
                             "header_names_order_unknown_fields_preserved": True,
                             "original_bytes_except_changed_rows_identical": True},
            "runtime_accepted": False}


def _sdat_header(path: Path) -> dict:
    with path.open("rb") as stream:
        header = stream.read(144)
    if len(header) != 144 or header[:4] != b"NPD\0":
        raise ValueError("Expected a complete original NPD/SDAT header")
    version, license_type, data_type = struct.unpack_from(">3I", header, 4)
    flags, block, size = struct.unpack_from(">IIQ", header, 128)
    if version not in (1, 2, 3, 4) or license_type != 0 or not flags & 0x01000000:
        raise ValueError("Original container is not a supported license-0 SDAT")
    if block != 0x4000:
        raise ValueError("Original SDAT block size is not supported by pinned pack_data")
    content = header[16:64]
    text, _, padding = content.partition(b"\0")
    if len(text) >= 48 or any(padding) or any(c < 32 or c > 126 for c in text):
        raise ValueError("Original SDAT content ID cannot be represented safely by the pinned CLI")
    return {"version": version, "license": license_type, "type": data_type,
            "content_id": text.decode("ascii"), "flags": flags, "block_size": block,
            "dat_size": size, "header_sha256": _digest(header)}


def _compare_variant_dat(source: Path, variant: Path, expected_changed: tuple[str, ...]) -> dict:
    """Verify the exact source-entry partition; UI/font inputs must be identical."""
    dat = _dat_module()
    old_meta, old_entries = _table(source, dat)
    new_meta, new_entries = _table(variant, dat, len(old_entries))
    if old_meta["pre_entries_hex"] != new_meta["pre_entries_hex"]:
        raise ValueError("Source variant changed the DAT header or filename region")
    changed, identical = [], 0
    with source.open("rb") as old_stream, variant.open("rb") as new_stream:
        with mmap.mmap(old_stream.fileno(), 0, access=mmap.ACCESS_READ) as old_blob:
            with mmap.mmap(new_stream.fileno(), 0, access=mmap.ACCESS_READ) as new_blob:
                for old, new in zip(old_entries, new_entries):
                    if any(getattr(old, key) != getattr(new, key) for key in
                           ("index", "name", "name_offset", "unknown0", "unknown1")):
                        raise ValueError("Source variant changed entry order, names or unknown fields")
                    old_size = old.compressed_size or old.uncompressed_size
                    new_size = new.compressed_size or new.uncompressed_size
                    same = vars(old) == vars(new)
                    for at in range(0, max(old_size, new_size), BLOCK):
                        if (old_blob[old.file_offset + at:old.file_offset + min(at + BLOCK, old_size)] !=
                                new_blob[new.file_offset + at:new.file_offset + min(at + BLOCK, new_size)]):
                            same = False
                            break
                    if same:
                        identical += 1
                    else:
                        if new.name not in expected_changed:
                            raise ValueError(f"Source variant changed an unapproved entry: {new.name}")
                        changed.append(new.name)
    if set(changed) != set(expected_changed):
        raise ValueError("Source variant changed-entry partition differs from the reviewed inventory")
    return {"identical_entries": identical, "changed_entries": changed,
            "entry_count": len(new_entries), "ui_font_source_entries_identical": True}


def _invoke(command: list[str], log: Path, successes: tuple[str, ...], *,
            allowed_warnings: tuple[str, ...] = ()) -> None:
    with log.open("xb") as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    messages = log.read_text(encoding="utf-8", errors="replace")
    checked = "\n".join(line for line in messages.splitlines() if line not in allowed_warnings)
    if (result.returncode or any(message not in messages for message in successes)
            or re.search(r"failed|error:|invalid|warning:", checked, re.IGNORECASE)):
        raise ValueError(f"make_npdata did not complete successfully; inspect {log}")


def stage(replacements: dict[str, bytes], output_dir: Path, *,
          source_sdat: Path | None = None) -> dict:
    """Stage DAT + encrypted SDAT and prove a complete decrypt/SHA roundtrip.

    The original pinned decryptor and separately built/repaired packer are
    mandatory; this API never builds or downloads dependencies. A failed stage
    remains in its new directory for diagnosis and cannot be silently reused.
    """
    output_dir = Path(output_dir).resolve()
    allowed = (ROOT / "build", ROOT / "work/ui-staging")
    if not any(_inside(output_dir, root.resolve()) and output_dir != root.resolve() for root in allowed):
        raise ValueError("Staging directory must be a new child of build/ or work/ui-staging/")
    if _inside(output_dir, (ROOT / "build/typography-probe").resolve()):
        raise ValueError("Native typography base build is immutable")
    installed = _installed_root()
    if installed is not None and (_inside(output_dir, installed) or _inside(installed, output_dir)):
        raise ValueError("Staging must not target installed game paths")
    if output_dir.exists():
        raise ValueError("Staging directory already exists; refusing overwrite")
    _validate_replacements(replacements)
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    if source_sdat is None:
        if installed is None:
            raise ValueError(
                "No game_usrdir in project.json; add your own <game>/PS3_GAME/USRDIR path "
                "or pass --source-sdat")
        original_sdat = installed / "data.sdat"
    else:
        original_sdat = Path(source_sdat).resolve()
    full_archive_hash_rechecked = source_sdat is not None
    source_sha = assets.sha(original_sdat) if full_archive_hash_rechecked else manifest["source_sha256"]
    variant = None
    if source_sha != manifest["source_sha256"]:
        variant = SOURCE_VARIANTS.get(source_sha)
        if variant is None:
            raise ValueError("Explicit source SDAT SHA-256 differs from immutable decryption provenance and known variants")
        if original_sdat.stat().st_size != variant["source_size"]:
            raise ValueError("Source variant SDAT size differs from its pinned identity")
    if _inside(original_sdat, output_dir):
        raise ValueError("Source SDAT must be outside the new staging directory")
    if manifest["output_size"] != SOURCE.stat().st_size or manifest["entry_count"] != 3516:
        raise ValueError("Source DAT size/count differs from immutable decryption provenance")
    if variant is not None and assets.sha(SOURCE) != manifest["output_sha256"]:
        raise ValueError("Reference DAT SHA-256 differs from immutable decryption provenance")
    binary = assets.BINARY.resolve()
    if not binary.is_file():
        raise ValueError("Existing work/make_npdata.exe is required; no automatic build is permitted")
    if assets.sha(binary) != manifest["binary_sha256"] or manifest["make_npdata_revision"] != assets.REVISION:
        raise ValueError("make_npdata executable/provenance differs from pinned decryption tool")
    revision = subprocess.check_output(
        ["git", "-C", str(assets.UPSTREAM.parent), "rev-parse", "HEAD"], text=True).strip()
    if revision != assets.REVISION:
        raise ValueError("Unexpected pinned make_npdata source revision")
    packer, packer_provenance = build_sdat_tool.validated_tool()
    # An explicit immutable backup is read-only input, never copied over the
    # installed file or written back into project/manifest configuration.
    original_header = _sdat_header(original_sdat)
    source_size = manifest["output_size"] if variant is None else variant["dat_size"]
    if original_header["dat_size"] != source_size:
        raise ValueError("Original SDAT header length differs from recovered DAT")
    # DAT copy, encrypted output, and full temporary decrypted proof coexist.
    required = (3 + int(variant is not None)) * (source_size + sum(map(len, replacements.values()))) + 64 * 1024 * 1024
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output_dir.parent).free < required:
        raise ValueError("Insufficient free space for DAT, SDAT and complete roundtrip proof")
    output_dir.mkdir(exist_ok=False)
    source_dat, dat_sha, variant_proof = SOURCE, manifest["output_sha256"], None
    if variant is not None:
        source_dat = output_dir / "source-variant.dat"
        source_log = output_dir / "source-decryption.log"
        source_args = [str(binary), "-v", "-d", str(original_sdat), str(source_dat), "0"]
        # These two legacy warnings are retained, not authentication passes.
        # Only the exact pinned encrypted/decrypted pair can take this path;
        # output authentication and roundtrip still permit no warnings.
        _invoke(source_args, source_log, ("File successfully parsed!", "File successfully decrypted!"),
                allowed_warnings=LEGACY_SOURCE_WARNINGS)
        dat_sha = variant["dat_sha256"]
        if source_dat.stat().st_size != source_size or assets.sha(source_dat) != dat_sha:
            raise ValueError("Source variant decrypted DAT differs from its pinned size/SHA-256")
        if set(replacements) & set(variant["changed_entries"]):
            raise ValueError("UI staging must preserve source-variant-specific entries")
        variant_proof = {"name": variant["name"], "source_sdat_sha256": source_sha,
                         "source_dat_sha256": dat_sha, "source_dat": str(source_dat),
                         "comparison": _compare_variant_dat(SOURCE, source_dat, variant["changed_entries"]),
                         "decryption_log": str(source_log), "command": source_args,
                         "legacy_warnings": [line for line in source_log.read_text(encoding="utf-8").splitlines()
                                             if line in LEGACY_SOURCE_WARNINGS],
                         "source_cryptographically_authenticated": False}
    staged_dat, staged_sdat = output_dir / "data.dat", output_dir / "data.sdat"
    dat_report = stage_dat(source_dat, replacements, staged_dat,
                           expected_sha256=dat_sha, expected_entry_count=3516)
    encrypt_log, decrypt_log = output_dir / "encryption.log", output_dir / "decryption.log"
    # argv includes the empty content-ID argument and key mode 0. No RAP argument:
    # the pinned parser dereferences it if supplied. -v satisfies decrypt argc>5.
    encrypt_args = [str(packer), "-v", "-e", str(staged_dat), str(staged_sdat),
                    str(original_header["version"]), "0", str(original_header["type"]),
                    "1", original_header["content_id"], "0"]
    _invoke(encrypt_args, encrypt_log, ("File successfully encrypted!", "File successfully forged!"))
    staged_header = _sdat_header(staged_sdat)
    for field in ("version", "license", "type", "content_id", "block_size"):
        if staged_header[field] != original_header[field]:
            raise ValueError(f"Staged SDAT {field} differs from original semantics")
    if staged_header["flags"] != 0x0100000C or staged_header["dat_size"] != staged_dat.stat().st_size:
        raise ValueError("Staged SDAT does not match pinned pack_data flags/length")
    authentication_log = output_dir / "authentication.log"
    authentication_args = [str(packer), "--verify", str(staged_sdat)]
    _invoke(authentication_args, authentication_log,
            ("SDAT header, metadata and every ciphertext block authenticated!",))
    with tempfile.TemporaryDirectory(prefix="roundtrip-", dir=output_dir) as temporary:
        decrypted = Path(temporary) / "data.dat"
        decrypt_args = [str(binary), "-v", "-d", str(staged_sdat), str(decrypted), "0"]
        _invoke(decrypt_args, decrypt_log, ("File successfully parsed!", "File successfully decrypted!"))
        if not decrypted.is_file() or decrypted.stat().st_size != dat_report["output_size"]:
            raise ValueError("SDAT roundtrip decrypted DAT length differs")
        roundtrip_sha = assets.sha(decrypted)
        if roundtrip_sha != dat_report["output_sha256"]:
            raise ValueError("SDAT roundtrip complete DAT SHA-256 differs")
    if MANIFEST.read_bytes() != manifest_bytes or _sdat_header(original_sdat) != original_header:
        raise ValueError("Read-only input provenance changed during staging")
    if full_archive_hash_rechecked and assets.sha(original_sdat) != source_sha:
        raise ValueError("Read-only source SDAT changed during staging")
    if variant is not None and assets.sha(source_dat) != dat_sha:
        raise ValueError("Source variant DAT changed during staging")
    if assets.sha(staged_dat) != dat_report["output_sha256"]:
        raise ValueError("Staged DAT changed during encryption/roundtrip")
    report = {"schema_version": 1, "dat": dat_report,
              "decryption_manifest": {"path": str(MANIFEST), "sha256": _digest(manifest_bytes)},
              "original_sdat": {"path": str(original_sdat), "header": original_header,
                                "manifest_sha256": source_sha,
                                "full_archive_hash_rechecked": full_archive_hash_rechecked},
              "source_variant": variant_proof,
              "sdat": {"path": str(staged_sdat), "size": staged_sdat.stat().st_size,
                       "sha256": assets.sha(staged_sdat), "header": staged_header},
              "toolchain": {"make_npdata_revision": revision, "binary": str(binary),
                            "binary_sha256": manifest["binary_sha256"],
                            "dat_tool_sha256": assets.sha(DAT_TOOL),
                            "scenario_tool_sha256": assets.sha(SCENARIO_TOOL),
                            "make_npdata_source_sha256": assets.sha(assets.UPSTREAM / "make_npdata.c"),
                            "repaired_packer": packer_provenance},
              "roundtrip": {"complete_dat_sha256": roundtrip_sha, "matches_staged_dat": True,
                            "every_ciphertext_block_authenticated": True,
                            "decrypted_size": dat_report["output_size"], "temporary_dat_removed": True},
              "commands": {"encrypt": encrypt_args, "authenticate": authentication_args, "decrypt": decrypt_args},
              "logs": {"encryption": str(encrypt_log), "authentication": str(authentication_log),
                       "decryption": str(decrypt_log)},
              "runtime_accepted": False, "installed_files_modified": False,
              "emulator_launched": False}
    with (output_dir / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--replace", action="append", required=True, metavar="ARCHIVE_NAME=FILE")
    parser.add_argument("--source-sdat", type=Path,
                        help="Read-only SDAT matching the original manifest or an explicitly pinned source variant")
    args = parser.parse_args()
    replacements = {}
    for item in args.replace:
        name, separator, filename = item.partition("=")
        if not separator or not filename or name in replacements:
            parser.error("Each --replace must be a distinct ARCHIVE_NAME=FILE")
        replacements[name] = Path(filename).read_bytes()
    print(json.dumps(stage(replacements, args.output_dir, source_sdat=args.source_sdat), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"ERROR: {error}")
