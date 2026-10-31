"""Synthetic patch-data build/apply boundaries; no game data involved."""
import json
import struct
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import patch_data
import patch_game
from patch_fixtures import elf_like, make_dat, make_sdat, patched_dat, sha


class TempFolderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def make_pair(self, pristine, patched):
        return self.write("pristine.bin", pristine), self.write("patched.bin", patched)


class SharedHashTests(TempFolderTests):
    def test_hash_and_progress_are_preserved_for_both_entry_points(self):
        path = self.write("hash.bin", b"0123456789")
        for hasher in (patch_data.sha256_file, patch_game.sha256_file):
            with self.subTest(hasher=hasher):
                progress = []
                with patch.object(patch_data, "BLOCK", 4):
                    actual = hasher(str(path), lambda done, total: progress.append((done, total)))
                self.assertEqual(actual, sha(path.read_bytes()))
                self.assertEqual(progress, [(4, 10), (8, 10), (10, 10)])

    def test_empty_file_hash_needs_no_progress_callback(self):
        path = self.write("empty.bin", b"")
        for hasher in (patch_data.sha256_file, patch_game.sha256_file):
            progress = []
            self.assertEqual(hasher(path, lambda *args: progress.append(args)), sha(b""))
            self.assertEqual(progress, [])


class EditRunTests(unittest.TestCase):
    def test_run_edges_and_gap_thresholds(self):
        cases = [
            (b"", b"tail", 16, []),
            (b"same", b"same", 16, []),
            (b"abc", b"abc-tail", 16, []),
            (b"abcd", b"aX", 16, [(1, 1)]),
            (b"abcdef", b"XbcdeY", 4, [(0, 6)]),
            (b"abcdef", b"XbcdeY", 3, [(0, 1), (5, 1)]),
            (b"abcdef", b"aXXdYf", 0, [(1, 2), (4, 1)]),
            (b"abcdef", b"aXXdYf", -1, [(1, 2), (4, 1)]),
            (b"abcdef", b"aXXdYf", 1, [(1, 4)]),
            (b"abc", b"XYZ-tail", 0, [(0, 3)]),
        ]
        for pristine, patched, gap, expected in cases:
            with self.subTest(pristine=pristine, patched=patched, gap=gap):
                self.assertEqual(patch_data.edit_runs(pristine, patched, gap=gap), expected)


