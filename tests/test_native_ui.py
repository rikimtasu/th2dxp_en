"""Asset-free native UI format/encoding and complete-copy boundaries."""
import copy
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import native_layout_patch
import native_ui_patch
import project


class NativeTextTests(unittest.TestCase):
    def test_preserves_date_arguments_and_tens_of_seconds(self):
        self.assertEqual(native_ui_patch.encode_text("%d月%d日 (%s)", "%d/%d (%s)", "cp932"), b"%d/%d (%s)")
        self.assertEqual(native_ui_patch.encode_text("残り およそ%d0秒", "About %d0 seconds remaining", "cp932"),
                         b"About %d0 seconds remaining")
        for translated in ("About %d seconds remaining", "About %s0 seconds remaining"):
            with self.subTest(translated=translated), self.assertRaisesRegex(ValueError, "printf"):
                native_ui_patch.encode_text("残り およそ%d0秒", translated, "cp932")
        with self.assertRaisesRegex(ValueError, "printf"):
            native_ui_patch.encode_text("%d月%d日 (%s)", "%s (%d/%d)", "cp932")

    def test_rejects_encoding_alias_loss_and_native_control_injection(self):
        with self.assertRaisesRegex(ValueError, "round-trip"):
            native_ui_patch.encode_text("元", "〜", "cp932")
        for text in ("", "  \n ", "Save\0Load", "Save\tLoad", "Save\x7f"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "nonblank|control"):
                native_ui_patch.encode_text("元", text, "cp932")
        self.assertEqual(native_ui_patch.encode_text("元", "Save\nLoad", "utf8"), b"Save\nLoad")

    def test_rejects_malformed_or_injected_percent_conversion(self):
        for translated in ("Progress: %n", "Progress: %q", "Progress: %%"):
            with self.subTest(translated=translated), self.assertRaisesRegex(ValueError, "printf|percent"):
                native_ui_patch.encode_text("進行中", translated, "cp932")

    def test_preserves_native_private_glyphs_in_music_titles(self):
        self.assertEqual(native_ui_patch.encode_text("なんちゃって\ue002", "Just Kidding \ue002", "cp932"),
                         b"Just Kidding \xf0\x42")
        with self.assertRaisesRegex(ValueError, "decorative glyphs"):
            native_ui_patch.encode_text("なんちゃって\ue002", "Just Kidding", "cp932")


def native_fixture():
    """A synthetic ELF layout with separately mapped code, UI and scenario data."""
    image = bytearray(0x660010)
    image[:6] = b"\x7fELF\x02\x02"
    struct.pack_into(">Q", image, 0x20, 0x40)
    struct.pack_into(">HH", image, 0x36, 56, 8)
    begin, end = native_layout_patch.CAVE_START, native_layout_patch.CAVE_START + 4
    struct.pack_into(">IIQQQQQQ", image, 0x40, 1, 5, 0, 0x10000, 0x10000, end, end, 0x10000)
    text = b"English UI\0"
    struct.pack_into(">IIQQQQQQ", image, 0x40 + 2 * 56, 1, 4,
                     0x650000, 0xA30000, 0xA30000, len(text), len(text), 0x10000)
    struct.pack_into(">IIQQQQQQ", image, 0x40 + 3 * 56, 1, 6,
                     0x660000, 0xA40000, 0xA40000, 16, 16, 0x10000)
    image[0x230:0x234] = bytes.fromhex("48000004")
    image[begin:end] = bytes.fromhex("60000000")
    struct.pack_into(">I", image, 0x64264C, 0xA30000)
    image[0x650000:0x650000 + len(text)] = text
    report = {"source_sha256": native_layout_patch.SOURCE_SHA256,
              "output_sha256": project.digest(image),
              "rx_extension": {"file_begin": begin, "file_end": end},
              "patches": [{"file_offset": "0x230", "after": "48000004"}],
              "data_patches": [{"file_offset": "0x64264c", "after": "00a30000"}],
              "ui_strings": {"program_header_index": 2, "file_offset": 0x650000,
                             "virtual_address": 0xA30000, "file_size": len(text), "flags": 4,
                             "sha256": project.digest(text), "records": [{} for _ in range(142)],
                             "translated_records": 142}}
    return bytes(image), report


