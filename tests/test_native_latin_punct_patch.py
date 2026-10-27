"""Check the ASCII punctuation atlas extension on synthetic data."""
from pathlib import Path
import string
import sys
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import geninterface_latin
import native_latin_punct_patch as punct
import project


class PunctuationSetTests(unittest.TestCase):
    def test_set_is_every_fitting_printable_punctuation(self):
        expected = {char for char in string.punctuation
                    if char not in geninterface_latin.BRACKETS and char not in punct.EXCLUDED}
        self.assertEqual(set(punct.PUNCTUATION), expected)
        self.assertEqual(len(punct.PUNCTUATION), 23)
        self.assertFalse(set(punct.PUNCTUATION) & set(geninterface_latin.REPLACED))

    def test_overflowing_aliases_stay_on_their_original_cells(self):
        for char in "$|":
            self.assertNotIn(char, punct.PUNCTUATION)
            self.assertIn(char, punct.EXCLUDED)
        self.assertNotIn("\\", punct.PUNCTUATION)
        self.assertIn("yen", punct.EXCLUDED["\\"])

    def test_every_rendered_corpus_character_is_covered(self):
        corpus = ".,'\"?!:;-~%&+/=*<>#@^_`"
        self.assertEqual([char for char in corpus if char not in punct.PUNCTUATION], [])

    def test_advance_keeps_six_pixel_padding(self):
        self.assertEqual(punct.ADVANCE_PADDING, 6)
        self.assertEqual(punct.CELL, 48)


