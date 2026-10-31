"""Synthetic DAT preservation and SDAT orchestration boundaries; no game assets."""
from contextlib import ExitStack
import hashlib
import json
import lzma
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import assets
import ui_archive
import scenario_source

DAT = ui_archive._dat_module()
KIT = ui_archive._native_kit()


def archive(path, files):
    """Build a tiny valid archive with nonzero unknown fields and metadata gaps."""
    names = bytearray(b"name-gap")
    offsets = []
    for name, _, _ in files:
        offsets.append(16 + len(names))
        names.extend(name.encode("latin1") + b"\0")
    table_offset = 16 + len(names) + 7
    start = table_offset + len(files) * 24 + 13
    payloads, rows = bytearray(b"payload-gap!!"), []
    for index, ((_, raw, compressed), name_offset) in enumerate(zip(files, offsets)):
        payload = scenario_source.pack(raw, KIT) if compressed else raw
        rows.append(struct.pack(">6I", name_offset, len(payload) if compressed else 0,
                                0x11110000 + index, len(raw), 0x22220000 + index, start))
        payloads.extend(payload)
        payloads.extend(b"pad")
        start += len(payload) + 3
    blob = (struct.pack(">4I", len(files), 0x12345678, 0xABCDEF01, table_offset)
            + bytes(names) + b"gap!!!!" + b"".join(rows) + bytes(payloads))
    path.write_bytes(blob)
    return blob, table_offset


def sdat_header(size, *, version=3, license_type=0, data_type=0,
                flags=0x0100003C, block_size=0x4000, content=b""):
    result = bytearray(144)
    result[:4] = b"NPD\0"
    struct.pack_into(">3I", result, 4, version, license_type, data_type)
    result[16:64] = content.ljust(48, b"\0")
    struct.pack_into(">IIQ", result, 128, flags, block_size, size)
    return bytes(result)


class DatStagingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source, self.output = self.root / "source.dat", self.root / "staged.dat"
        self.files = [("sys/title.tpl", b"old pixels" * 20, True),
                      ("raw/plain.bin", b"untouched raw\0\xff", False),
                      ("sys/untouched.tpl", b"untouched compressed" * 30, True)]
        self.original, self.table_offset = archive(self.source, self.files)

    def test_append_only_change_preserves_entire_template_and_unchanged_entries(self):
        replacement = b"replacement pixels" * 100
        report = ui_archive.stage_dat(self.source, {"sys/title.tpl": replacement}, self.output)
        staged = self.output.read_bytes()
        expected_prefix = bytearray(self.original)
        expected_prefix[self.table_offset:self.table_offset + 24] = staged[self.table_offset:self.table_offset + 24]
        self.assertEqual(staged[:len(self.original)], expected_prefix)
        self.assertEqual(self.source.read_bytes(), self.original)
        _, old_entries = DAT.parse_archive_table(self.source)
        _, entries = DAT.parse_archive_table(self.output)
        self.assertEqual([entry.name for entry in entries], [row[0] for row in self.files])
        self.assertGreaterEqual(entries[0].file_offset, len(self.original))
        self.assertEqual(entries[0].file_offset % 4, 0)
        self.assertEqual((entries[0].unknown0, entries[0].unknown1),
                         (old_entries[0].unknown0, old_entries[0].unknown1))
        for entry, (_, expected, _) in zip(entries, self.files):
            raw, _ = DAT.decompress_archive_entry(staged, entry)
            self.assertEqual(raw, replacement if entry.index == 0 else expected)
        self.assertEqual(report["output_sha256"], hashlib.sha256(staged).hexdigest())
        self.assertEqual(report["verification"]["unchanged_table_rows_preserved"], 2)
        self.assertFalse(report["runtime_accepted"])

    def test_replaces_raw_and_empty_entries_with_exact_bytes(self):
        replacements = {"raw/plain.bin": b"new raw bytes", "sys/title.tpl": b""}
        ui_archive.stage_dat(self.source, replacements, self.output)
        _, entries = DAT.parse_archive_table(self.output)
        for entry in entries:
            if entry.name in replacements:
                self.assertEqual(DAT.decompress_archive_entry(self.output.read_bytes(), entry)[0],
                                 replacements[entry.name])

    def test_table_rows_crossing_io_block_boundaries_are_verified_exactly(self):
        with patch.object(ui_archive, "BLOCK", 13):
            ui_archive.stage_dat(self.source, {"sys/title.tpl": b"new pixels"}, self.output)
        staged = self.output.read_bytes()
        expected = bytearray(self.original)
        expected[self.table_offset:self.table_offset + 24] = staged[self.table_offset:self.table_offset + 24]
        self.assertEqual(staged[:len(self.original)], expected)

    def test_incorrect_native_compressor_bytes_cannot_pass_consumer_verification(self):
        pack = scenario_source.pack
        with patch.object(scenario_source, "pack", side_effect=lambda raw, kit: pack(b"x" * len(raw), kit)):
            with self.assertRaisesRegex(ValueError, "Replacement verification failed"):
                ui_archive.stage_dat(self.source, {"sys/title.tpl": b"new pixels"}, self.output)

    def test_vendor_unknown_size_compression_is_rejected_before_append(self):
        # The old compressor roundtrips in Python but fails the EDGE contract.
        with patch.object(scenario_source, "pack", side_effect=lambda raw, kit: DAT.compress_archive_data(raw)):
            with self.assertRaisesRegex(ValueError, "properties/dictionary|explicit usize"):
                ui_archive.stage_dat(self.source, {"sys/title.tpl": b"new pixels"}, self.output)
        self.assertEqual(self.output.read_bytes(), self.original)

    def test_replacement_crosses_native_chunk_boundary_and_reextracts_completely(self):
        replacement = bytes(range(256)) * 256 + b"complete final chunk"
        report = ui_archive.stage_dat(self.source, {"sys/title.tpl": replacement}, self.output)
        _, entries = DAT.parse_archive_table(self.output)
        entry = entries[0]
        staged = self.output.read_bytes()
        chunks = ui_archive.validate_native_chunks(
            staged[entry.file_offset:entry.file_offset + entry.compressed_size], len(replacement))
        self.assertEqual([chunk["uncompressed_size"] for chunk in chunks], [32768, 32768, 20])
        self.assertEqual([chunk["flag"] for chunk in chunks], [0x80, 0x80, 0])
        self.assertEqual(DAT.decompress_archive_entry(staged, entry)[0], replacement)
        self.assertTrue(report["verification"]["native_chunk_contract_validated"])


    def test_unmodified_unknown_compression_is_preserved_without_decoding(self):
        _, entries = DAT.parse_archive_table(self.source)
        untouched = entries[2]
        original = bytearray(self.original)
        original[untouched.file_offset] = 0x7F  # Unsupported chunk flag in an untouched proprietary entry.
        self.source.write_bytes(original)
        ui_archive.stage_dat(self.source, {"sys/title.tpl": b"changed"}, self.output)
        length = untouched.compressed_size
        self.assertEqual(self.output.read_bytes()[untouched.file_offset:untouched.file_offset + length],
                         original[untouched.file_offset:untouched.file_offset + length])

    def test_rejects_existing_output_without_modifying_it(self):
        self.output.write_bytes(b"must survive")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            ui_archive.stage_dat(self.source, {"sys/title.tpl": b"new"}, self.output)
        self.assertEqual(self.output.read_bytes(), b"must survive")

    def test_rejects_bad_source_hash_before_creating_output(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            ui_archive.stage_dat(self.source, {"sys/title.tpl": b"new"}, self.output,
                                 expected_sha256="0" * 64)
        self.assertFalse(self.output.exists())

    def test_rejects_wrong_entry_count(self):
        with self.assertRaisesRegex(ValueError, "Expected 3516"):
            ui_archive.stage_dat(self.source, {"sys/title.tpl": b"new"}, self.output,
                                 expected_entry_count=3516)

    def test_rejects_unknown_empty_and_nonbyte_replacements(self):
        for replacements, message in [({}, "At least"), ({"sys/missing.tpl": b"x"}, "Unknown"),
                                      ({"sys/title.tpl": bytearray(b"x")}, "complete bytes")]:
            with self.subTest(replacements=replacements), self.assertRaisesRegex(ValueError, message):
                ui_archive.stage_dat(self.source, replacements, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_unsafe_names_even_when_not_present(self):
        for name in ("../outside", "/absolute", "a//b", "a/./b", "a\\b", "C:/a", "nul.txt", "a:stream", "a\0b", "a."):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "filename"):
                ui_archive.stage_dat(self.source, {name: b"x"}, self.output)

    def test_rejects_truncated_table_and_payload_bounds(self):
        for offset, value in ((12, len(self.original)), (self.table_offset + 20, len(self.original) + 1)):
            malformed = bytearray(self.original)
            struct.pack_into(">I", malformed, offset, value)
            self.source.write_bytes(malformed)
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "bounds"):
                ui_archive.stage_dat(self.source, {"sys/title.tpl": b"x"}, self.output)
            self.assertFalse(self.output.exists())

    def test_rejects_duplicate_source_names(self):
        archive(self.source, [("same.tpl", b"a", False), ("same.tpl", b"b", False)])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            ui_archive.stage_dat(self.source, {"same.tpl": b"x"}, self.output)

    def test_rejects_unterminated_name_region(self):
        malformed = bytearray(self.original)
        malformed[16:self.table_offset] = b"x" * (self.table_offset - 16)
        self.source.write_bytes(malformed)
        with self.assertRaisesRegex(ValueError, "unterminated"):
            ui_archive.stage_dat(self.source, {"sys/title.tpl": b"x"}, self.output)

    def test_detects_preservation_tampering(self):
        self.output.write_bytes(self.original[:-1] + b"!")
        with self.assertRaisesRegex(ValueError, "preservation"):
            ui_archive._verify_prefix(self.source, self.output, {}, assets.sha(self.source))

    def test_reports_address_overflow_instead_of_packing_truncated_offsets(self):
        with patch.object(ui_archive, "LIMIT", len(self.original) + 4):
            with self.assertRaisesRegex(ValueError, "32-bit"):
                ui_archive.stage_dat(self.source, {"sys/title.tpl": b"large replacement" * 100}, self.output)

    def test_rejects_installed_output_even_with_absent_filename(self):
        installed = self.root / "installed"
        installed.mkdir()
        (self.root / "project.json").write_text(json.dumps({"game_usrdir": str(installed)}))
        with patch.object(ui_archive, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "installed"):
                ui_archive.stage_dat(self.source, {"sys/title.tpl": b"x"}, installed / "new.dat")
        self.assertFalse((installed / "new.dat").exists())


