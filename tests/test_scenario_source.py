"""Consumer-visible container regressions, without requiring game data."""
from pathlib import Path
import lzma
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import scenario_source


def chunk(payload, flag):
    packed = lzma.compress(payload, format=lzma.FORMAT_ALONE)
    data = struct.pack(">I", flag << 24 | len(packed)) + packed
    return data + b"\0" * (-len(data) % 4)


class ScenarioContainerTests(unittest.TestCase):
    def test_continuation_restores_text_beyond_first_32k(self):
        first = bytes(range(256)) * 128
        last = "Continuation contains previously omitted dialogue.".encode("cp932")
        data = chunk(first, 0x80) + chunk(last, 0)
        actual, _ = scenario_source.read_chunks(data, 0, len(data), len(first) + len(last))
        self.assertEqual(actual, first + last)

    def test_final_chunk_cannot_claim_another_chunk(self):
        data = chunk(b"dialogue", 0x80)
        with self.assertRaisesRegex(ValueError, "Continuation flag"):
            scenario_source.read_chunks(data, 0, len(data), len(b"dialogue"))

    def test_missing_continuation_does_not_silently_truncate(self):
        data = chunk(b"opening", 0x80)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            scenario_source.read_chunks(data, 0, len(data), len(b"opening and ending"))

    def test_declared_slot_cannot_read_neighbor_payload(self):
        first = chunk(b"opening", 0x80)
        second = chunk(b"neighbor", 0)
        with self.assertRaises(ValueError):
            scenario_source.read_chunks(first + second, 0, len(first), 15)

    def test_declared_size_cannot_hide_decoded_bytes(self):
        data = chunk(b"complete dialogue", 0)
        with self.assertRaisesRegex(ValueError, "declared"):
            scenario_source.read_chunks(data, 0, len(data), 4)


if __name__ == "__main__":
    unittest.main()