class CellPackingTests(unittest.TestCase):
    def raster(self, width=6, height=6, top=-6):
        return Image.new("L", (width, height), 255), (4, top, 4 + width, top + height)

    def test_full_stop_packs_on_the_latin_baseline(self):
        raster, bounds = self.raster()
        cell, ink, placement, pair = punct.pack_cell(raster, bounds)
        self.assertEqual(placement[1], geninterface_latin.BASELINE - 6)
        self.assertEqual(pair, (ink[0], ink[2] - ink[0]))
        self.assertEqual(cell.getbbox(), ink)
        self.assertGreaterEqual(ink[0], geninterface_latin.SAMPLING_BORDER)
        self.assertLessEqual(ink[3], punct.CELL - geninterface_latin.SAMPLING_BORDER)

    def test_overflowing_ink_is_rejected_not_squeezed(self):
        raster, bounds = self.raster(width=47, height=47, top=-30)
        with self.assertRaisesRegex(ValueError, "sampling border cannot fit"):
            punct.pack_cell(raster, bounds)

    def test_descender_beyond_the_cell_is_rejected(self):
        raster, bounds = self.raster(height=14, top=0)
        with self.assertRaisesRegex(ValueError, "sampling border cannot fit"):
            punct.pack_cell(raster, bounds)

    def test_quantization_sets_the_metric_pair(self):
        raster = Image.new("L", (8, 8), 200)
        _, ink, _, pair = punct.pack_cell(raster, (2, -8, 10, 0))
        self.assertEqual(pair, (ink[0], ink[2] - ink[0]))

    def test_cell_write_keeps_every_other_packed_bit(self):
        plane_offset, plane, size = 64, 1536, 48
        index = 33
        tpl = bytearray(b"\xab" * (plane_offset + (index // 32 * size + size) * plane * 2))
        original = bytes(tpl)
        cell = Image.new("L", (size, size))
        cell.putpixel((0, 0), 255)
        punct._write_cell(tpl, plane_offset, index, cell)
        x, y = index % 32 * size, index // 32 * size
        changed = [offset for offset in range(plane_offset, len(original))
                   if tpl[offset] != original[offset]]
        # Only this cell's R nibbles move, and every written byte keeps its
        # packed top bits; nothing outside the cell changes.
        self.assertEqual(len(changed), size * size)
        for offset in changed:
            row, column = divmod((offset - plane_offset) // 2, plane)
            self.assertTrue(y <= row < y + size and x <= column < x + size)
            self.assertEqual(tpl[offset] & 0xF0, 0xAB & 0xF0)
        self.assertEqual(tpl[plane_offset + (y * plane + x) * 2], 0xAF)


class MetricPatchTests(unittest.TestCase):
    def setUp(self):
        self.source = bytes(0x200)
        self.image = bytes(self.source)
        self.manifest = {"source_sha256": project.digest(self.source), "patches": [
            {"file_offset": "0x18", "source_before": "0000", "after": "0306", "character": "."},
            {"file_offset": "0x2a", "source_before": "0102", "after": "0105", "character": "!"}]}
        self.image = bytearray(self.image)
        self.image[0x2A:0x2C] = b"\x01\x02"
        self.image = bytes(self.image)

    def test_apply_installs_and_rereads_every_pair(self):
        applied, manifest = punct.apply(self.image, self.manifest, source=self.source)
        self.assertEqual(applied[0x18:0x1A], b"\x03\x06")
        self.assertEqual(applied[0x2A:0x2C], b"\x01\x05")
        self.assertIs(manifest, self.manifest)

    def test_apply_refuses_a_changed_source_pair(self):
        image = bytearray(self.image)
        image[0x18:0x1A] = b"\x09\x09"
        with self.assertRaisesRegex(ValueError, "differs from the immutable original"):
            punct.apply(bytes(image), self.manifest, source=self.source)

    def test_apply_refuses_a_manifest_from_another_source(self):
        self.manifest["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "another source executable"):
            punct.apply(self.image, self.manifest, source=self.source)


class AtlasVerificationTests(unittest.TestCase):
    def build(self):
        plane_offset, size = 32, 48
        tpl = bytearray(plane_offset + 1536 * size * 2)
        tpl[12:16] = plane_offset.to_bytes(4, "big")
        index = 5
        cell = Image.new("L", (size, size))
        for x, y in ((10, 20), (10, 21), (11, 20)):
            cell.putpixel((x, y), 255)
        punct._write_cell(tpl, plane_offset, index, cell)
        ink = cell.getbbox()
        row = {"character": ".", "native_index": index, "metric_file_offset": 0x10,
               "a": ink[0], "b": ink[2] - ink[0], "ink_bounds": list(ink),
               "cell_sha256": project.digest(cell.tobytes())}
        image = bytearray(0x40)
        image[0x10:0x12] = bytes((row["a"], row["b"]))
        manifest = {"output_tpl_sha256": project.digest(bytes(tpl)), "glyphs": [row],
                    "advance_rule": "test"}
        return bytes(image), bytes(tpl), manifest

    def test_matching_pair_and_atlas_verify(self):
        image, tpl, manifest = self.build()
        report = punct.verify(image, tpl, manifest)
        self.assertEqual(report["verified_characters"], 1)

    def test_missing_metric_pair_is_rejected(self):
        image, tpl, manifest = self.build()
        broken = bytearray(image)
        broken[0x10] = 0
        with self.assertRaisesRegex(ValueError, "metric pair is absent"):
            punct.verify(bytes(broken), tpl, manifest)

    def test_changed_pixel_is_rejected(self):
        image, tpl, manifest = self.build()
        broken = bytearray(tpl)
        # one ink pixel inside the verified cell (index 5, cell column 240)
        broken[32 + (20 * 1536 + 240 + 10) * 2] = 0x00
        with self.assertRaisesRegex(ValueError, "atlas cell differs"):
            punct.verify(image, bytes(broken), manifest)

    def test_foreign_tpl_is_rejected(self):
        image, tpl, manifest = self.build()
        broken = bytearray(tpl)
        broken[32] = 0x0F  # a byte outside the one verified cell
        with self.assertRaisesRegex(ValueError, "supplied TPL differs"):
            punct.verify(image, bytes(broken), manifest)


if __name__ == "__main__":
    unittest.main()
