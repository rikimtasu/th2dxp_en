import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import debug_script_probe


class DebugScriptProbeTests(unittest.TestCase):
    def source(self):
        return (b"\x5a" * debug_script_probe.START_OFFSET
                + debug_script_probe.ORIGINAL + b"immutable tail")

    def test_exact_patch_extent_and_source_preservation(self):
        source = self.source()
        patched, writes = debug_script_probe.patch_named_start(source, 0xFA62C)
        offset = debug_script_probe.START_OFFSET
        self.assertEqual(len(patched), len(source))
        self.assertEqual(patched[:offset], source[:offset])
        self.assertEqual(patched[offset + 20:], source[offset + 20:])
        self.assertEqual(source[offset:offset + 20], debug_script_probe.ORIGINAL)
        self.assertEqual(len(writes), 5)
        self.assertEqual(writes[0]["file_offset"], "0x7bc9c")

    def test_pointer_context_lookup_and_call_return(self):
        patched, _ = debug_script_probe.patch_named_start(self.source(), 0xFA62C)
        words = struct.unpack_from(">5I", patched, debug_script_probe.START_OFFSET)
        self.assertEqual(words[:4], (0x3C80000F, 0x6084A62C, 0x3C600065, 0x80632614))
        self.assertEqual(((words[0] & 0xFFFF) << 16) | (words[1] & 0xFFFF), 0xFA62C)
        displacement = words[4] & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        call_va = debug_script_probe.START_VA + 16
        self.assertEqual(call_va + displacement, 0x5E0E0)
        self.assertEqual(words[4] & 3, 1)  # relative branch with link
        self.assertEqual(call_va + 4, 0x8BCB0)

    def test_rejects_changed_or_truncated_instruction_guard(self):
        for source in (self.source()[:debug_script_probe.START_OFFSET + 19],
                       self.source().replace(debug_script_probe.ORIGINAL,
                                             b"\0" * 20)):
            with self.assertRaisesRegex(ValueError, "instruction guard"):
                debug_script_probe.patch_named_start(source, 0xFA62C)

    def test_rejects_invalid_pointer(self):
        for address in (0, -1, 0x100000000):
            with self.assertRaisesRegex(ValueError, "nonzero 32-bit"):
                debug_script_probe.patch_named_start(self.source(), address)


if __name__ == "__main__":
    unittest.main()
