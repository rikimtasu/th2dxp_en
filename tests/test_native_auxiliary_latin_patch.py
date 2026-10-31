"""Synthetic source-index/pixel preservation for the auxiliary-font Latin extension."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_auxiliary_latin_patch as auxiliary
import native_japanese_font_patch as japanese
import native_typography_smoke


def atlas(width=1536, height=96):
    raw = bytearray(128 + width * height * 2)
    struct.pack_into('>I', raw, 0, 1)
    struct.pack_into('>HHHBBI4H', raw, 4, height, width, width * 2, 0xa3, 1, 128, 1, 1, 1, 1)
    return raw


def painted(codes, width=1536, height=96):
    """Atlas carrying one distinct cell per code, plus a bit-writable mask."""
    raw = atlas(width, height)
    allowed = bytearray(len(raw))
    for index in range(len(codes)):
        cell = Image.new('L', (48, 48))
        cell.paste(170, (3 + index % 5, 4, 25, 40))
        japanese.write_cell(raw, index, cell, allowed)
    return raw


class AliasExtensionTests(unittest.TestCase):
    def test_contiguous_ranges_retain_order_without_merging_gaps(self):
        self.assertEqual(auxiliary.contiguous_ranges([0x8165, 0x8166, 0x8260, 0x8261, 0x8281]),
                         [(0x8165, 0x8166), (0x8260, 0x8261), (0x8281, 0x8281)])
        self.assertEqual(auxiliary.contiguous_ranges([]), [])

    def test_auxiliary_fonts_own_distinct_hooks_and_lookup_allocations(self):
        self.assertEqual([auxiliary.FONTS[font]['hook'] for font in (1, 2, 3)],
                         [0x118D4, 0x11968, 0x119FC])
        self.assertEqual([auxiliary.FONTS[font]['continue'] for font in (1, 2, 3)],
                         [0x118D8, 0x1196C, 0x11A00])
        self.assertEqual([auxiliary.FONTS[font]['table'] for font in (1, 2, 3)],
                         [0x24702C, 0x247030, 0x247034])
        self.assertEqual([auxiliary.FONTS[font]['tpl'] for font in (1, 2, 3)],
                         ['_initial/font1.tpl', '_initial/font2.tpl', '_initial/font3.tpl'])

    def test_latin_aliases_append_without_reindexing_or_redrawing_original_cells(self):
        original = [0x8140, 0x8148] + list(range(0x9000, 0x9000 + 135))
        extra = [int.from_bytes(char.encode('cp932'), 'big') for char in '‘’“”'] + [0x8260, 0x8261]
        codes = original + extra
        source = bytearray(64)
        struct.pack_into('>I', source, 32, 1104)
        main, old = atlas(), atlas()
        allowed = bytearray(len(main))
        for index in range(len(codes)):
            cell = Image.new('L', (48, 48))
            cell.paste(170, (3 + index % 5, 4, 25, 40))
            japanese.write_cell(main, index, cell, allowed)
        original_bits = bytearray(len(old))
        for index in range(len(original)):
            japanese.write_cell(old, index, japanese.read_cell(main, index), original_bits)
        aliases = {'A': (0x8260, 137), 'B': (0x8261, 138), '?': (0x8148, 1)}
        with patch.dict(auxiliary.FONTS[1], {'table': 32}):
            with patch.object(japanese, 'native_codes', side_effect=[original, codes]):
                with patch.object(auxiliary.geninterface_latin, 'aliases', return_value=aliases):
                    result, report = auxiliary.extend_atlas(bytes(source), bytes(main), bytes(old))
        self.assertEqual(report['original_glyphs'], 137)
        self.assertEqual(report['added_glyphs'], 6)
        self.assertEqual(report['codes'][:137], original)
        self.assertEqual(report['old_range_count'], 137)
        for index in range(137):
            self.assertEqual(japanese.read_cell(result, index).tobytes(), japanese.read_cell(old, index).tobytes())
        for index, code in enumerate(report['codes'][137:], 137):
            self.assertEqual(japanese.read_cell(result, index).tobytes(),
                             japanese.read_cell(main, codes.index(code)).tobytes())
        for index in range(len(report['codes']), 256):
            self.assertEqual(japanese.read_cell(result, index).tobytes(), japanese.read_cell(old, index).tobytes())

    def test_explicit_subset_extends_only_the_requested_second_font_codes(self):
        original = [0x8140] + list(range(0x9000, 0x9000 + 202))
        codes = original + [0x8260, 0x8261]
        source = bytearray(64)
        struct.pack_into('>I', source, 32, (203 + 1) * 8)
        main, old = painted(codes), painted(original)
        with patch.dict(auxiliary.FONTS[3], {'table': 32}):
            with patch.object(japanese, 'native_codes', side_effect=[original, codes]):
                result, report = auxiliary.extend_atlas(
                    bytes(source), bytes(main), bytes(old), font=3, codes={0x8260, 0x8261})
        self.assertEqual(report['font'], 3)
        self.assertEqual(report['tpl'], '_initial/font3.tpl')
        self.assertEqual(report['old_range_count'], 203)
        self.assertEqual(report['added_glyphs'], 2)
        self.assertEqual(report['added_ranges'], [(0x8260, 0x8261)])
        for index in range(203):
            self.assertEqual(japanese.read_cell(result, index).tobytes(),
                             japanese.read_cell(old, index).tobytes())
        for index in (203, 204):
            self.assertEqual(japanese.read_cell(result, index).tobytes(),
                             japanese.read_cell(main, index).tobytes())

    def test_requested_codes_beyond_the_texture_banks_fail_closed(self):
        original = [0x8140] + list(range(0x9000, 0x9000 + 202))
        source = bytearray(64)
        struct.pack_into('>I', source, 32, (203 + 1) * 8)
        main, old = painted(original), painted(original)
        requested = set(range(0x8300, 0x8300 + 60))
        with patch.dict(auxiliary.FONTS[3], {'table': 32}):
            with patch.object(japanese, 'native_codes', side_effect=[original, original]):
                with self.assertRaisesRegex(ValueError, 'four texture banks hold 256 cells'):
                    auxiliary.extend_atlas(bytes(source), bytes(main), bytes(old),
                                           font=3, codes=requested)

    def test_unknown_executable_is_rejected_before_asset_processing(self):
        with self.assertRaisesRegex(ValueError, 'pinned source executable'):
            auxiliary.apply(bytes(64), b'', b'', {}, source=bytes(64))

    def test_counter_read_uses_actual_cpu_counter_without_clobbering_state(self):
        cpu = object.__new__(native_typography_smoke.GlyphCPU)
        cpu.pc, cpu.steps, cpu.executed = 4, 0, set()
        cpu.code, cpu.r, cpu.ctr = {4: ('mfctr', 'r12')}, [0] * 32, 0x12345678
        cpu.step()
        self.assertEqual(cpu.r[12], 0x12345678)
        self.assertEqual(cpu.ctr, 0x12345678)
        self.assertEqual(cpu.pc, 8)
        self.assertEqual(cpu.executed, {4})


if __name__ == '__main__':
    unittest.main()
