import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import rpcs3_debug_patch


class PpuPatchHashTests(unittest.TestCase):
    def elf(self):
        image = bytearray(256)
        image[:6] = b'\x7fELF\x02\x02'
        struct.pack_into('>Q', image, 32, 64)
        struct.pack_into('>HH', image, 54, 56, 3)
        struct.pack_into('>IIQQQQQQ', image, 64, 1, 5, 240, 0x10000, 0, 4, 16, 16)
        # Empty LOAD headers still contribute type/flags to RPCS3's hash.
        struct.pack_into('>IIQQQQQQ', image, 120, 1, 4, 244, 0, 0, 0, 0, 16)
        struct.pack_into('>IIQQQQQQ', image, 176, 7, 4, 244, 0x10004, 0, 4, 4, 4)
        image[240:248] = b'CODETLS!'
        return bytes(image)

    def test_matches_ordered_rpc3_header_and_load_hashing(self):
        expected_input = (struct.pack('>IIQQ', 1, 5, 0x10000, 16)
                          + b'CODE' + struct.pack('>II', 1, 4)
                          + struct.pack('>II', 7, 4))
        self.assertEqual(rpcs3_debug_patch.ppu_patch_hash(self.elf()),
                         'PPU-' + hashlib.sha1(expected_input).hexdigest())

    def test_nonload_payload_excluded_but_load_payload_included(self):
        image = self.elf()
        changed = bytearray(image)
        changed[244:248] = b'XXXX'
        self.assertEqual(rpcs3_debug_patch.ppu_patch_hash(image),
                         rpcs3_debug_patch.ppu_patch_hash(bytes(changed)))
        changed[240] ^= 1
        self.assertNotEqual(rpcs3_debug_patch.ppu_patch_hash(image),
                            rpcs3_debug_patch.ppu_patch_hash(bytes(changed)))

    def test_empty_segment_flags_still_identify_executable(self):
        image = self.elf()
        changed = bytearray(image)
        struct.pack_into('>I', changed, 124, 6)
        self.assertNotEqual(rpcs3_debug_patch.ppu_patch_hash(image),
                            rpcs3_debug_patch.ppu_patch_hash(bytes(changed)))

    def test_rejects_bad_class_endianness_and_short_header(self):
        for image in (b'', self.elf()[:63], b'NOTELF' + self.elf()[6:],
                      self.elf()[:5] + b'\x01' + self.elf()[6:]):
            with self.assertRaisesRegex(ValueError, 'ELF64 big-endian'):
                rpcs3_debug_patch.ppu_patch_hash(image)

    def test_rejects_header_table_and_load_bounds(self):
        for field, value in ((54, 55), (56, 100)):
            image = bytearray(self.elf())
            struct.pack_into('>H', image, field, value)
            with self.assertRaisesRegex(ValueError, 'program-header table'):
                rpcs3_debug_patch.ppu_patch_hash(bytes(image))
        for file_size in (17, 1000):
            image = bytearray(self.elf())
            struct.pack_into('>Q', image, 64 + 32, file_size)
            with self.assertRaisesRegex(ValueError, 'load-segment bounds'):
                rpcs3_debug_patch.ppu_patch_hash(bytes(image))


if __name__ == '__main__':
    unittest.main()
