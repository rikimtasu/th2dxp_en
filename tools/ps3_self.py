"""Decrypt a retail PS3 SELF (``EBOOT.BIN``) into the plain ELF an emulator boots.

The game ships one encrypted executable; the translation patch is a diff against
its decrypted image. Decrypting needs Sony's SELF key set, so exactly one set is
carried here: the retail *application* set at revision 0x13 that BLJM60381's
``EBOOT.BIN`` selects. Any other SELF (different program type, revision or
descriptor layout) raises instead of guessing a key, and every caller still
checks the decrypted SHA-256 against the pinned pristine image.

The container format follows the public SELF description; the two constants in
``KEY_SETS`` are the published retail application key pair also used by
RPCS3's ``Crypto/key_vault.cpp`` (GPL-2.0). No per-console or per-account key is
involved: a retail disc executable decrypts identically on every machine, which
is why one key set is enough.
"""
from __future__ import annotations

import struct

SELF_MAGIC = b"SCE\x00"
ELF_MAGIC = b"\x7fELF"

# (program_type, revision) -> (erk 32 bytes, riv 16 bytes)
KEY_SETS = {
    (4, 0x0013): (
        bytes.fromhex("DBF62D76FC81C8AC92372A9D631DDC9219F152C59C4B20BFF8F96B64AB065E94"),
        bytes.fromhex("CB5DD4BE8CF115FFB25801BC6086E729"),
    ),
}

SCE_HEADER = 0x20          # SCE header: magic/version/flags/type/meta/hsize/esize
EXT_FIELDS = 10            # u64 fields following the SCE header
META_INFO = 0x40           # key/iv pair with their padding words
SECTION_HEADER = 0x30      # one metadata section header
PHDR_TYPE = 2              # metadata section that carries program-header data
DEBUG_FLAG = 0x8000


def _aes():
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    return Cipher, algorithms, modes


def cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    Cipher, algorithms, modes = _aes()
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    return decryptor.update(data) + decryptor.finalize()


def ctr_crypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    """AES-CTR with a 128-bit big-endian counter starting at ``iv``.

    ``cryptography``'s CTR mode increments the whole 128-bit block as a
    big-endian integer, which is exactly the PS3 key-stream ordering.
    """
    Cipher, algorithms, modes = _aes()
    cryptor = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
    return cryptor.update(data) + cryptor.finalize()


def read_header(data: bytes) -> dict:
    """Parse just enough of the SELF to name it, before any key is chosen."""
    if len(data) < SCE_HEADER + EXT_FIELDS * 8:
        raise ValueError("File is too short to be a PS3 SELF")
    magic, version, flags, kind, meta, header_size, encrypted_size = struct.unpack(
        ">IIHHIQQ", data[:SCE_HEADER])
    if data[:4] != SELF_MAGIC:
        raise ValueError("Not a PS3 SELF: the file does not start with SCE\\0")
    ext = struct.unpack(">10Q", data[SCE_HEADER:SCE_HEADER + EXT_FIELDS * 8])
    program_id = ext[1]
    if program_id + 0x20 > len(data):
        raise ValueError("SELF program identification header is out of bounds")
    authority, vendor, program_type, sceversion, _ = struct.unpack(
        ">QIIQQ", data[program_id:program_id + 0x20])
    return {"version": version, "flags": flags, "type": kind, "metadata_offset": meta,
            "header_size": header_size, "encrypted_size": encrypted_size,
            "program_authority_id": authority, "program_vendor_id": vendor,
            "program_type": program_type, "program_sceversion": sceversion,
            "elf_header_offset": ext[2], "program_header_offset": ext[3],
            "section_header_offset": ext[4], "segment_ext_offset": ext[5],
            "supplemental_offset": ext[7], "supplemental_size": ext[8]}


def key_set(header: dict):
    """Return the one key pair this SELF selects, or refuse."""
    if header["flags"] & DEBUG_FLAG:
        raise ValueError("This is a debug SELF with plaintext segments; no key is needed")
    chosen = KEY_SETS.get((header["program_type"], header["flags"]))
    if chosen is None:
        raise ValueError(
            f"Unsupported SELF key set (program type {header['program_type']}, "
            f"revision {header['flags']:#06x}); this tool only decrypts the retail "
            "BLJM60381 executable")
    return chosen


