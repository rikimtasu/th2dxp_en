"""Synthetic packed-bit tests; no proprietary assets or runtime required."""
import copy
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_compound_punct_patch as compound


def texture():
    data = bytearray(44 + 2 * 48 * 48 * 2)
    struct.pack_into('>I', data, 0, 2)
    for record in range(2):
        at = 4 + record * 20
        struct.pack_into('>HHH', data, at, 48, 48, 96)
        data[at + 6] = 0xA3
        struct.pack_into('>I', data, at + 8, 44 + record * 4608)
    data[44:] = bytes([0xA5]) * (len(data) - 44)
    return bytes(data)


class CompoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        font, ofl = root / 'font.bin', root / 'OFL.txt'
        font.write_bytes(b'approved face')
        ofl.write_bytes(b'approved license')
        self.tpl = texture()
        folder = root / 'work/assets/fonts/_initial'
        folder.mkdir(parents=True)
        (folder / 'font.tpl').write_bytes(self.tpl)
        (folder / 'font1.tpl').write_bytes(self.tpl)
        source = bytearray(1024)
        # Real native_codes traversal: five main entries and one auxiliary entry.
        for i, code in enumerate((0x8140, 0x8141, 0xF040, 0xF041, 0xF04E)):
            struct.pack_into('>H', source, 300 + i * 2, code)
            struct.pack_into('>II', source, 100 + i * 8,
                             0x10000 + 300 + i * 2, 0x10000 + 300 + i * 2)
        struct.pack_into('>II', source, 200, 0x10000 + 304, 0x10000 + 304)
        self.source = bytes(source)
        specs = (('_initial/font.tpl', 100, 5, compound.project.digest(self.tpl)),
                 ('_initial/font1.tpl', 200, 1, compound.project.digest(self.tpl)))
        whitelist = tuple((u, c, t, index) for (u, c, t, _), index in
                          zip(compound.WHITELIST, (2, 3, 4)))
        patches = [patch.object(compound.project, 'ROOT', root),
                   patch.object(compound.native_layout_patch, 'SOURCE_SHA256', compound.project.digest(self.source)),
                   patch.object(compound.latin, 'FONT', font),
                   patch.object(compound.latin, 'OFL', ofl),
                   patch.object(compound.latin, 'FONT_SHA256', compound.project.digest(font.read_bytes())),
                   patch.object(compound.latin, 'OFL_SHA256', compound.project.digest(ofl.read_bytes())),
                   patch.object(compound.latin, 'METRICS_OFFSET', 500),
                   patch.object(compound.latin, 'raster_font', return_value=object()),
                   patch.object(compound.latin, 'raster_ink', side_effect=self.raster),
                   patch.object(compound.japanese, 'SPECS', specs),
                   patch.object(compound, 'WHITELIST', whitelist)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.inputs = {'_initial/font.tpl': self.tpl, '_initial/font1.tpl': self.tpl}

    @staticmethod
    def raster(font, char):
        # Distinct native quantized bounds, including low coverage removed at quantization.
        mask = Image.new('L', (5 if char == '!' else 8, 20), 220)
        mask.putpixel((0, 0), 2)
        return mask, (1, -20, 1 + mask.width, 0)

    def build(self):
        replacements, manifest = compound.substitute(self.source, self.inputs)
        image = compound.apply(self.source, manifest, source=self.source)
        return replacements, manifest, image

    def test_non_r_banks_metrics_and_preservation(self):
        replacements, manifest, image = self.build()
        proof = compound.verify(self.source, image, replacements, manifest)
        self.assertEqual(proof['verified_cells'], 4)
        self.assertEqual([row['channel'] for row in manifest['assets'][0]['glyphs']], ['B', 'A', 'R'])
        allowed = bytearray(len(self.tpl))
        expected = bytearray(self.tpl)
        for row in manifest['assets'][0]['glyphs']:
            index = row['native_index']
            cell = compound.japanese.read_cell(replacements[compound.MAIN], index)
            compound.japanese.write_cell(expected, index, cell, allowed)
            ink = cell.getbbox()
            self.assertEqual(row['metric_pair'], [ink[0], ink[2] - ink[0]])
            self.assertTrue(1 <= ink[0] < ink[2] <= 47)
            self.assertTrue(1 <= ink[1] < ink[3] <= 47)
        self.assertEqual(bytes(expected), replacements[compound.MAIN])
        self.assertFalse(any((a ^ b) & (255 ^ m) for a, b, m in
                             zip(self.tpl, replacements[compound.MAIN], allowed)))
        self.assertEqual(self.inputs[compound.MAIN], self.tpl)

    def test_header_and_unrelated_nibble_rejected(self):
        for offset, mask in ((23, 1), (44, 1)):
            with self.subTest(offset=offset):
                replacements, manifest, image = self.build()
                damaged = bytearray(replacements[compound.MAIN])
                damaged[offset] ^= mask
                replacements[compound.MAIN] = bytes(damaged)
                with self.assertRaises(ValueError):
                    compound.verify(self.source, image, replacements, manifest)

    def test_selected_cell_mutation_rejected(self):
        replacements, manifest, image = self.build()
        damaged = bytearray(replacements[compound.MAIN])
        cell = compound.japanese.read_cell(damaged, 2)
        cell.putpixel((20, 20), 17)
        compound.japanese.write_cell(damaged, 2, cell, bytearray(len(damaged)))
        replacements[compound.MAIN] = bytes(damaged)
        with self.assertRaises(ValueError):
            compound.verify(self.source, image, replacements, manifest)

    def test_metric_and_manifest_provenance_rejected(self):
        replacements, manifest, image = self.build()
        damaged = bytearray(image)
        damaged[504] ^= 1
        with self.assertRaises(ValueError):
            compound.verify(self.source, bytes(damaged), replacements, manifest)
        for field in ('font_sha256', 'ofl_sha256', 'source_sha256'):
            bad = copy.deepcopy(manifest)
            bad[field] = 'altered'
            with self.assertRaises(ValueError):
                compound.verify(self.source, image, replacements, bad)
        bad = copy.deepcopy(manifest)
        bad['patches'][0]['after'] = '0001'
        with self.assertRaises(ValueError):
            compound.apply(self.source, bad, source=self.source)

    def test_overflow_rejected_without_clipping(self):
        with patch.object(compound.latin, 'raster_ink',
                          return_value=(Image.new('L', (24, 20), 255), (0, -20, 24, 0))):
            with self.assertRaises(ValueError):
                compound.substitute(self.source, self.inputs)

    def test_required_main_and_source_font_provenance(self):
        with self.assertRaises(ValueError):
            compound.substitute(self.source, {'_initial/font1.tpl': self.tpl})
        original = compound.project.ROOT / 'work/assets/fonts/_initial/font.tpl'
        original.write_bytes(self.tpl + b'x')
        with self.assertRaises(ValueError):
            compound.substitute(self.source, self.inputs)


if __name__ == '__main__':
    unittest.main()
