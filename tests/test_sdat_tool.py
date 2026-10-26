import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import assets
import build_sdat_tool


@unittest.skipUnless(shutil.which("gcc") and (assets.UPSTREAM / "make_npdata.c").is_file(),
                     "Standalone GCC and pinned GPL sources are required; no game assets are used")
class SdatToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        build_sdat_tool.build(cls.root / "tool")
        cls.binary = cls.root / "tool/make_npdata-pack.exe"

    def run_tool(self, *arguments):
        return subprocess.run([str(self.binary), *map(str, arguments)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def pack(self, source, output):
        result = self.run_tool("-v", "-e", source, output, "3", "0", "0", "1", "", "0")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_complete_authenticated_roundtrip_across_block_and_padding_boundaries(self):
        for size in (1, 16383, 16384, 16385):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                original = bytes((index * 37 + 19) % 256 for index in range(size))
                source, packed, decoded = root / "data.dat", root / "data.sdat", root / "decoded.dat"
                source.write_bytes(original)
                self.pack(source, packed)
                authentication = self.run_tool("--verify", packed)
                self.assertEqual(authentication.returncode, 0, authentication.stdout)
                decryption = self.run_tool("-v", "-d", packed, decoded, "0")
                self.assertNotIn("WARNING:", decryption.stdout)
                self.assertEqual(decoded.read_bytes(), original)
                self.assertEqual(source.read_bytes(), original)

    def test_header_metadata_ciphertext_and_declared_length_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, packed = root / "data.dat", root / "data.sdat"
            source.write_bytes(bytes(range(256)) * 65)
            self.pack(source, packed)
            original = packed.read_bytes()
            for name, offset, expected in (("header", 0x90, "header CMAC"),
                                           ("metadata", 0x100, "metadata CMAC"),
                                           ("ciphertext", 0x100 + 32 + 19, "ciphertext block CMAC"),
                                           ("length", 0x88, "format bounds")):
                with self.subTest(name=name):
                    damaged = bytearray(original)
                    damaged[offset] ^= 1
                    path = root / (name + ".sdat")
                    path.write_bytes(damaged)
                    result = self.run_tool("--verify", path)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn(expected, result.stdout)
                    self.assertEqual(path.read_bytes(), damaged)

    def test_final_padding_and_container_hash_are_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data.dat"
            source.write_bytes(b"Exact unaligned input; no allocator bytes in padding.")
            first, second = root / "first.sdat", root / "second.sdat"
            self.pack(source, first)
            self.pack(source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
