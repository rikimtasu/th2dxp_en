"""Synthetic Japanese glyph coverage, placement, banks and guarded metric edits."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_japanese_font_patch as jp


def tpl(records=2, columns=1, rows=1):
    width, height = columns * 48, rows * 48
    size = width * height * 2
    data = bytearray(b'\xa5' * (128 + records * size))
    struct.pack_into('>I', data, 0, records)
    for index in range(records):
        struct.pack_into('>HHHBBI4H', data, 4 + index * 20,
                         height, width, width * 2, 0xa3, 1, 128 + index * size, 1, 1, 1, 1)
    return bytes(data)


class JapaneseSetTests(unittest.TestCase):
    def test_japanese_letters_and_punctuation_are_selected(self):
        for char in 'あがっアガッ日本語愛佳郁乃々ー「」、。':
            self.assertTrue(jp.japanese(char), char)

    def test_latin_private_icons_and_space_are_retained(self):
        for char in 'A0!？☆ΩЖ \ue000\ue001￥':
            self.assertFalse(jp.japanese(char), char)

    def test_unicode_cmap_does_not_claim_notdef_as_coverage(self):
        data = bytearray(128)
        struct.pack_into('>H', data, 4, 1)
        struct.pack_into('>4sIII', data, 12, b'cmap', 0, 28, 100)
        struct.pack_into('>HHHHI', data, 28, 0, 1, 3, 10, 12)
        struct.pack_into('>HHIII', data, 40, 12, 0, 40, 0, 2)
        struct.pack_into('>III', data, 56, 0x3041, 0x3043, 0)
        struct.pack_into('>III', data, 68, 0x65e5, 0x65e5, 12)
        self.assertEqual(jp.unicode_glyphs(bytes(data)), {0x3042, 0x3043, 0x65e5})

    def test_missing_unicode_table_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cmap'):
            jp.unicode_glyphs(bytes(32))

    def test_source_ranges_keep_index_order_and_exact_count(self):
        source = bytearray(256)
        struct.pack_into('>II', source, 32, 0x10080, 0x10082)
        struct.pack_into('>HH', source, 128, 0x8140, 0x8142)
        self.assertEqual(jp.native_codes(source, 32, 3), [0x8140, 0x8141, 0x8142])
        with self.assertRaisesRegex(ValueError, 'inventory'):
            jp.native_codes(source, 32, 2)
        with self.assertRaisesRegex(ValueError, 'count'):
            jp.native_codes(source, 32, 4)


class JapanesePlacementTests(unittest.TestCase):
    def test_voicing_marks_fit_without_per_character_shifts(self):
        raster = Image.new('L', (41, 40), 200)
        cell, where = jp.pack_cell(raster, (3, -39, 44, 1))
        self.assertEqual(where, (4, 1))
        self.assertEqual(cell.getbbox(), (4, 1, 45, 41))
        self.assertTrue(all(value % 17 == 0 for value in cell.tobytes()))

    def test_corner_bracket_keeps_the_faces_own_side_bearing(self):
        cell, where = jp.pack_cell(Image.new('L', (14, 29), 255), (22, -38, 36, -9))
        self.assertEqual(where, (23, 2))
        self.assertEqual(cell.getbbox()[0], 23)

    def test_overflow_is_rejected_not_clipped_or_squeezed(self):
        for bounds in ((0, -40, 42, 3), (0, -39, 47, 3), (0, -39, 42, 8)):
            with self.subTest(bounds=bounds):
                raster = Image.new('L', (bounds[2] - bounds[0], bounds[3] - bounds[1]), 255)
                with self.assertRaisesRegex(ValueError, 'clipping'):
                    jp.pack_cell(raster, bounds)

    def test_quantized_empty_ink_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no quantized ink'):
            jp.pack_cell(Image.new('L', (4, 4), 1), (3, -4, 7, 0))


class PackedBankTests(unittest.TestCase):
    def test_all_eight_banks_preserve_the_other_three_channels(self):
        original = tpl()
        cell = Image.new('L', (48, 48))
        cell.putpixel((3, 4), 255)
        for bank, (byte, shift) in enumerate(jp.CHANNELS * 2):
            with self.subTest(bank=bank):
                output, allowed = bytearray(original), bytearray(len(original))
                jp.write_cell(output, bank, cell, allowed)
                self.assertEqual(jp.read_cell(output, bank).tobytes(), cell.tobytes())
                record = bank // 4
                at = 128 + record * 48 * 48 * 2 + (4 * 48 + 3) * 2 + byte
                self.assertEqual((output[at] >> shift) & 15, 15)
                self.assertFalse(any((a ^ b) & (255 ^ mask)
                                     for a, b, mask in zip(original, output, allowed)))
                for other in range(8):
                    if other != bank:
                        self.assertEqual(jp.read_cell(output, other).tobytes(),
                                         jp.read_cell(original, other).tobytes())

    def test_bank_transition_uses_atlas_cell_count_not_main_font_constant(self):
        original = tpl(columns=2, rows=2)
        self.assertEqual(jp.slot(original, 3)[:4], (0, 0, 48, 48))
        self.assertEqual(jp.slot(original, 4)[:4], (0, 1, 0, 0))
        self.assertEqual(jp.slot(original, 16)[:4], (1, 0, 0, 0))

    def test_rectangular_auxiliary_atlas_uses_height_then_width(self):
        original = tpl(columns=32, rows=2)
        self.assertEqual(jp.slot(original, 63)[:4], (0, 0, 1488, 48))
        self.assertEqual(jp.slot(original, 64)[:4], (0, 1, 0, 0))

    def test_out_of_bank_indices_are_rejected(self):
        for index in (-1, 8):
            with self.assertRaisesRegex(ValueError, 'index'):
                jp.slot(tpl(), index)


class MetricPatchTests(unittest.TestCase):
    def test_exact_manifest_and_original_pair_are_required(self):
        source = bytes(64)
        manifest = {'patches': [{'file_offset': '0x10', 'source_before': '0000', 'after': '032a'}]}
        with patch.object(jp, 'substitute', return_value=({}, manifest)):
            result = jp.apply(source, manifest, source=source)
            self.assertEqual(result[:16], source[:16])
            self.assertEqual(result[16:18], b'\x03\x2a')
            self.assertEqual(result[18:], source[18:])
            with self.assertRaisesRegex(ValueError, 'source metric pair'):
                jp.apply(result, manifest, source=source)
            with self.assertRaisesRegex(ValueError, 'manifest'):
                jp.apply(source, {'patches': []}, source=source)

    def test_verifier_rejects_rebased_or_missing_pixels(self):
        with patch.object(jp, 'substitute', return_value=({'font': b'expected'}, {'assets': []})):
            with self.assertRaisesRegex(ValueError, 'pixels/manifest'):
                jp.verify(bytes(1), bytes(1), {'font': b'foreign'}, {'assets': []})


if __name__ == '__main__':
    unittest.main()