class NativeCopyGuardTests(unittest.TestCase):
    def test_executable_helpers_require_exact_bounded_nonwritable_mapping(self):
        staged, report = native_fixture()
        image = bytearray(staged)
        payload = b"English UI\0" + bytes(5) + bytes.fromhex("60000000")
        image[0x650000:0x650000 + len(payload)] = payload
        struct.pack_into(">IIQQQQQQ", image, 0x40 + 2 * 56, 1, 5,
                         0x650000, 0xA30000, 0xA30000, len(payload), len(payload), 0x10000)
        report["ui_strings"].update(flags=5, file_size=len(payload), sha256=project.digest(payload))
        report["supplemental_code"] = [{"file_offset": 0x650010, "virtual_address": 0xA30010,
                                         "size": 4, "sha256": project.digest(payload[-4:])}]
        report["output_sha256"] = project.digest(image)
        staged = bytes(image)
        self.assertTrue(native_layout_patch.native_code_matches(staged, staged, report))
        for field, value in (("file_offset", 0x65000C), ("virtual_address", 0xA30014),
                             ("size", 8), ("sha256", "0" * 64)):
            invalid = copy.deepcopy(report)
            invalid["supplemental_code"][0][field] = value
            with self.subTest(field=field):
                self.assertFalse(native_layout_patch.native_code_matches(staged, staged, invalid))
        corrupted = bytearray(staged)
        corrupted[0x650010] ^= 1
        self.assertFalse(native_layout_patch.native_code_matches(bytes(corrupted), staged, report))
        for flags in (6, 7):
            writable = bytearray(staged)
            struct.pack_into(">I", writable, 0x40 + 2 * 56 + 4, flags)
            invalid = copy.deepcopy(report)
            invalid["ui_strings"]["flags"] = flags
            invalid["output_sha256"] = project.digest(writable)
            self.assertFalse(native_layout_patch.native_code_matches(bytes(writable), bytes(writable), invalid))

    def test_partial_copy_of_any_ui_component_fails_closed(self):
        staged, report = native_fixture()
        self.assertTrue(native_layout_patch.native_code_matches(staged, staged, report))
        for name, offset in (("code", 0x230), ("helper", native_layout_patch.CAVE_START),
                             ("table_pointer", 0x64264C), ("ui_payload", 0x650000),
                             ("ui_header", 0x40 + 2 * 56)):
            image = bytearray(staged)
            image[offset] ^= 1
            with self.subTest(component=name):
                self.assertFalse(native_layout_patch.native_code_matches(bytes(image), staged, report))

    def test_scenario_segment_may_move_but_cannot_overlap_read_only_ui(self):
        staged, report = native_fixture()
        image = bytearray(staged)
        struct.pack_into(">QQ", image, 0x40 + 3 * 56 + 16, 0xA50000, 0xA50000)
        self.assertTrue(native_layout_patch.native_code_matches(bytes(image), staged, report))
        struct.pack_into(">QQ", image, 0x40 + 3 * 56 + 16, 0xA30000, 0xA30000)
        self.assertFalse(native_layout_patch.native_code_matches(bytes(image), staged, report))

    def test_data_pointer_requires_ui_segment_and_reviewed_table_bounds(self):
        staged, report = native_fixture()
        for offset in ("0x64264d", "0x1000", "0x647c4c"):
            invalid = copy.deepcopy(report)
            invalid["data_patches"][0]["file_offset"] = offset
            with self.subTest(offset=offset):
                self.assertFalse(native_layout_patch.native_code_matches(staged, staged, invalid))
        del report["ui_strings"]
        self.assertFalse(native_layout_patch.native_code_matches(staged, staged, report))


if __name__ == "__main__":
    unittest.main()
