"""Synthetic SELF wrapping/unwrapping; no game data or keys beyond the retail pair."""
import hashlib
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ps3_self


def build_elf(segments):
    """A minimal 64-bit big-endian PS3-shaped ELF carrying ``segments``."""
    phoff = 0x40
    phentsize, shentsize = 0x38, 0x40
    shoff = 0x100
    data_end = max(shoff + 2 * shentsize, 0x200) + len(segments) * 0x100
    image = bytearray(data_end)
    ident = b"\x7fELF" + bytes([2, 2, 1, 102]) + b"\x00" * 8
    header = ident + struct.pack(">HHIQQQIHHHHHH", 2, 0x15, 1, 0x10000, phoff, shoff,
                                 0, 0x40, phentsize, len(segments), shentsize, 2, 1)
    image[:len(header)] = header
    for index, payload in enumerate(segments):
        offset = max(shoff + 2 * shentsize, 0x200) + index * 0x100
        phdr = struct.pack(">IIQQQQQQ", 1, 5, offset, 0x10000 + index * 0x100,
                           0x10000 + index * 0x100, len(payload), len(payload), 0x100)
        image[phoff + index * phentsize:phoff + (index + 1) * phentsize] = phdr
        image[offset:offset + len(payload)] = payload
    return bytes(image).rstrip(b"\x00") or bytes(image[:0x40])


def cbc_encrypt(key, iv, data):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(data) + encryptor.finalize()


def wrap_self(elf, *, program_type=4, revision=0x13, keys=None, corrupt_pad=False):
    """Encrypt ``elf`` into a SELF shaped exactly like a retail disc executable."""
    erk, riv = keys or ps3_self.KEY_SETS[(4, 0x0013)]
    _, _, _, _, e_phoff, e_shoff, _, _, e_phentsize, e_phnum, e_shentsize, e_shnum, _ = (
        struct.unpack(">HHIQQQIHHHHHH", elf[16:0x40]))
    phdrs = []
    for index in range(e_phnum):
        base = e_phoff + index * e_phentsize
        phdrs.append(struct.unpack(">IIQQQQQQ", elf[base:base + e_phentsize]))
    shdrs = elf[e_shoff:e_shoff + e_shnum * e_shentsize]

    meta_offset = 0x410
    prog_id_offset, ehdr_offset = 0x70, 0x90
    phdr_offset = 0xD0
    shdr_offset = 0x64A8F0 if False else None
    seg_ext_offset = phdr_offset + e_phnum * e_phentsize
    metadata_info_offset = meta_offset + 0x20
    metadata_headers_offset = metadata_info_offset + 0x40

    meta_key = bytes(range(16))
    meta_iv = bytes(range(16, 32))
    pad = b"\x01" * 16 if corrupt_pad else b"\x00" * 16
    info = meta_key + pad + meta_iv + pad

    payloads = [elf[phdr[2]:phdr[2] + phdr[5]] for phdr in phdrs]
    data_keys = b""
    encrypted = []
    for index, payload in enumerate(payloads):
        key = hashlib.sha256(b"key" + bytes([index])).digest()[:16]
        iv = hashlib.sha256(b"iv" + bytes([index])).digest()[:16]
        data_keys += key + iv
        encrypted.append(ps3_self.ctr_crypt(key, iv, payload))

    def headers_for(offsets):
        sections = b""
        for index, payload in enumerate(payloads):
            sections += struct.pack(">QQIIIIIIII", offsets[index], len(payload), 2, index, 2,
                                    index, 3, index * 2, index * 2 + 1, 1)
        header = struct.pack(">QIIIIII", 0x950, 1, len(payloads), len(payloads) * 2, 0, 0, 0)
        return header + sections + data_keys

    header_size = metadata_headers_offset + len(headers_for([0] * len(payloads)))
    segment_start = header_size + ((-header_size) % 16)
    offsets, position = [], segment_start
    for blob in encrypted:
        offsets.append(position)
        position += len(blob) + ((-len(blob)) % 16)
    headers = headers_for(offsets)
    segments_blob = bytearray(position - segment_start)
    for index, blob in enumerate(encrypted):
        start = offsets[index] - segment_start
        segments_blob[start:start + len(blob)] = blob

    out = bytearray(segment_start + len(segments_blob))
    out[0:0x20] = struct.pack(">IIHHIQQ", 0x53434500, 2, revision, 1, meta_offset,
                              header_size, len(elf))
    out[0x20:0x70] = struct.pack(">10Q", 3, prog_id_offset, ehdr_offset, phdr_offset,
                                 shdr_offset or 0, seg_ext_offset, 0, 0, 0, 0)
    out[prog_id_offset:prog_id_offset + 0x20] = struct.pack(
        ">QIIQQ", 0x1010000001000003, 0x1000002, program_type, 0x0001000000000000, 0)
    out[ehdr_offset:ehdr_offset + 0x40] = elf[:0x40]
    for index, phdr in enumerate(phdrs):
        base = phdr_offset + index * e_phentsize
        out[base:base + e_phentsize] = struct.pack(">IIQQQQQQ", *phdr)
        base = seg_ext_offset + index * 0x20
        out[base:base + 0x20] = struct.pack(">QQIIQ", offsets[index],
                                            len(encrypted[index]), 1, 0, 1)
    out[metadata_info_offset:metadata_info_offset + 0x40] = cbc_encrypt(erk, riv, info)
    out[metadata_headers_offset:header_size] = ps3_self.ctr_crypt(meta_key, meta_iv, headers)
    out[segment_start:segment_start + len(segments_blob)] = segments_blob
    return bytes(out)