class SourceVariantComparisonTests(unittest.TestCase):
    def test_exact_changed_partition_keeps_ui_and_font_inputs_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            source, variant = Path(directory) / "old.dat", Path(directory) / "fresh.dat"
            files = [("_initial/font.tpl", b"font", False), ("n/8000.bin", b"old!", False)]
            archive(source, files)
            archive(variant, [files[0], ("n/8000.bin", b"new!", False)])
            report = ui_archive._compare_variant_dat(source, variant, ("n/8000.bin",))
            self.assertEqual(report["identical_entries"], 1)
            self.assertEqual(report["changed_entries"], ["n/8000.bin"])
            self.assertTrue(report["ui_font_source_entries_identical"])

    def test_payload_change_without_table_change_is_not_missed(self):
        with tempfile.TemporaryDirectory() as directory:
            source, variant = Path(directory) / "old.dat", Path(directory) / "fresh.dat"
            archive(source, [("_initial/font.tpl", b"font", False), ("n/8200.bin", b"old!", False)])
            archive(variant, [("_initial/font.tpl", b"font", False), ("n/8200.bin", b"new!", False)])
            with self.assertRaisesRegex(ValueError, "unapproved entry: n/8200.bin"):
                ui_archive._compare_variant_dat(source, variant, ())

    def test_changed_font_and_missing_expected_difference_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, variant = Path(directory) / "old.dat", Path(directory) / "fresh.dat"
            archive(source, [("_initial/font.tpl", b"font", False)])
            archive(variant, [("_initial/font.tpl", b"oops", False)])
            with self.assertRaisesRegex(ValueError, "unapproved entry"):
                ui_archive._compare_variant_dat(source, variant, ("n/8000.bin",))
            variant.write_bytes(source.read_bytes())
            with self.assertRaisesRegex(ValueError, "partition"):
                ui_archive._compare_variant_dat(source, variant, ("n/8000.bin",))

    def test_changed_header_is_not_treated_as_an_entry_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            source, variant = Path(directory) / "old.dat", Path(directory) / "fresh.dat"
            raw, _ = archive(source, [("n/8000.bin", b"old!", False)])
            changed = bytearray(raw)
            changed[4] ^= 1
            variant.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "header or filename"):
                ui_archive._compare_variant_dat(source, variant, ("n/8000.bin",))


