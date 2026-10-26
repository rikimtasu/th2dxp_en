"""Synthetic glyph masks: readability is geometry, not particular wording."""
from collections import defaultdict
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ui_graphics


def atlas():
    font = ui_graphics.LatinAtlas.__new__(ui_graphics.LatinAtlas)
    font.default_weight = 3
    font.glyphs = {chr(byte): (Image.new("L", (32, 48), 255), 36)
                   for byte in range(65, 91)}
    font.glyphs[" "] = Image.new("L", (20, 48)), 20
    dash = Image.new("L", (20, 48))
    ImageDraw.Draw(dash).rectangle((0, 22, 19, 25), fill=255)
    font.glyphs["-"] = dash, 36
    return font


class ReadableGraphicTests(unittest.TestCase):
    def test_words_wrap_without_condensation_or_fragments(self):
        result = atlas().mask("ONE TWO", (100, 80), height=24, weight=1, minimum=14)
        self.assertEqual(result.info["ui_layout"]["lines"], ["ONE", "TWO"])
        self.assertEqual(result.getbbox()[3] - result.getbbox()[1], 50)
        self.assertFalse(result.info["ui_layout"]["horizontal_compression"])

    def test_hyphen_retains_font_scale_instead_of_becoming_a_wide_capital(self):
        result = atlas().line("-", 24, 100, weight=1)
        self.assertEqual(result.size, (10, 2))
        self.assertEqual(result.getbbox(), (0, 0, 10, 2))

    def test_unreadable_cell_fails_instead_of_squashing_or_shortening(self):
        with self.assertRaisesRegex(ValueError, "Uncompressed UI text"):
            atlas().line("LONGWORD", 24, 12, weight=1)
        with self.assertRaisesRegex(ValueError, "larger native cell"):
            atlas().mask("LONGWORD", (8, 20), height=24, minimum=14, weight=1)

    def test_explicit_mapping_uses_its_advances_and_preserves_descenders_and_punctuation(self):
        glyphs = {chr(byte): (Image.new("L", (1, 48)), 7)
                  for byte in range(0x20, 0x7F)}
        for char, width, top, bottom in [("A", 4, 5, 30), ("g", 5, 17, 44), ("-", 3, 22, 23)]:
            mask = Image.new("L", (width, 48))
            ImageDraw.Draw(mask).rectangle((0, top, width - 1, bottom), fill=255)
            glyphs[char] = mask, width + 6
        # No original ELF/atlas is needed for an explicit mapping; neither its
        # widths nor its baseline may accidentally leak into selected-font text.
        font = ui_graphics.LatinAtlas(b"", glyphs=glyphs)
        result = font.line("Ag-", 48, 24, weight=1)
        self.assertEqual(result.size, (24, 40))
        self.assertEqual(result.getpixel((5, 20)), 0)
        self.assertEqual(result.getpixel((10, 39)), 255)
        self.assertEqual(result.getpixel((21, 17)), 255)
        self.assertEqual(font.line("-", 24, 100, weight=1).size, (2, 1))
        with self.assertRaisesRegex(ValueError, "Uncompressed UI text"):
            font.line("Ag-", 48, 23, weight=1)

    def test_gen_regular_provenance_disables_only_default_artificial_bold(self):
        class Mapping(dict):
            provenance = {"face": "Gen Interface JP Regular"}

        glyphs = Mapping({chr(byte): (Image.new("L", (12, 48)), 18)
                          for byte in range(0x20, 0x7F)})
        ImageDraw.Draw(glyphs["A"][0]).rectangle((3, 12, 8, 35), fill=255, width=1)
        selected = ui_graphics.LatinAtlas(b"", glyphs=glyphs)
        original_convention = ui_graphics.LatinAtlas(b"", glyphs=dict(glyphs))
        self.assertEqual(selected.default_weight, 1)
        self.assertEqual(original_convention.default_weight, 3)
        self.assertEqual(selected.line("A", 48, 30).size, (6, 24))
        self.assertEqual(original_convention.line("A", 48, 30).size, (8, 26))
        self.assertEqual(selected.line("A", 48, 30, weight=3).tobytes(),
                         original_convention.line("A", 48, 30).tobytes())
        layout = ui_graphics.paint(Image.new("L", (30, 30)),
                                   {"id": "test", "rect": [0, 0, 30, 30],
                                    "english": "A", "height": 24}, selected)
        self.assertEqual(layout["stroke_filter"], 1)

    def test_padding_fits_uniformly_without_truncation(self):
        result = atlas().mask("ONE", (55, 30), height=24, weight=1, padding=3)
        layout = result.info["ui_layout"]
        self.assertLess(layout["font_pixels"], 24)
        self.assertEqual(layout["lines"], ["ONE"])
        self.assertEqual(layout["padding"], 3)
        self.assertFalse(layout["horizontal_compression"])
        for x, y, width, height in layout["line_boxes"]:
            self.assertGreaterEqual(x, 3)
            self.assertGreaterEqual(y, 3)
            self.assertLessEqual(x + width, 52)
            self.assertLessEqual(y + height, 27)

    def test_next_paints_only_padded_source_lettering_interior(self):
        inventory = {"readable_layout": {"legend_cells": defaultdict(lambda: [0, 0, 64, 24])}}
        with patch.object(ui_graphics.project, "load", return_value=inventory):
            labels = ui_graphics.editorial_labels()
        next_labels = [label for label in labels if label["id"].startswith("general.button.next.")]
        self.assertEqual(len(next_labels), 4)
        glyphs = {chr(byte): (Image.new("L", (20, 48)), 26)
                  for byte in range(0x20, 0x7F)}
        for char in "Next":
            ImageDraw.Draw(glyphs[char][0]).rectangle((0, 12, 19, 35), fill=255)
        font = ui_graphics.LatinAtlas(b"", glyphs=glyphs)
        for label in next_labels:
            self.assertEqual(label["rect"], [145, 57, 190, 78])
            self.assertEqual(label["height"], 18)
            image = Image.new("L", (240, 96))
            ImageDraw.Draw(image).rounded_rectangle((104, 48, 199, 85), radius=10,
                                                     outline=255, width=3)
            before = image.copy()
            layout = ui_graphics.paint(image, label, font)
            self.assertEqual(layout["lines"], ["Next"])
            self.assertEqual(layout["padding"], 3)
            left, top, right, bottom = ImageChops.difference(before, image).getbbox()
            self.assertGreaterEqual(left, 145)
            self.assertGreaterEqual(top, 57)
            self.assertLessEqual(right, 190)
            self.assertLessEqual(bottom, 78)
        # Perspective, source cells, and nominal map/footer font sizes remain
        # native; readability is improved through the selected stroke policy.
        self.assertTrue(all(label["height"] == 24 for label in labels if label["id"].startswith("map.")))
        self.assertTrue(all(label["height"] == 20 for label in labels if label["id"].startswith("general.legend.")))


if __name__ == "__main__":
    unittest.main()
