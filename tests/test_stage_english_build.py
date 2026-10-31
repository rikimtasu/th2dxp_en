"""Rebuilt-payload proof for the staged English build, on synthetic data."""
from pathlib import Path
import struct
import sys
import unittest
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import project
import stage_english_build as stage


def record(text, suffix=""):
    raw = (text + suffix).encode("cp932")
    return b"\x02\x0B\x00\x0A" + struct.pack("<H", len(raw)) + raw


def payload(code):
    return b"VE" + struct.pack("<I", len(code)) + struct.pack("<I", 0) + b"\0" * 8 + code


def units_of(data, kit):
    return kit.make_structured_units(
        data, kit.read_text_records_structured(data, "cp932", None),
        include_offsets=False, encoding="cp932", font_table=None, decode_gaps=False)


class PayloadProofTests(unittest.TestCase):
    def setUp(self):
        self.kit = project.codec()
        self.code = (record("Hello") + b"\x02\x08\x20" + record("a cafe") + record("tail", "\k"))
        self.data = payload(self.code)
        self.units = units_of(self.data, self.kit)

    def translate(self, *texts):
        view = []
        index = 0
        for unit in self.units:
            clone = {"end_reason": unit["end_reason"], "items": []}
            for item in unit["items"]:
                item = dict(item)
                if item["kind"] == "text":
                    item["translated_text"] = texts[index]
                    index += 1
                clone["items"].append(item)
            view.append(clone)
        return view

    def test_matching_translation_is_accepted(self):
        view = self.translate("Hello", "a cafe", "tail")
        self.assertEqual(stage.expect_items("script_0000.json", self.data, view, self.kit), 3)

    def test_trailing_control_may_arrive_inside_translation(self):
        view = self.translate("Hello", "a cafe", "tail")
        view[1]["items"][1]["translated_text"] = "tail\k"
        view[1]["items"][1]["control_suffix"] = ""
        self.assertEqual(stage.full_text(view[1]["items"][1]), "tail\k")
        self.assertEqual(stage.expect_items("script_0000.json", self.data, view, self.kit), 3)

    def test_missing_translation_is_rejected(self):
        view = self.translate("Hello", "a cafe", "wrong tail")
        with self.assertRaisesRegex(ValueError, "text differs"):
            stage.expect_items("script_0000.json", self.data, view, self.kit)

    def test_changed_bytecode_gap_is_rejected(self):
        view = self.translate("Hello", "a cafe", "tail")
        gap = view[0]["items"][1]
        self.assertEqual(gap["bytes"], "020820")
        gap["bytes"] = "020821"
        with self.assertRaisesRegex(ValueError, "bytecode/control changed"):
            stage.expect_items("script_0000.json", self.data, view, self.kit)

    def test_choice_parent_gap_may_change_for_spliced_caption(self):
        view = self.translate("Hello", "a cafe", "tail")
        view[0]["items"][1]["bytes"] = "0a03010203"
        self.assertEqual(stage.expect_items("script_0000.json", self.data, view, self.kit,
                                            choice_parent=True), 3)

    def test_item_count_change_is_rejected(self):
        view = self.translate("Hello", "a cafe", "tail")
        view.append({"end_reason": "eof", "items": [dict(view[0]["items"][0])]})
        with self.assertRaisesRegex(ValueError, "items for"):
            stage.expect_items("script_0000.json", self.data, view, self.kit)


