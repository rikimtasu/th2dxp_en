"""Check the default-player-name relocation on synthetic data."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import native_default_name_patch as names


def _lis(register, value=0x10):
    return (0x3C000000 | (register << 21) | value).to_bytes(4, "big")


def _addic(register, immediate, base=None):
    return (0x30000000 | (register << 21) | ((register if base is None else base) << 16)
            | (immediate & 0xFFFF)).to_bytes(4, "big")


def _addi(register, base, immediate):
    return (0x38000000 | (register << 21) | (base << 16) | (immediate & 0xFFFF)).to_bytes(4, "big")


def _ori(register, base, immediate=0):
    return (0x60000000 | (register << 21) | (base << 16) | immediate).to_bytes(4, "big")


SITE_BASE = 0x1000


def fixture(*, limits=None, tail=b"\0\0\0\0", extra=None, listed_extra=None):
    """A synthetic read-only window plus one lis/addic|ori copy per name slot."""
    image = bytearray(0x100000)
    image[:4] = b"\x7fELF"
    for offset, text, _ in names.SLOTS:
        encoded = text.encode("cp932") + b"\0"
        image[offset:offset + len(encoded)] = encoded
    image[names.WINDOW_END - len(tail):names.WINDOW_END] = tail
    records, sites = [], []
    for index, (offset, text, _) in enumerate(names.SLOTS):
        register = 10 + index
        site = SITE_BASE + index * 0x20
        immediate = (offset + names.TEXT_BASE) - names.LIS_RIGHT
        image[site:site + 4] = _lis(register)
        image[site + 4:site + 8] = _addic(register, immediate)
        image[site + 8:site + 12] = _addi(5, 0, (limits or {}).get(index, 13))
        image[site + 12:site + 16] = _ori(4, register)
        records.append({"offset": offset, "original": text,
                        "code_references": [{"site": site + 4 + 0x10000},
                                            {"site": site + 12 + 0x10000}]})
        sites.append(site + 4)
    if extra is not None:
        at, word = extra
        image[at:at + 4] = word
    if listed_extra is not None:
        records[0]["code_references"].append({"site": listed_extra + 0x10000})
    return bytes(image), {"records": records}, sites


class LayoutTests(unittest.TestCase):
    def test_six_slots_fit_the_native_window(self):
        source, inventory, _ = fixture()
        manifest = names._plan(source, inventory)
        self.assertEqual(manifest["window"]["bytes_written"], 38)
        self.assertEqual(len(bytes.fromhex(manifest["window"]["after"])), 40)
        self.assertEqual([slot["text"] for slot in manifest["slots"]],
                         ["Takaaki", "Takaaki", "Kouno", "Kouno", "Taka", "Taka"])
        self.assertEqual(manifest["names"]["display"], "Kouno Takaaki")
        self.assertEqual(manifest["reference_sites"], 6)
        self.assertFalse(manifest["helper_injected"])

    def test_repointed_immediates_keep_opcode_and_registers(self):
        source, inventory, sites = fixture()
        manifest = names._plan(source, inventory)
        image = names.apply(source, manifest, source=source)[0]
        for patch, site in zip(manifest["patches"], sites):
            before = struct.unpack_from(">I", source, site)[0]
            after = struct.unpack_from(">I", image, site)[0]
            self.assertEqual(before >> 26, after >> 26)
            self.assertEqual((before >> 21) & 31, (after >> 21) & 31)
            self.assertEqual((before >> 16) & 31, (after >> 16) & 31)
            self.assertEqual(after & 0xFFFF, int(patch["target_slot_offset"], 0) & 0xFFFF)

    def test_first_slot_immediate_is_unchanged(self):
        source, inventory, sites = fixture()
        manifest = names._plan(source, inventory)
        first = manifest["patches"][0]
        self.assertEqual(first["source_before"], first["after"])
        self.assertEqual(names.apply(source, manifest, source=source)[0][sites[0]:sites[0] + 4],
                         source[sites[0]:sites[0] + 4])

    def test_only_the_window_and_immediates_change(self):
        source, inventory, sites = fixture()
        manifest = names._plan(source, inventory)
        image = names.apply(source, manifest, source=source)[0]
        allowed = set(range(names.SLOTS[0][0], names.WINDOW_END))
        for site in sites:
            allowed.update(range(site, site + 4))
        changed = {at for at in range(len(source)) if source[at] != image[at]}
        self.assertTrue(changed)
        self.assertEqual(changed - allowed, set())

    def test_window_tail_data_is_rejected(self):
        source, inventory, _ = fixture(tail=b"\0\0\0\x01")
        with self.assertRaisesRegex(ValueError, "carries data after the six strings"):
            names._plan(source, inventory)

    def test_native_string_mismatch_is_rejected(self):
        source, inventory, _ = fixture()
        broken = bytearray(source)
        broken[names.SLOTS[2][0]] = 0x41
        with self.assertRaisesRegex(ValueError, "differs from its immutable bytes"):
            names._plan(bytes(broken), inventory)

    def test_inventory_must_still_hold_the_slot(self):
        source, inventory, _ = fixture()
        dropped = {"records": [row for row in inventory["records"]
                               if row["offset"] != names.SLOTS[4][0]]}
        with self.assertRaisesRegex(ValueError, "inventory lost the native string"):
            names._plan(source, dropped)

    def test_a_name_longer_than_the_native_copy_is_rejected(self):
        source, inventory, _ = fixture(limits={0: 6})
        with self.assertRaisesRegex(ValueError, "exceeds the native 6-byte copy"):
            names._plan(source, inventory)

    def test_an_unreviewed_load_is_rejected(self):
        source, inventory, _ = fixture()
        image = bytearray(source)
        image[SITE_BASE + 0x800:SITE_BASE + 0x804] = _lis(20)
        image[SITE_BASE + 0x804:SITE_BASE + 0x808] = _addic(20, 0x73D8)
        with self.assertRaisesRegex(ValueError, "unreviewed instruction"):
            names._plan(bytes(image), inventory)

    def test_an_inventoried_non_immediate_site_is_rejected(self):
        stray = SITE_BASE + 0x800
        source, inventory, _ = fixture(listed_extra=stray)
        image = bytearray(source)
        image[stray:stray + 4] = _addic(9, 0x1234)
        with self.assertRaisesRegex(ValueError, "not a plain addic/addi immediate"):
            names._plan(bytes(image), inventory)


class ApplyAndVerifyTests(unittest.TestCase):
    def build(self):
        source, inventory, sites = fixture()
        manifest = names._plan(source, inventory)
        return source, manifest, sites

    def test_apply_refuses_a_changed_window(self):
        source, manifest, _ = self.build()
        image = bytearray(source)
        image[names.SLOTS[3][0]] ^= 0xFF
        with self.assertRaisesRegex(ValueError, "window differs from the immutable original"):
            names.apply(bytes(image), manifest, source=source)

    def test_apply_refuses_a_changed_load(self):
        source, manifest, sites = self.build()
        image = bytearray(source)
        image[sites[2] + 3] ^= 0x01
        with self.assertRaisesRegex(ValueError, "differs from the immutable original"):
            names.apply(bytes(image), manifest, source=source)

    def test_apply_refuses_a_manifest_from_another_source(self):
        source, manifest, _ = self.build()
        manifest = dict(manifest, source_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "another source executable"):
            names.apply(source, manifest, source=source)

    def test_verify_accepts_the_applied_image(self):
        source, manifest, _ = self.build()
        image = names.apply(source, manifest, source=source)[0]
        report = names.verify(image, manifest, source=source)
        self.assertEqual(report["reference_sites"], 6)
        self.assertEqual(report["slots"][0], "Takaaki")
        self.assertFalse(report["runtime_accepted"])

    def test_verify_rejects_a_load_left_on_the_old_offset(self):
        source, manifest, sites = self.build()
        image = bytearray(names.apply(source, manifest, source=source)[0])
        image[sites[2]:sites[2] + 4] = source[sites[2]:sites[2] + 4]
        with self.assertRaisesRegex(ValueError, "was not repointed"):
            names.verify(bytes(image), manifest, source=source)

    def test_verify_rejects_a_short_window(self):
        source, manifest, _ = self.build()
        image = bytearray(names.apply(source, manifest, source=source)[0])
        image[names.WINDOW_END - 1] = 0x41
        with self.assertRaisesRegex(ValueError, "renamed name window is absent"):
            names.verify(bytes(image), manifest, source=source)

    def test_substitute_refuses_an_unreviewed_source(self):
        source, inventory, _ = fixture()
        with self.assertRaisesRegex(ValueError, "immutable reviewed executable"):
            names.substitute(source, inventory=inventory)


if __name__ == "__main__":
    unittest.main()
