"""Layout invariants for the isolated explicit-break profile; no emulator claims."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from text_layout import compile_units, wrap_ascii


class TextLayoutTests(unittest.TestCase):
    def test_long_word_wrap_preserves_every_visible_character(self):
        original = "[F01] ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        emitted = wrap_ascii(original, 24)
        self.assertEqual(emitted.replace("\\n", ""), original)
        self.assertTrue(all(len(line) <= 24 for line in emitted.split("\\n")))
        self.assertEqual(emitted.split("\\n")[-1], "STUVWXYZ")

    def test_word_boundaries_do_not_drop_spaces_or_punctuation(self):
        original = "The quick brown fox jumps."
        emitted = wrap_ascii(original, 16)
        self.assertEqual(emitted.replace("\\n", ""), original)
        self.assertTrue(all(len(line) <= 16 for line in emitted.split("\\n")))
        self.assertIn("\\n", emitted)

    def test_fragment_break_does_not_add_wait_or_replace_terminal_controls(self):
        units = [{"items": [
            {"kind": "text", "original_text": "X" * 40, "translated_text": "[F01] ABCDEFGHIJKLMNOPQRSTUVWXYZ", "control_suffix": ""},
            {"kind": "text", "original_text": "Y" * 20, "translated_text": "second fragment", "control_suffix": "\\k\\n"},
            {"kind": "control_text", "control": "\\p0001"},
        ]}]
        compiled, _ = compile_units(units, columns=24, break_fragments=True)
        text = compiled[0]["items"][1]
        self.assertEqual(text["translated_text"], "\\nsecond fragment")
        self.assertEqual(text["control_suffix"], "\\k\\n")
        self.assertEqual(compiled[0]["items"][2]["control"], "\\p0001")
        self.assertNotIn("\\k", text["translated_text"])

    def test_break_bytes_cannot_overflow_original_record_budget(self):
        units = [{"items": [{"kind": "text", "original_text": "X" * 26,
                             "translated_text": "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "control_suffix": ""}]}]
        with self.assertRaises(ValueError):
            compile_units(units, columns=24, break_fragments=True)

    def test_unsupported_inline_controls_are_not_rewritten(self):
        with self.assertRaises(ValueError):
            wrap_ascii("Hello\\k world", 24)


if __name__ == "__main__":
    unittest.main()
