"""Synthetic Message-JSON conversion/identity tests; no game or GUI needed."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import project
import linguagacha_export as export


def text(original, suffix=""):
    return {"kind": "text", "original_text": original, "translated_text": original,
            "control_suffix": suffix, "length": len(original.encode("cp932")), "editable": True}


class LinguaGachaExportTests(unittest.TestCase):
    def setUp(self):
        self.units = [
            {"end_reason": "terminal_control", "items": [
                text("未完の", ""), text("続き。*nnk\\k<S10>", "\\k\\n"),
                {"kind": "control_text", "control": "\\p0001", "length": 6, "editable": False}]},
            {"end_reason": "opcode_gap", "items": [text("", "\\k"), text("同じ"), text("同じ"),
                {"kind": "opcode_gap", "bytes": "020820", "length": 3, "editable": False}]},
        ]

    def view(self, script="script_0000.json", native="010301000", domains=None, kind="message", units=None):
        return {"script": script, "parent_script": "script_0000.json", "native_name": native,
                "kind": kind, "story_domains": ["base_game"] if domains is None else domains,
                "source_payload_sha256": "fixture", "baseline_json_sha256": "fixture",
                "ownership_status": "base_game", "units": self.units if units is None else units}

    def test_original_only_and_exact_fragment_blank_duplicate_roundtrip(self):
        rows, mapping = export.make_rows(self.units, "script_0000.json")
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(set(row) == {"name", "message"} and row["name"] == "" for row in rows))
        self.assertEqual(rows[2]["message"], "")
        self.assertEqual(rows[3], rows[4])
        self.assertEqual(mapping[1]["record_id"], "script_0000.json:0:1")
        self.assertEqual(mapping[1]["control_suffix"], "\\k\\n")
        self.assertEqual(export.restore_units(self.units, rows, "script_0000.json"), self.units)
        edited = copy.deepcopy(self.units)
        edited[0]["items"][0]["translated_text"] = "Not original Japanese"
        self.assertEqual(export.make_rows(edited, "script_0000.json")[0][0]["message"], "未完の")

    def test_import_rejects_count_name_controls_blanks_and_private_glyph_changes(self):
        original, _ = export.make_rows(self.units, "fixture.json")
        cases = []
        rows = copy.deepcopy(original); rows.pop(); cases.append((rows, "row count"))
        rows = copy.deepcopy(original); rows[0]["name"] = "Guessed"; cases.append((rows, "speaker"))
        rows = copy.deepcopy(original); rows[1]["message"] = "続き。*nnk<S10>"; cases.append((rows, "controls"))
        rows = copy.deepcopy(original); rows[2]["message"] = "Invented"; cases.append((rows, "blank carrier"))
        rows = copy.deepcopy(original); rows[0]["message"] = ""; cases.append((rows, "deleted"))
        rows = copy.deepcopy(original); rows[1]["message"] = "続き。*nnk\\k<S10>"; cases.append((rows, "private glyph"))
        for rows, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                export.restore_units(self.units, rows, "fixture.json")

    def test_strict_cp932_and_schema(self):
        rows, _ = export.make_rows(self.units, "fixture.json")
        rows[0]["message"] = "\u301c"
        with self.assertRaisesRegex(ValueError, "round-trip"):
            export.restore_units(self.units, rows, "fixture.json")
        rows[0]["message"] = "a\nb"
        with self.assertRaisesRegex(ValueError, "literal control"):
            export.restore_units(self.units, rows, "fixture.json")
        rows[0]["message"] = 123
        with self.assertRaisesRegex(ValueError, "must be a string"):
            export.restore_units(self.units, rows, "fixture.json")

    def test_atomic_flat_sets_choices_sidecars_and_no_empty_array_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "export"
            choice = [{"items": [text("選ぶ？")], "end_reason": "native_choice_operand"}]
            empty = [{"items": [{"kind": "control_text", "control": "\\p0001"}]}]
            views = [self.view(), self.view("script_0000_choices.json", kind="choice", units=choice),
                     self.view("script_0001.json", "020101000", ["anotherdays"]),
                     self.view("script_0002.json", "control_only", units=empty)]
            result = export.write_export(target, views, {"source": "synthetic"})
            self.assertEqual(result["counts"]["all-original"]["text_items"], 11)
            self.assertEqual(result["counts"]["base-game"]["text_items"], 6)
            self.assertEqual(result["counts"]["all-original"]["json_files"], 3)
            self.assertEqual(len(result["empty_views_not_exported"]), 1)
            self.assertTrue((target / "base-game/gt_input/010301000_choices.json").is_file())
            self.assertFalse((target / "all-original/gt_input/control_only.json").exists())
            rows = project.load(target / "all-original/gt_input/010301000.json")
            self.assertEqual(export.restore_units(self.units, rows, "script_0000.json"), self.units)
            with self.assertRaisesRegex(ValueError, "Existing export preserved"):
                export.write_export(target, [], {})

    def test_bad_or_duplicate_native_name_never_publishes_partial_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "export"
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                export.write_export(target, [self.view(native="../outside")], {})
            self.assertFalse(target.exists())
            with self.assertRaisesRegex(ValueError, "colliding"):
                export.write_export(target, [self.view(), self.view()], {})
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
