"""Bounded choice text and symbolic-branch invariants, without game assets."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import choice_text


class RawLengthFallback:
    TEXT_OPCODE = b"\x02\x0b\x00\x0a"

    @staticmethod
    def read_text_records_structured(*args):
        # Exercise scan_sites' raw length-delimited fallback, not codec decoding.
        return []


def scenario(code, targets=()):
    header = b"VE\0\0" + struct.pack("<III", len(code), len(targets), 0)
    labels = b"".join((f"@{index}".encode().ljust(32, b"\0") + struct.pack("<I", target))
                      for index, target in enumerate(targets))
    return header + labels + code


def option(raw):
    return b"\x02\x08\x22\x0a" + struct.pack("<H", len(raw)) + raw


class ChoiceTextTests(unittest.TestCase):
    def test_embedded_signature_in_dialogue_is_not_an_option(self):
        fake = option(b"not an option")
        message = RawLengthFallback.TEXT_OPCODE + struct.pack("<H", len(fake)) + fake
        original = scenario(message + option(b"Actual option."))
        self.assertEqual([row["text"] for row in choice_text.records(original, RawLengthFallback)],
                         ["Actual option."])

    def test_growth_keeps_symbolic_branch_destination(self):
        caption = option("公園へ".encode("cp932"))
        branch = b"\x02\x08\x63\x05\x02@0\x02"
        terminal = b"\x02\x08\x01\x02"
        original = scenario(caption + branch + terminal, [len(caption) + len(branch)])
        code_start = 16 + 36
        start, end = code_start + 3, code_start + len(caption)
        translation = b"How about going to an amusement park?"
        rebuilt = choice_text.splice_literals(original, [(start, end, translation)])
        target = code_start + struct.unpack_from("<I", rebuilt, 48)[0]
        self.assertEqual(rebuilt[target:], terminal)
        self.assertEqual(rebuilt[target - len(branch):target], branch)
        self.assertEqual(choice_text.records(rebuilt, RawLengthFallback)[0]["text"], translation.decode())
        self.assertEqual(struct.unpack_from("<I", rebuilt, 4)[0], len(rebuilt) - code_start)

    def test_label_into_resized_literal_is_rejected(self):
        caption = option(b"Original")
        original = scenario(caption, [7])
        with self.assertRaisesRegex(ValueError, "interior"):
            choice_text.splice_literals(original, [(16 + 36 + 3, len(original), b"Longer caption")])

    def test_format_overflow_is_rejected_not_truncated(self):
        original = scenario(option(b"A"))
        with self.assertRaisesRegex(ValueError, "16-bit"):
            choice_text.splice_literals(original, [(19, len(original), b"A" * 65536)])

    def test_dynamic_choice_argument_is_not_silently_omitted(self):
        original = scenario(b"\x02\x08\x22\x06\x00\x02")
        with self.assertRaisesRegex(ValueError, "bounded literal"):
            choice_text.records(original, RawLengthFallback)


if __name__ == "__main__":
    unittest.main()