class ElfPatchTests(TempFolderTests):
    def setUp(self):
        super().setUp()
        self.pristine = elf_like(b"pristine", 4096, seed=1)
        patched = bytearray(self.pristine)
        patched[0x20:0x30] = b"changed header!!"
        patched[0x400:0x404] = b"\xff\xff\xff\xff"
        patched += b"appended segment bytes" * 64
        self.patched = bytes(patched)
        self.source, _ = self.make_pair(self.pristine, self.patched)
        self.patch = self.root / "patch"
        self.spec = patch_data.build_elf_patch(self.source, self.root / "patched.bin", self.patch)

    def test_round_trip_recovers_the_patched_image(self):
        target = self.root / "out.elf"
        report = patch_data.apply_elf_patch(self.source, target, self.patch, self.spec)
        self.assertEqual(target.read_bytes(), self.patched)
        self.assertEqual(report["output_sha256"], sha(self.patched))

    def test_edits_are_merged_and_cover_every_changed_byte(self):
        self.assertEqual(len(self.spec["edits"]), 2)
        self.assertEqual(self.spec["edits"][0], [0x20, 0x10])
        self.assertEqual(self.spec["edits_bytes"], 20)
        self.assertEqual(self.spec["tail_bytes"], len(self.patched) - len(self.pristine))

    def test_a_clean_unchanged_image_needs_no_edits(self):
        spec = patch_data.build_elf_patch(self.source, self.source, self.root / "same")
        self.assertEqual(spec["edits"], [])
        self.assertEqual(spec["edits_bytes"], 0)
        target = self.root / "same.elf"
        patch_data.apply_elf_patch(self.source, target, self.root / "same", spec)
        self.assertEqual(target.read_bytes(), self.pristine)

    def test_a_different_pristine_executable_is_refused(self):
        other = self.write("other.bin", elf_like(b"other", 4096, seed=2))
        with self.assertRaisesRegex(ValueError, "does not match the patch data"):
            patch_data.apply_elf_patch(other, self.root / "out.elf", self.patch, self.spec)
        self.assertFalse((self.root / "out.elf").exists())

    def test_a_modified_edit_payload_is_refused(self):
        path = self.patch / self.spec["edits_file"]
        path.write_bytes(path.read_bytes()[:-1] + b"\x00")
        with self.assertRaisesRegex(ValueError, "edit payload"):
            patch_data.apply_elf_patch(self.source, self.root / "out.elf", self.patch, self.spec)

    def test_overlapping_edit_runs_are_refused(self):
        broken = dict(self.spec)
        broken["edits"] = [[0x20, 8], [0x24, 8]]
        broken["edits_bytes"] = 16
        broken["edits_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "edit payload length|edit payload hash"):
            patch_data.apply_elf_patch(self.source, self.root / "out.elf", self.patch, broken)

    def test_an_edit_run_past_the_pristine_image_is_refused(self):
        broken = dict(self.spec)
        broken["edits"] = [[0x20, 16], [self.spec["source_size"] - 2, 4]]
        with self.assertRaisesRegex(ValueError, "exceeds the pristine image"):
            patch_data.apply_elf_patch(self.source, self.root / "out.elf", self.patch, broken)


class ArchivePatchTests(TempFolderTests):
    def setUp(self):
        super().setUp()
        self.entries = [("a.bin", b"AAAA"), ("b.bin", b"BBBBBBBB"), ("c.bin", b"C" * 64)]
        self.pristine = make_dat(self.entries)
        self.source = self.write("pristine.dat", self.pristine)
        self.patched_bytes = patched_dat(self.pristine, {"a.bin": b"new-A" * 9,
                                                         "c.bin": b"new-C" * 40})
        self.patched = self.write("patched.dat", self.patched_bytes)
        self.patch = self.root / "patch"
        self.spec = patch_data.build_archive_patch(self.source, self.patched, self.patch)

    def test_round_trip_recovers_the_patched_archive(self):
        target = self.root / "out.dat"
        report = patch_data.apply_archive_patch(self.source, target, self.patch, self.spec)
        self.assertEqual(target.read_bytes(), self.patched_bytes)
        self.assertEqual(report["output_sha256"], sha(self.patched_bytes))

    def test_only_changed_rows_are_shipped(self):
        self.assertEqual([row["name"] for row in self.spec["replacements"]], ["a.bin", "c.bin"])
        self.assertEqual(self.spec["entry_count"], 3)
        self.assertEqual(self.spec["output_dat_size"], len(self.patched_bytes))

    def test_row_metadata_is_carried_for_the_applier(self):
        first = self.spec["replacements"][0]
        self.assertEqual(first["original_raw_size"], 4)
        self.assertEqual(first["original_compressed_size"], 0)
        self.assertEqual(first["row_offset"], self.spec["entries_offset"])
        self.assertEqual(first["chunk"], "archive/0000.bin")

    def test_a_modified_chunk_is_refused(self):
        chunk = self.patch / self.spec["replacements"][0]["chunk"]
        chunk.write_bytes(chunk.read_bytes()[:-1] + b"\x00")
        with self.assertRaisesRegex(ValueError, "was modified|wrong length"):
            patch_data.apply_archive_patch(self.source, self.root / "out.dat", self.patch,
                                           self.spec)

    def test_a_different_pristine_archive_is_refused(self):
        other = self.write("other.dat", make_dat([("a.bin", b"ZZZZ")]))
        with self.assertRaisesRegex(ValueError, "pristine BLJM60381 DAT"):
            patch_data.apply_archive_patch(other, self.root / "out.dat", self.patch, self.spec)

    def test_an_existing_target_is_never_overwritten(self):
        target = self.write("out.dat", b"keep me")
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            patch_data.apply_archive_patch(self.source, target, self.patch, self.spec)
        self.assertEqual(target.read_bytes(), b"keep me")

    def test_a_row_that_moved_its_name_is_refused_at_build_time(self):
        broken = bytearray(self.patched_bytes)
        _, _, _, _, _, offset = struct.unpack_from(">6I", broken, self.spec["entries_offset"])
        struct.pack_into(">I", broken, self.spec["entries_offset"] + 8, 99)
        path = self.write("broken.dat", bytes(broken))
        with self.assertRaisesRegex(ValueError, "changed more than its sizes"):
            patch_data.build_archive_patch(self.source, path, self.root / "broken")


class WholePatchTests(TempFolderTests):
    def setUp(self):
        super().setUp()
        self.pristine_elf = elf_like(b"pristine", 1024, seed=3)
        patched = bytearray(self.pristine_elf)
        patched[0x40:0x44] = b"\xde\xad\xbe\xef"
        self.patched_elf = bytes(patched) + b"tail-data" * 32
        self.pristine_dat = make_dat([("a.bin", b"A" * 8), ("b.bin", b"B" * 16)])
        self.patched_dat = patched_dat(self.pristine_dat, {"b.bin": b"new" * 21})
        self.elf_source = self.write("EBOOT.elf", self.pristine_elf)
        self.dat_source = self.write("data.dat", self.pristine_dat)
        self.elf_target = self.write("EBOOT_EN.elf", self.patched_elf)
        self.dat_target = self.write("data_EN.dat", self.patched_dat)
        self.sdat_source = self.write("pristine.sdat", make_sdat(self.pristine_dat))
        self.sdat_target = self.write("patched.sdat", make_sdat(self.patched_dat))

    def build(self, output):
        return patch_data.build(self.elf_source, self.elf_target, self.dat_source,
                                self.dat_target, output, pristine_sdat=self.sdat_source,
                                patched_sdat=self.sdat_target, log=lambda *_: None)

    def test_build_writes_a_manifest_and_verifies_its_own_output(self):
        manifest = self.build(self.root / "patch")
        saved = json.loads((self.root / "patch" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["schema"], patch_data.SCHEMA_VERSION)
        self.assertEqual(saved["elf"]["output_sha256"], sha(self.patched_elf))
        self.assertEqual(saved["archive"]["output_dat_sha256"], sha(self.patched_dat))
        self.assertEqual(manifest["patch"]["version"], "0.1")

    def test_the_shipped_folder_rebuilds_both_artifacts(self):
        self.build(self.root / "patch")
        elf, dat = patch_data.verify(self.root / "patch", self.elf_source, self.dat_source,
                                     log=lambda *_: None)
        self.assertEqual(elf["output_sha256"], sha(self.patched_elf))
        self.assertEqual(dat["output_sha256"], sha(self.patched_dat))

    def test_build_refuses_to_overwrite_a_patch_folder(self):
        self.build(self.root / "patch")
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            self.build(self.root / "patch")

    def test_load_manifest_names_a_folder_without_patch_data(self):
        folder = self.root / "empty"
        folder.mkdir()
        with self.assertRaisesRegex(ValueError, "Not a patch folder"):
            patch_data.load_manifest(folder)

    def test_an_unsupported_schema_is_refused(self):
        self.build(self.root / "patch")
        path = self.root / "patch" / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["schema"] = 99
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unsupported patch data schema"):
            patch_data.load_manifest(self.root / "patch")

    def test_summary_reports_the_shipped_sizes(self):
        manifest = self.build(self.root / "patch")
        rows = patch_data.summary(manifest)
        self.assertEqual(rows["archive_replacements"], 1)
        self.assertEqual(rows["elf_payload_bytes"],
                         manifest["elf"]["edits_bytes"] + manifest["elf"]["tail_bytes"])

    def test_the_archive_header_is_carried_for_re_encryption(self):
        manifest = self.build(self.root / "patch")
        header = manifest["archive"]["header"]
        self.assertEqual(header["version"], 3)
        self.assertEqual(header["license"], 0)
        self.assertEqual(header["type"], 0)
        self.assertEqual(header["content_id"], "")
        self.assertEqual(header["block_size"], 0x4000)
        self.assertEqual(manifest["archive"]["source_sdat_sha256"],
                         sha(make_sdat(self.pristine_dat)))
        self.assertEqual(manifest["archive"]["output_sdat_sha256"],
                         sha(make_sdat(self.patched_dat)))

    def test_a_paired_sdat_that_describes_other_bytes_is_refused(self):
        self.write("wrong.sdat", make_sdat(self.patched_dat, dat_size=1234))
        with self.assertRaisesRegex(ValueError, "does not describe the patched DAT"):
            patch_data.build(self.elf_source, self.elf_target, self.dat_source,
                             self.dat_target, self.root / "patch2",
                             pristine_sdat=self.sdat_source,
                             patched_sdat=self.root / "wrong.sdat", log=lambda *_: None)

    def test_a_non_license_zero_header_is_refused(self):
        broken = bytearray(make_sdat(self.pristine_dat))
        struct.pack_into(">I", broken, 8, 1)
        path = self.write("licensed.sdat", bytes(broken))
        with self.assertRaisesRegex(ValueError, "license-0 SDAT"):
            patch_data.read_sdat_header(path)


if __name__ == "__main__":
    unittest.main()