class NativeChunkContractTests(unittest.TestCase):
    def packed(self, raw):
        return scenario_source.pack(raw, KIT)

    def test_native_codec_exact_size_dictionary_boundaries_and_eos_free(self):
        for size in (1, 2, 3, 31, 8192, 32767, 32768, 32769, 65536):
            raw = (bytes(range(256)) * ((size + 255) // 256))[:size]
            payload = self.packed(raw)
            with self.subTest(size=size):
                chunks = ui_archive.validate_native_chunks(payload, size)
                self.assertEqual(sum(chunk["uncompressed_size"] for chunk in chunks), size)
                for chunk in chunks:
                    start = chunk["offset"] + 4
                    self.assertEqual(payload[start:start + 5], bytes.fromhex("5d00200000"))
                    self.assertEqual(struct.unpack_from("<Q", payload, start + 5)[0],
                                     chunk["uncompressed_size"])

    def test_unknown_size_and_dictionary_mismatch_are_not_decoder_compatibility(self):
        raw = b"source-backed native properties" * 40
        valid = self.packed(raw)
        unknown = bytearray(valid)
        unknown[9:17] = b"\xff" * 8
        dictionary = bytearray(valid)
        dictionary[5:9] = struct.pack("<I", 8 * 1024 * 1024)
        for payload, message in ((unknown, "explicit usize"), (dictionary, "dictionary")):
            # Structural native checks, not a successful Python decode, decide.
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                ui_archive.validate_native_chunks(bytes(payload), len(raw))
        legacy = DAT.compress_archive_data(raw)
        self.assertEqual(lzma.decompress(legacy[4:4 + (struct.unpack_from(">I", legacy)[0] & 0xFFFFFF)],
                                         format=lzma.FORMAT_ALONE), raw)
        with self.assertRaises(ValueError):
            ui_archive.validate_native_chunks(legacy, len(raw))

    def test_known_size_range_flush_does_not_read_a_spurious_extra_symbol(self):
        value, raw = 10, bytearray()
        for _ in range(32768):
            value = (1664525 * value + 1013904223) & 0xFFFFFFFF
            raw.append(value >> 30)
        payload = self.packed(bytes(raw))
        chunks = ui_archive.validate_native_chunks(payload, len(raw))
        size = struct.unpack_from(">I", payload)[0]
        self.assertEqual(lzma.decompress(payload[4:4 + size], format=lzma.FORMAT_ALONE), raw)
        self.assertEqual([chunk["uncompressed_size"] for chunk in chunks], [32768])

    def test_continuation_stride_and_total_size_are_checked_before_decoding(self):
        short = bytearray(self.packed(b"too short for a continuation"))
        short[0] = 0x80
        with self.assertRaisesRegex(ValueError, "exactly 32768"):
            ui_archive.validate_native_chunks(bytes(short), 32769)
        valid = self.packed(b"a" * 32769)
        early_final = bytearray(valid)
        early_final[0] = 0
        late_final = bytearray(self.packed(b"a" * 32768))
        late_final[0] = 0x80
        for payload, size in ((early_final, 32769), (late_final, 32768), (valid, 32768)):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, "total raw size"):
                ui_archive.validate_native_chunks(bytes(payload), size)
        oversized = bytearray(self.packed(b"small"))
        struct.pack_into("<Q", oversized, 9, 32769)
        with self.assertRaisesRegex(ValueError, "output bounds"):
            ui_archive.validate_native_chunks(bytes(oversized), 32769)

    def test_bounds_padding_trailing_records_and_empty_entries_are_strict(self):
        raw = b"native"
        payload = self.packed(raw)
        self.assertEqual(ui_archive.validate_native_chunks(b"", 0), [])
        bad_flag = bytearray(payload)
        bad_flag[0] = 0x40  # Replacements never guess a different native raw-record path.
        oversized = bytearray(payload)
        struct.pack_into(">I", oversized, 0, len(payload))
        for data, size in ((b"\0", 1), (payload[:-1], len(raw)), (bad_flag, len(raw)),
                           (oversized, len(raw)), (payload + b"\0" * 4, len(raw)),
                           (b"", 1), (payload, 0)):
            with self.subTest(data=bytes(data), size=size), self.assertRaises(ValueError):
                ui_archive.validate_native_chunks(bytes(data), size)
        # Locate an actual alignment gap rather than assuming a compressed size.
        for size in range(1, 33):
            packed = bytearray(self.packed(b"a" * size))
            end = 4 + struct.unpack_from(">I", packed)[0]
            if end < len(packed):
                packed[end] = 1
                with self.assertRaisesRegex(ValueError, "padding"):
                    ui_archive.validate_native_chunks(bytes(packed), size)
                break
        else:
            self.fail("Synthetic native samples did not exercise alignment padding")


class SdatBoundaryTests(unittest.TestCase):
    def test_only_exact_explicit_legacy_source_warnings_are_permitted(self):
        success = "File successfully parsed!\nFile successfully decrypted!\n"
        with tempfile.TemporaryDirectory() as directory:
            for index, (message, allow, accepted) in enumerate((
                    (success + ui_archive.LEGACY_SOURCE_WARNINGS[0], (), False),
                    (success + ui_archive.LEGACY_SOURCE_WARNINGS[0], ui_archive.LEGACY_SOURCE_WARNINGS, True),
                    (success + "WARNING: Other failure!", ui_archive.LEGACY_SOURCE_WARNINGS, False),
                    (success + "ERROR: Invalid data", ui_archive.LEGACY_SOURCE_WARNINGS, False))):
                def run(command, *, stdout, stderr, check):
                    stdout.write(message.encode())
                    return SimpleNamespace(returncode=0)
                with patch.object(ui_archive.subprocess, "run", side_effect=run):
                    log = Path(directory) / f"{index}.log"
                    if accepted:
                        ui_archive._invoke(["synthetic"], log, ("File successfully decrypted!",),
                                           allowed_warnings=allow)
                    else:
                        with self.assertRaisesRegex(ValueError, "did not complete"):
                            ui_archive._invoke(["synthetic"], log, ("File successfully decrypted!",),
                                               allowed_warnings=allow)

    def test_original_header_semantics_are_read_not_guessed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sdat"
            original = sdat_header(1234, version=4, data_type=20, content=b"UP0000-TEST")
            path.write_bytes(original)
            header = ui_archive._sdat_header(path)
            self.assertEqual((header["version"], header["license"], header["type"]), (4, 0, 20))
            self.assertEqual(header["content_id"], "UP0000-TEST")
            self.assertEqual(header["flags"], 0x0100003C)
            self.assertEqual(header["header_sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(path.read_bytes(), original)

    def test_rejects_unsupported_container_semantics(self):
        cases = [b"short", sdat_header(1, license_type=3), sdat_header(1, version=9),
                 sdat_header(1, flags=0xC), sdat_header(1, block_size=0x8000),
                 sdat_header(1, content=b"x" * 48), sdat_header(1, content=b"abc\0hidden")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sdat"
            for blob in cases:
                path.write_bytes(blob)
                with self.subTest(blob=blob[:16]), self.assertRaises(ValueError):
                    ui_archive._sdat_header(path)

    def test_zero_exit_requires_all_actual_success_messages_and_no_failure(self):
        cases = [(0, "Usage: make_npdata"), (0, "File successfully parsed!"),
                 (0, "File successfully parsed!\nFile successfully decrypted!\nDecryption failed!"),
                 (1, "File successfully parsed!\nFile successfully decrypted!")]
        with tempfile.TemporaryDirectory() as directory:
            for index, (code, message) in enumerate(cases):
                def run(command, *, stdout, **kwargs):
                    stdout.write(message.encode())
                    return SimpleNamespace(returncode=code)
                with patch.object(ui_archive.subprocess, "run", side_effect=run):
                    with self.subTest(index=index), self.assertRaisesRegex(ValueError, "successfully"):
                        ui_archive._invoke(["fake"], Path(directory) / f"{index}.log",
                                           ("File successfully parsed!", "File successfully decrypted!"))


    def test_stage_rejects_paths_outside_staging_roots_and_base_typography(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(ui_archive, "ROOT", root):
                for output in (root / "outside", root / "build", root / "build/typography-probe/new"):
                    with self.subTest(output=output), self.assertRaisesRegex(ValueError, "directory|immutable"):
                        ui_archive.stage({"sys/title.tpl": b"x"}, output)

    def test_installed_folder_is_operator_configuration_not_a_committed_path(self):
        self.assertRaisesRegex(ValueError, "no game_usrdir", assets.configured_usrdir, {})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project.json").write_text(json.dumps({"game_usrdir": "  "}))
            with patch.object(ui_archive, "ROOT", root):
                self.assertIsNone(ui_archive._installed_root())
                (root / "project.json").write_text(json.dumps({"game_usrdir": str(root / "game")}))
                self.assertEqual(ui_archive._installed_root(), (root / "game").resolve())


class SyntheticRoundtripTests(unittest.TestCase):
    """Mock only the external crypto boundary, not DAT assembly or SHA proof.

    This proves orchestration/failure handling, not real SDAT cryptography or
    runtime compatibility. A real stage must execute the pinned existing tool.
    """
    def test_full_staging_reports_exact_hash_proof_and_removes_temporary_dat(self):
        self._stage_with_synthetic_container(corrupt=False)

    def test_full_sha_rejects_same_size_corruption_even_after_cli_success(self):
        self._stage_with_synthetic_container(corrupt=True)

    def test_verified_backup_is_used_without_modifying_changed_installed_archive(self):
        self._stage_with_synthetic_container(corrupt=False, backup=True)

    def test_wrong_backup_hash_fails_before_creating_staged_outputs(self):
        self._stage_with_synthetic_container(corrupt=False, backup=True, bad_backup=True)

    def test_pinned_variant_is_decrypted_compared_and_preserved(self):
        self._stage_with_synthetic_container(corrupt=False, variant=True)

    def test_wrong_variant_decrypted_dat_fails_closed(self):
        self._stage_with_synthetic_container(corrupt=False, variant=True, bad_variant_dat=True)

    def test_variant_cannot_replace_its_source_specific_entries(self):
        self._stage_with_synthetic_container(corrupt=False, variant=True, replace_variant_entry=True)

    def _stage_with_synthetic_container(self, corrupt, backup=False, bad_backup=False,
                                       variant=False, bad_variant_dat=False, replace_variant_entry=False):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            source = root / "source.dat"
            archive(source, [(f"sys/{index}.tpl", bytes([index % 256]), False) for index in range(3516)])
            installed = root / "installed"
            installed.mkdir()
            (installed / "data.sdat").write_bytes(sdat_header(source.stat().st_size))
            (root / "project.json").write_text(json.dumps({"game_usrdir": str(installed)}))
            binary = root / "make_npdata.exe"
            binary.write_bytes(b"synthetic test boundary; never executed")
            upstream = root / "vendor/make_npdata/Linux"
            upstream.mkdir(parents=True)
            (upstream / "make_npdata.c").write_bytes(b"synthetic provenance")
            manifest = root / "decryption.json"
            manifest.write_text(json.dumps({"output_size": source.stat().st_size,
                                           "output_sha256": assets.sha(source), "entry_count": 3516,
                                           "binary_sha256": assets.sha(binary),
                                           "make_npdata_revision": assets.REVISION,
                                           "source_sha256": assets.sha(installed / "data.sdat")}))
            original_backup = root / "original-data.sdat"
            options = {}
            if variant:
                _, entries = DAT.parse_archive_table(source)
                variant_bytes = bytearray(source.read_bytes())
                variant_bytes[entries[1].file_offset] ^= 1
                original_backup.write_bytes(sdat_header(len(variant_bytes)) + variant_bytes)
                variant_sha = hashlib.sha256(variant_bytes).hexdigest()
                stack.enter_context(patch.object(ui_archive, "SOURCE_VARIANTS", {
                    assets.sha(original_backup): {"name": "synthetic-variant",
                                                 "source_size": original_backup.stat().st_size,
                                                 "dat_size": len(variant_bytes),
                                                 "dat_sha256": "0" * 64 if bad_variant_dat else variant_sha,
                                                 "changed_entries": ("sys/1.tpl",)}}))
                options["source_sdat"] = original_backup
            if backup:
                original_backup.write_bytes((installed / "data.sdat").read_bytes()
                                            + (b"wrong original" if bad_backup else b""))
                (installed / "data.sdat").write_bytes(sdat_header(source.stat().st_size + 32))
                options["source_sdat"] = original_backup
            installed_snapshot = (installed / "data.sdat").read_bytes()
            backup_snapshot = original_backup.read_bytes() if backup or variant else None
            for name, value in (("ROOT", root), ("SOURCE", source), ("MANIFEST", manifest)):
                stack.enter_context(patch.object(ui_archive, name, value))
            stack.enter_context(patch.object(assets, "BINARY", binary))
            stack.enter_context(patch.object(assets, "UPSTREAM", upstream))
            stack.enter_context(patch.object(ui_archive.subprocess, "check_output", return_value=assets.REVISION))
            stack.enter_context(patch.object(ui_archive.build_sdat_tool, "validated_tool",
                                            return_value=(binary, {"synthetic_crypto_boundary": True})))

            def invoke(command, log, successes, **kwargs):
                log.write_text("\n".join(successes))
                if command[1] == "--verify":
                    return
                input_path, output_path = Path(command[3]), Path(command[4])
                if command[2] == "-e":
                    raw = input_path.read_bytes()
                    output_path.write_bytes(sdat_header(len(raw), flags=0x0100000C) + raw)
                else:
                    raw = input_path.read_bytes()[144:]
                    if corrupt:
                        raw = bytes([raw[0] ^ 1]) + raw[1:]
                    output_path.write_bytes(raw)

            stack.enter_context(patch.object(ui_archive, "_invoke", side_effect=invoke))
            output = root / "build/ui-stage"
            original_source, original_manifest = source.read_bytes(), manifest.read_bytes()
            replacements = {"sys/1.tpl" if replace_variant_entry else "sys/0.tpl": b"actual replacement"}
            if bad_backup:
                with self.assertRaisesRegex(ValueError, "Explicit source SDAT SHA-256"):
                    ui_archive.stage({"sys/0.tpl": b"actual replacement"}, output, **options)
                self.assertFalse(output.exists())
            elif corrupt:
                with self.assertRaisesRegex(ValueError, "complete DAT SHA-256"):
                    ui_archive.stage({"sys/0.tpl": b"actual replacement"}, output, **options)
                self.assertFalse((output / "report.json").exists())
            elif bad_variant_dat or replace_variant_entry:
                message = "decrypted DAT" if bad_variant_dat else "preserve source-variant-specific"
                with self.assertRaisesRegex(ValueError, message):
                    ui_archive.stage(replacements, output, **options)
                self.assertFalse((output / "report.json").exists())
            else:
                report = ui_archive.stage(replacements, output, **options)
                self.assertEqual(report["roundtrip"]["complete_dat_sha256"], assets.sha(output / "data.dat"))
                self.assertEqual(report["sdat"]["sha256"], assets.sha(output / "data.sdat"))
                self.assertTrue(report["roundtrip"]["matches_staged_dat"])
                self.assertFalse(report["runtime_accepted"])
                self.assertEqual(report["original_sdat"]["full_archive_hash_rechecked"], backup or variant)
                if backup or variant:
                    self.assertEqual(report["original_sdat"]["path"], str(original_backup))
                if variant:
                    self.assertEqual(report["source_variant"]["comparison"]["identical_entries"], 3515)
                    self.assertEqual(report["dat"]["source_sha256"], variant_sha)
                    self.assertFalse(report["source_variant"]["source_cryptographically_authenticated"])
                    self.assertEqual((output / "source-variant.dat").read_bytes(), bytes(variant_bytes))
                    _, rebuilt_entries = DAT.parse_archive_table(output / "data.dat")
                    self.assertEqual(DAT.decompress_archive_entry((output / "data.dat").read_bytes(),
                                                                 rebuilt_entries[1])[0], bytes([0]))
                self.assertTrue((output / "report.json").is_file())
                with self.assertRaisesRegex(ValueError, "already exists"):
                    ui_archive.stage({"sys/0.tpl": b"different"}, output)
            self.assertEqual(list(output.glob("roundtrip-*")), [])
            self.assertEqual(source.read_bytes(), original_source)
            self.assertEqual(manifest.read_bytes(), original_manifest)
            self.assertEqual((installed / "data.sdat").read_bytes(), installed_snapshot)
            if backup or variant:
                self.assertEqual(original_backup.read_bytes(), backup_snapshot)


if __name__ == "__main__":
    unittest.main()
