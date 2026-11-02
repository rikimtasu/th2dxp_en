"""Rebuilt-payload proof for the staged English build, on synthetic data."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import project
import stage_english_build as stage


def record(text, suffix=""):
    raw = (text + suffix).encode("cp932")
    return b"\x02\x0B\x00\x0A" + struct.pack("<H", len(raw)) + raw


def payload(code):
    return b"VE\0\0" + struct.pack("<III", len(code), 0, 0) + code


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



class ApostropheCanonicalizationTests(unittest.TestCase):
    @staticmethod
    def item(text, original="翻訳", suffix=""):
        return {"kind": "text", "original_text": original,
                "translated_text": text, "control_suffix": suffix}

    def test_lexical_only_with_quotation_and_japanese_boundaries(self):
        text = "It’s can’t that‘s O’Brien rock’n’roll ‘It’s’ ‘word’ ’ 日本’語 日a’a本 1a’a a’a1"
        item = self.item(text, suffix=r"\k")
        changed = {"a.json": [{"items": [item]}]}
        counts = stage.canonicalize_english_apostrophes(changed)
        self.assertEqual(item["translated_text"],
                         "It's can't that's O'Brien rock'n'roll ‘It's’ ‘word’ ’ 日本’語 日a’a本 1a’a a’a1")
        self.assertEqual(counts, {"apostrophes": 7, "text_rows": 1, "scripts": 1})
        self.assertEqual(item["original_text"], "翻訳")
        self.assertEqual(item["control_suffix"], r"\k")
        self.assertEqual(stage.canonicalize_english_apostrophes(changed),
                         {"apostrophes": 0, "text_rows": 0, "scripts": 0})

    def test_controls_private_glyphs_and_untranslated_source_are_opaque(self):
        text = r"\p1234It’s\kcan’t<It’s>*nf1that’s" + "\ue001"
        items = [self.item(text), self.item("source’s", original="source’s"),
                 self.item("<", original="<"), self.item("control’s", original="control’s"),
                 self.item(">", original=">"), self.item("after’s"),
                 {"kind": "opcode_gap", "bytes": "020820"}]
        changed = {"a.json": [{"items": items}]}
        counts = stage.canonicalize_english_apostrophes(changed)
        self.assertEqual(items[0]["translated_text"],
                         r"\p1234It's\kcan't<It’s>*nf1that's" + "\ue001")
        self.assertEqual(project.engine_controls(items[0]["translated_text"]),
                         project.engine_controls(text))
        self.assertEqual(items[1]["translated_text"], "source’s")
        self.assertEqual(items[3]["translated_text"], "control’s")
        self.assertEqual(items[5]["translated_text"], "after's")
        self.assertEqual(counts, {"apostrophes": 4, "text_rows": 2, "scripts": 1})

    def test_mixed_word_chains_are_not_partially_normalized(self):
        text = "日rock’n’roll rock’n’roll日 a’b’1 1’a’b _a’b a’b_"
        item = self.item(text)
        self.assertEqual(stage.canonicalize_english_apostrophes({"a": [{"items": [item]}]}),
                         {"apostrophes": 0, "text_rows": 0, "scripts": 0})
        self.assertEqual(item["translated_text"], text)

    def test_rebuilt_comparison_uses_canonical_staged_text(self):
        kit = project.codec()
        data = payload(record("source", r"\k"))
        units = units_of(data, kit)
        text_item = next(item for unit in units for item in unit["items"] if item["kind"] == "text")
        text_item["translated_text"] = "It’s"
        changed = {"a.json": units}
        stage.canonicalize_english_apostrophes(changed)
        self.assertEqual(stage.expect_items("a.json", payload(record("It's", r"\k")), units, kit), 1)
        with self.assertRaisesRegex(ValueError, "text differs"):
            stage.expect_items("a.json", payload(record("It’s", r"\k")), units, kit)

class RubySuppressionTests(unittest.TestCase):
    @staticmethod
    def items(*texts):
        return [{"kind": "text", "original_text": text,
                 "translated_text": text, "control_suffix": ""} for text in texts]

    def test_suppresses_only_readings_in_changed_and_unchanged_scripts(self):
        first = self.items("Before", "<", "R32", ">", "reading", "<", "R0", ">", "base")
        second = self.items("<", "R11", ">", "・", "<", "R0", ">", "word")
        changed = {"a.json": [{"items": first}]}
        source = [{"items": second}]
        meta = {"entries": [{"json_filename": "a.json", "text_count": 1},
                            {"json_filename": "b.json", "text_count": 1}]}
        with patch.object(project, "load", return_value=source):
            self.assertEqual(stage.suppress_ruby(changed, meta), 2)
        self.assertEqual(first[4]["translated_text"], "")
        self.assertEqual(second[3]["translated_text"], "")
        self.assertEqual(first[8]["translated_text"], "base")
        self.assertEqual([first[i]["translated_text"] for i in (1, 2, 3, 5, 6, 7)],
                         ["<", "R32", ">", "<", "R0", ">"])
        self.assertEqual(first[4]["original_text"], "reading")
        self.assertIn("b.json", changed)

    def test_zero_length_reading_roundtrips_without_losing_following_text(self):
        kit = project.codec()
        texts = ("AB", "<", "R32", ">", "reading", "<", "R0", ">", "CD")
        original = payload(b"".join(record(text) for text in texts))
        units = units_of(original, kit)
        changed = {"a.json": units}
        meta = {"entries": [{"json_filename": "a.json", "text_count": len(texts)}]}
        stage.suppress_ruby(changed, meta)
        rebuilt = kit.rebuild_scenario_from_structured_json(
            original, units, encoding="cp932", font_table=None, allow_growth=True)
        actual = [item["original_text"] for unit in units_of(rebuilt, kit)
                  for item in unit["items"] if item["kind"] == "text"]
        self.assertEqual(actual, ["AB", "<", "R32", ">", "", "<", "R0", ">", "CD"])
        self.assertEqual(len(original) - len(rebuilt), len("reading"))

    def test_rejects_malformed_or_control_bearing_reading(self):
        meta = {"entries": [{"json_filename": "a.json", "text_count": 1}]}
        for texts in (("<", "R32", ">", "word", "<", "R1", ">"),
                      ("<", "R32", ">", r"word\k", "<", "R0", ">")):
            changed = {"a.json": [{"items": self.items(*texts)}]}
            with self.subTest(texts=texts), self.assertRaises(ValueError):
                stage.suppress_ruby(changed, meta)


class UIReplayCorrespondenceTests(unittest.TestCase):
    def setUp(self):
        self.image = bytes(stage.geninterface_latin.ALIAS_OFFSET + 95 * 2)
        self.native = {
            "ui_strings": {"file_offset": 80, "file_size": 20},
            "rx_extension": {"file_begin": 100, "file_end": 140},
            "patches": [{"file_offset": "0x14", "after": "00000000"}],
            "data_patches": [{"file_offset": "0x28", "after": "00000000"}],
        }

    def test_final_metrics_and_replayed_ui_must_match_even_when_scenarios_grow(self):
        stage.verify_ui_replay(self.image + b"scenario arena", self.image, self.native)
        for offset in (20, 40, 80, 100, stage.geninterface_latin.METRICS_OFFSET,
                       stage.geninterface_latin.ALIAS_OFFSET):
            final = bytearray(self.image)
            final[offset] = 1
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "differs from UI replay"):
                stage.verify_ui_replay(bytes(final), self.image, self.native)

    def test_missing_final_font_mapping_is_not_a_correspondence_pass(self):
        with self.assertRaisesRegex(ValueError, "differs from UI replay"):
            stage.verify_ui_replay(self.image[:1000], self.image, self.native)


class JapaneseArchiveInputsTests(unittest.TestCase):
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
