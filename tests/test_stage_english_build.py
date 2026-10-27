"""Rebuilt-payload proof for the staged English build, on synthetic data."""
from pathlib import Path
import struct
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