class JapaneseArchiveInputsTests(unittest.TestCase):
    def test_explicit_original_is_forwarded_with_all_four_font_replacements(self):
        import ui_archive
        import ui_probe
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'original.sdat'
            source.write_bytes(b'read-only synthetic original')
            graphics = {'latin_font': {'output_tpl_sha256': 'latin', 'source_tpl_sha256': 'source'}}
            replacements = {'_initial/font.tpl': b'jp0', '_initial/font1.tpl': b'jp1',
                            '_initial/font2.tpl': b'jp2', '_initial/font3.tpl': b'jp3'}
            applied = {'punct_manifest': {'base_output_tpl_sha256': 'latin', 'base_tpl_sha256': 'source',
                                          'output_tpl_sha256': 'punct'},
                       'font_tpl': b'jp0',
                       'japanese_manifest': {'base_punctuation_tpl_sha256': 'punct'},
                       'japanese_replacements': replacements}
            with patch.object(ui_probe, 'graphics_inputs', return_value=({}, graphics)):
                with patch.object(ui_archive, 'stage', return_value={'verified': True}) as pack:
                    result, actual_graphics = stage.stage_archive(Path(temporary) / 'out', applied,
                                                                   source_sdat=source)
            self.assertEqual(result, {'verified': True})
            self.assertIs(actual_graphics, graphics)
            pack.assert_called_once_with(replacements, Path(temporary) / 'out/assets', source_sdat=source)
            self.assertEqual(source.read_bytes(), b'read-only synthetic original')

    def test_foreign_japanese_base_is_not_staged(self):
        import ui_archive
        import ui_probe
        graphics = {'latin_font': {'output_tpl_sha256': 'latin', 'source_tpl_sha256': 'source'}}
        applied = {'punct_manifest': {'base_output_tpl_sha256': 'latin', 'base_tpl_sha256': 'source',
                                      'output_tpl_sha256': 'punct'},
                   'font_tpl': b'jp', 'japanese_manifest': {'base_punctuation_tpl_sha256': 'foreign'},
                   'japanese_replacements': {}}
        with patch.object(ui_probe, 'graphics_inputs', return_value=({}, graphics)):
            with patch.object(ui_archive, 'stage') as pack:
                with self.assertRaisesRegex(ValueError, 'not chained'):
                    stage.stage_archive(Path('build/new'), applied)
                pack.assert_not_called()


class AuxiliarySubsetTests(unittest.TestCase):
    """font3 can only hold the aliases its G3 spans actually draw."""

    def aliases(self):
        return {'A': (0x8260, 0), 'b': (0x8261, 1), 'C': (0x8262, 2),
                'k': (0x8263, 3), 'x': (0x8264, 4), 'y': (0x8265, 5),
                ' ': (0x8140, 6)}

    def test_only_the_requested_font_spans_contribute_codes(self):
        scripts = {'script_0001.json': [{'items': [
            {'kind': 'text', 'original_text': '<', 'translated_text': '<'},
            {'kind': 'text', 'original_text': 'G3', 'translated_text': 'G3'},
            {'kind': 'text', 'original_text': '>', 'translated_text': '>'},
            {'kind': 'text', 'original_text': 'Ab', 'translated_text': 'Ab'},
            {'kind': 'text', 'original_text': '<', 'translated_text': '<'},
            {'kind': 'text', 'original_text': 'G2', 'translated_text': 'G2'},
            {'kind': 'text', 'original_text': '>', 'translated_text': '>'},
            {'kind': 'text', 'original_text': 'CC', 'translated_text': 'CC'},
            {'kind': 'text', 'original_text': '<', 'translated_text': '<'},
            {'kind': 'text', 'original_text': 'G0', 'translated_text': 'G0'},
            {'kind': 'text', 'original_text': '>', 'translated_text': '>'},
            {'kind': 'text', 'original_text': 'A', 'translated_text': 'A'},
        ]}]}
        with patch.object(stage.geninterface_latin, 'aliases', return_value=self.aliases()):
            codes = stage.auxiliary_latin_codes(scripts, b'source', 3)
        self.assertEqual(codes, {0x8260, 0x8261})

    def test_inline_tags_and_backslash_controls_are_stripped_before_lookup(self):
        scripts = {'script_0001.json': [{'items': [
            {'kind': 'text', 'original_text': 'x<G3>y', 'translated_text': 'x\\ky'},
        ]}]}
        with patch.object(stage.geninterface_latin, 'aliases', return_value=self.aliases()):
            codes = stage.auxiliary_latin_codes(scripts, b'source', 3)
        self.assertEqual(codes, {0x8264, 0x8265})


if __name__ == "__main__":
    unittest.main()
