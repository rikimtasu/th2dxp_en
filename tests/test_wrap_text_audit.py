import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import wrap_text_audit


def text(value, suffix=""):
    return {"kind": "text", "translated_text": value, "control_suffix": suffix}


class WrapTextAuditTests(unittest.TestCase):
    def test_finds_sentence_boundary_and_reports_split_word_as_candidate(self):
        items = [text("stand"), text("ing in place."), text("She says hi.")]
        rows = wrap_text_audit.scan_unit("script.json", 13, items)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["category"], "sentence_spacing")
        self.assertEqual((rows[0]["left_item"], rows[0]["right_item"]), (1, 2))
        self.assertTrue(rows[0]["across_fragments"])
        self.assertEqual(rows[1]["category"], "joined_word_boundary")

    def test_ellipsis_is_not_a_sentence_spacing_candidate(self):
        self.assertEqual(wrap_text_audit.scan_unit("script.json", 0, [text("...Huh?")]), [])

    def test_native_controls_and_gaps_end_contiguous_runs(self):
        items = [text("Hi.", "\\k\\n"), text("She left."),
                 {"kind": "opcode_gap"}, text("Again.")]
        self.assertEqual(wrap_text_audit.scan_unit("script.json", 0, items), [])

    def test_internal_and_cross_fragment_spaces_are_identified(self):
        items = [text("Hi.There  "), text(" again.")]
        rows = wrap_text_audit.scan_unit("script.json", 0, items)
        self.assertEqual([row["category"] for row in rows],
                         ["sentence_spacing", "multiple_ascii_spaces"])
        self.assertTrue(rows[1]["across_fragments"])


if __name__ == "__main__":
    unittest.main()