class SelfDecryptorTests(unittest.TestCase):
    def setUp(self):
        self.segments = [b"first segment payload", b"second segment, longer payload!"]
        self.elf = build_elf(self.segments)

    def test_round_trip_recovers_the_exact_elf(self):
        self.assertEqual(ps3_self.decrypt_self(wrap_self(self.elf)), self.elf)

    def test_header_names_the_retail_key_set(self):
        header = ps3_self.read_header(wrap_self(self.elf))
        self.assertEqual((header["program_type"], header["flags"]), (4, 0x13))
        self.assertEqual(header["type"], 1)
        self.assertEqual(header["metadata_offset"], 0x410)

    def test_an_unknown_revision_is_refused_before_any_key_is_chosen(self):
        with self.assertRaisesRegex(ValueError, "Unsupported SELF key set"):
            ps3_self.decrypt_self(wrap_self(self.elf, revision=0x0014))

    def test_a_library_selftype_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Unsupported SELF key set"):
            ps3_self.decrypt_self(wrap_self(self.elf, program_type=2))

    def test_a_debug_self_is_named_not_decrypted(self):
        with self.assertRaisesRegex(ValueError, "debug SELF"):
            ps3_self.decrypt_self(wrap_self(self.elf, revision=0x8013))

    def test_metadata_that_does_not_decrypt_stops_the_run(self):
        with self.assertRaisesRegex(ValueError, "did not decrypt"):
            ps3_self.decrypt_self(wrap_self(self.elf, corrupt_pad=True))

    def test_a_plain_elf_is_not_a_self(self):
        with self.assertRaisesRegex(ValueError, "does not start with SCE"):
            ps3_self.decrypt_self(self.elf)

    def test_truncated_input_is_rejected(self):
        blob = wrap_self(self.elf)
        with self.assertRaisesRegex(ValueError, "too short|truncated|out of bounds"):
            ps3_self.decrypt_self(blob[:0x60])
        with self.assertRaisesRegex(ValueError, "too short|truncated|out of bounds"):
            ps3_self.decrypt_self(blob[:-0x20])

    def test_decrypt_file_checks_the_pinned_hash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, target = root / "EBOOT.BIN", root / "EBOOT.elf"
            source.write_bytes(wrap_self(self.elf))
            expected = hashlib.sha256(self.elf).hexdigest()
            report = ps3_self.decrypt_file(source, target, expected_sha256=expected)
            self.assertEqual(target.read_bytes(), self.elf)
            self.assertEqual(report["output_sha256"], expected)
            self.assertEqual(report["program_type"], 4)
            target.unlink()
            with self.assertRaisesRegex(ValueError, "does not match the pinned"):
                ps3_self.decrypt_file(source, target, expected_sha256="0" * 64)
            self.assertFalse(target.exists())

    def test_cli_writes_the_elf_beside_the_self_and_refuses_overwrite(self):
        import contextlib
        import io
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "EBOOT.BIN"
            source.write_bytes(wrap_self(self.elf))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(ps3_self.main([str(source)]), 0)
            target = root / "EBOOT.elf"
            self.assertEqual(target.read_bytes(), self.elf)
            self.assertEqual(json.loads(out.getvalue())["output_sha256"],
                             hashlib.sha256(self.elf).hexdigest())
            with self.assertRaisesRegex(ValueError, "already exists"):
                ps3_self.main([str(source)])
            replaced = root / "custom.elf"
            replaced.write_bytes(b"stale")
            with contextlib.redirect_stdout(io.StringIO()):
                ps3_self.main([str(source), "-o", str(replaced), "--force"])
            self.assertEqual(replaced.read_bytes(), self.elf)

    def test_cli_refuses_a_missing_file_and_the_wrong_pin(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, "No such file"):
                ps3_self.main([str(root / "absent.BIN")])
            source = root / "EBOOT.BIN"
            source.write_bytes(wrap_self(self.elf))
            with self.assertRaisesRegex(ValueError, "does not match the pinned"), \
                    contextlib.redirect_stdout(io.StringIO()):
                ps3_self.main([str(source), "--expect-sha256", "0" * 64])
            self.assertFalse((root / "EBOOT.elf").exists())


if __name__ == "__main__":
    unittest.main()