def decrypt_self(data: bytes) -> bytes:
    """Return the plain ELF image carried by one retail SELF."""
    header = read_header(data)
    erk, riv = key_set(header)
    meta_offset = header["metadata_offset"] + SCE_HEADER
    header_size = header["header_size"]
    if header_size > len(data) or meta_offset + META_INFO > header_size:
        raise ValueError("SELF metadata header does not fit inside the declared header size")

    info = cbc_decrypt(erk, riv, data[meta_offset:meta_offset + META_INFO])
    key, key_pad, iv, iv_pad = (info[0:16], info[16:32], info[32:48], info[48:64])
    if any(key_pad) or any(iv_pad):
        raise ValueError("SELF metadata did not decrypt with the retail key set")

    headers = ctr_crypt(key, iv, data[meta_offset + META_INFO:header_size])
    if len(headers) < 0x20:
        raise ValueError("SELF metadata headers are truncated")
    _, _, section_count, key_count, _, _, _ = struct.unpack(">QIIIIII", headers[:0x20])
    if not 0 < section_count <= 64 or key_count > 64:
        raise ValueError(f"Implausible SELF metadata counts ({section_count} sections, "
                         f"{key_count} keys)")
    keys_offset = 0x20 + section_count * SECTION_HEADER
    if keys_offset + key_count * 16 > len(headers):
        raise ValueError("SELF data key table is out of bounds")
    data_keys = headers[keys_offset:keys_offset + key_count * 16]

    sections = []
    for index in range(section_count):
        base = 0x20 + index * SECTION_HEADER
        fields = struct.unpack(">QQIIIIIIII", headers[base:base + SECTION_HEADER])
        sections.append(dict(zip(
            ("offset", "size", "type", "program_index", "hashed", "sha1_index",
             "encrypted", "key_index", "iv_index", "compressed"), fields)))

    elf_header_offset = header["elf_header_offset"]
    program_header_offset = header["program_header_offset"]
    section_header_offset = header["section_header_offset"]
    if elf_header_offset + 0x40 > len(data):
        raise ValueError("SELF does not contain a complete ELF header")
    elf_header = data[elf_header_offset:elf_header_offset + 0x40]
    if elf_header[:4] != ELF_MAGIC:
        raise ValueError("SELF does not carry an ELF image")
    (_, elf_class, elf_data, _, _, _) = struct.unpack(">IBBBBQ", elf_header[:16])
    if (elf_class, elf_data) != (2, 2):
        raise ValueError(f"Unsupported ELF class/byte order ({elf_class}/{elf_data}); "
                         "this tool expects a 64-bit big-endian PS3 image")
    (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff, e_flags, e_ehsize,
     e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx) = struct.unpack(
        ">HHIQQQIHHHHHH", elf_header[16:0x40])
    if e_phentsize != 0x38 or e_shentsize != 0x40:
        raise ValueError("Unexpected ELF header entry sizes")

    program_headers = []
    for index in range(e_phnum):
        base = program_header_offset + index * e_phentsize
        if base + e_phentsize > len(data):
            raise ValueError("SELF program header table is truncated")
        fields = struct.unpack(">IIQQQQQQ", data[base:base + e_phentsize])
        program_headers.append(dict(zip(
            ("type", "flags", "offset", "vaddr", "paddr", "filesz", "memsz", "align"),
            fields)))

    image = bytearray(elf_header)
    for section in sections:
        if section["type"] != PHDR_TYPE:
            continue
        if section["program_index"] >= len(program_headers):
            raise ValueError("SELF section points outside the program header table")
        start = section["offset"]
        end = start + section["size"]
        if end > len(data):
            raise ValueError("SELF segment data is out of bounds")
        payload = data[start:end]
        if section["encrypted"] == 3:
            if section["key_index"] >= key_count or section["iv_index"] >= key_count:
                raise ValueError("SELF segment references a missing data key")
            segment_key = data_keys[section["key_index"] * 16:section["key_index"] * 16 + 16]
            segment_iv = data_keys[section["iv_index"] * 16:section["iv_index"] * 16 + 16]
            payload = ctr_crypt(segment_key, segment_iv, payload)
        program_header = program_headers[section["program_index"]]
        if section["compressed"] == 2:
            import zlib
            payload = zlib.decompress(payload)
            if len(payload) > program_header["filesz"]:
                raise ValueError("Compressed SELF segment expands past its program header")
        target = program_header["offset"]
        needed = target + len(payload)
        if len(image) < needed:
            image.extend(b"\x00" * (needed - len(image)))
        image[target:needed] = payload

    if section_header_offset and e_shnum:
        size = e_shnum * e_shentsize
        if section_header_offset + size > len(data):
            raise ValueError("SELF section header table is truncated")
        needed = e_shoff + size
        if len(image) < needed:
            image.extend(b"\x00" * (needed - len(image)))
        image[e_shoff:needed] = data[section_header_offset:section_header_offset + size]

    if e_phnum:
        size = e_phnum * e_phentsize
        if program_header_offset + size > len(data):
            raise ValueError("SELF program header table is truncated")
        needed = e_phoff + size
        if len(image) < needed:
            image.extend(b"\x00" * (needed - len(image)))
        image[e_phoff:needed] = data[program_header_offset:program_header_offset + size]

    return bytes(image)


def decrypt_file(source, target, *, expected_sha256=None) -> dict:
    """Decrypt one SELF file to ``target``; refuse a mismatched pinned image."""
    import hashlib
    from pathlib import Path

    source, target = Path(source), Path(target)
    data = source.read_bytes()
    header = read_header(data)
    image = decrypt_self(data)
    digest = hashlib.sha256(image).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(
            f"Decrypted EBOOT.BIN does not match the pinned BLJM60381 executable "
            f"(got {digest}, expected {expected_sha256})")
    target.write_bytes(image)
    return {"source": str(source), "source_size": len(data), "output": str(target),
            "output_size": len(image), "output_sha256": digest,
            "program_type": header["program_type"], "revision": header["flags"],
            "sceversion": f"{header['program_sceversion']:016x}"}
