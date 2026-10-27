"""End-to-end install engine checks on synthetic patch data; no game data."""
import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import patch_data
import patch_engine
import patch_game
import patch_gui
from patch_fixtures import elf_like, make_dat, make_sdat, patched_dat, sha


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.usrdir = self.root / "PS3_GAME" / "USRDIR"
        self.usrdir.mkdir(parents=True)

        self.pristine_elf = elf_like(b"pristine", 2048, seed=5)
        patched = bytearray(self.pristine_elf)
        patched[0x30:0x34] = b"\xca\xfe\xba\xbe"
        self.patched_elf = bytes(patched) + b"tail" * 40
        self.pristine_dat = make_dat([("a.bin", b"A" * 8), ("b.bin", b"B" * 16)])
        self.patched_dat = patched_dat(self.pristine_dat, {"b.bin": b"new" * 21})
        self.pristine_sdat = make_sdat(self.pristine_dat)
        self.patched_sdat = make_sdat(self.patched_dat)

        artifacts = self.root / "artifacts"
        artifacts.mkdir()
        self.write(artifacts / "EBOOT.elf", self.pristine_elf)
        self.write(artifacts / "EBOOT_EN.elf", self.patched_elf)
        self.write(artifacts / "data.dat", self.pristine_dat)
        self.write(artifacts / "data_EN.dat", self.patched_dat)
        self.write(artifacts / "data.sdat", self.pristine_sdat)
        self.write(artifacts / "data_EN.sdat", self.patched_sdat)
        self.patch = self.root / "patch-data"
        patch_data.build(artifacts / "EBOOT.elf", artifacts / "EBOOT_EN.elf",
                         artifacts / "data.dat", artifacts / "data_EN.dat", self.patch,
                         pristine_sdat=artifacts / "data.sdat",
                         patched_sdat=artifacts / "data_EN.sdat", log=lambda *_: None)

        self.write(self.usrdir / "EBOOT.BIN", self.pristine_elf)
        self.write(self.usrdir / "data.sdat", self.pristine_sdat)
        self.salt = b"path-salt-in-npd"

        self.start(patch.object(patch_engine, "_invoke", side_effect=self.fake_invoke))

    def start(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_tools(self):
        return patch.object(patch_engine, "find_tools",
                            return_value=(Path("decrypt"), Path("pack")))

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def fake_invoke(self, command, *, expect, label):
        command = [str(part) for part in command]
        if "--verify" in command:
            return "SDAT header, metadata and every ciphertext block authenticated!"
        if "-d" in command:
            sdat, dat = Path(command[3]), Path(command[4])
            dat.write_bytes(sdat.read_bytes()[144:])
            return "File successfully parsed!\nFile successfully decrypted!"
        if "-e" in command:
            dat, sdat = Path(command[3]), Path(command[4])
            image = bytearray(make_sdat(dat.read_bytes()))
            # A real rebuild hashes the input path into the NPD header, so its
            # bytes never match the reference archive produced on another machine.
            image[80:96] = self.salt
            sdat.write_bytes(bytes(image))
            return "File successfully encrypted!\nFile successfully forged!"
        raise AssertionError(f"unexpected command: {command}")

    def plan(self):
        return patch_engine.plan(self.patch, self.usrdir)

    def install(self):
        with self.fake_tools():
            return patch_engine.install(self.patch, self.usrdir, confirm=True)

    # ---- planning --------------------------------------------------------
    def test_plan_names_the_pristine_pair_and_what_it_would_write(self):
        plan = self.plan()
        self.assertEqual(plan["blocked"], [])
        self.assertTrue(plan["elf"]["install"])
        self.assertEqual(plan["elf"]["current_kind"], "ELF")
        self.assertEqual(plan["archive"]["current_kind"], "pristine")
        self.assertTrue(plan["archive"]["install"])
        self.assertFalse(plan["nothing_to_do"])
        self.assertEqual(plan["patch"]["version"], "0.1")

    def test_free_space_covers_the_backup_and_the_largest_intermediate(self):
        plan = self.plan()
        backup = len(self.pristine_sdat)
        self.assertGreaterEqual(plan["free_space_needed"],
                                backup + len(self.pristine_dat) + len(self.patched_dat))
        self.assertGreaterEqual(plan["free_space_needed"],
                                backup + len(self.patched_dat) + len(self.patched_sdat))
        self.assertGreaterEqual(plan["free_space_needed"], patch_engine.SLACK)

    def test_the_default_patch_folder_is_found_beside_the_release(self):
        self.assertEqual(patch_engine.default_patch_dir(self.root), self.patch)

    def test_a_shortage_of_space_blocks_the_install(self):
        with patch.object(patch_engine, "_free", return_value=1024):
            plan = self.plan()
        self.assertTrue(any("Not enough free space" in text for text in plan["blocked"]))
        with self.assertRaisesRegex(ValueError, "Cannot install"):
            patch_engine.apply(plan)

    def test_an_archive_that_is_not_pristine_blocks_with_restore_advice(self):
        self.write(self.usrdir / "data.sdat", b"not the retail archive")
        plan = self.plan()
        self.assertEqual(plan["archive"]["current_kind"], "unknown")
        self.assertTrue(any("neither the pristine BLJM60381 archive" in text
                            for text in plan["blocked"]))
        with self.assertRaisesRegex(ValueError, "Cannot install"):
            patch_engine.apply(plan)
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), b"not the retail archive")

    def test_an_executable_from_another_build_blocks_with_restore_advice(self):
        self.write(self.usrdir / "EBOOT.BIN", elf_like(b"other-build", 2048, seed=9))
        plan = self.plan()
        self.assertTrue(any("another build" in text for text in plan["blocked"]))

    def test_patch_data_without_archive_hashes_is_refused(self):
        bare = self.root / "bare-patch"
        patch_data.build(self.root / "artifacts/EBOOT.elf", self.root / "artifacts/EBOOT_EN.elf",
                         self.root / "artifacts/data.dat", self.root / "artifacts/data_EN.dat",
                         bare, log=lambda *_: None)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            patch_engine.plan(bare, self.usrdir)

    def test_apply_refuses_a_plan_that_did_not_come_from_plan(self):
        with self.assertRaisesRegex(ValueError, "was not produced by plan"):
            patch_engine.apply({"usrdir": str(self.usrdir)})

    # ---- installation ----------------------------------------------------
    def test_install_writes_both_files_and_records_the_journal(self):
        result = self.install()
        self.assertTrue(result["applied"])
        self.assertEqual(result["installed"], {"elf": True, "sdat": True})
        self.assertEqual((self.usrdir / "EBOOT.BIN").read_bytes(), self.patched_elf)
        installed_sdat = (self.usrdir / "data.sdat").read_bytes()
        self.assertEqual(installed_sdat[144:], self.patched_dat)
        self.assertNotEqual(sha(installed_sdat), sha(self.patched_sdat))
        journal = patch_game.read_journal(self.usrdir)
        self.assertEqual(journal["backups"]["EBOOT.BIN"]["sha256"], sha(self.pristine_elf))
        self.assertEqual(journal["backups"]["data.sdat"]["sha256"], sha(self.pristine_sdat))
        self.assertEqual(journal["backups"]["data.sdat"]["kind"], "pristine")
        record = journal["installs"][-1]
        self.assertEqual(record["mode"], "self-contained")
        self.assertEqual(record["sdat_sha256"], sha(installed_sdat))
        self.assertEqual(record["sdat_dat_sha256"], sha(self.patched_dat))
        self.assertFalse((self.usrdir / patch_engine.WORK_DIRNAME).exists())

    def test_a_dry_run_writes_nothing(self):
        result = patch_engine.install(self.patch, self.usrdir)
        self.assertTrue(result["dry_run"])
        self.assertEqual((self.usrdir / "EBOOT.BIN").read_bytes(), self.pristine_elf)
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), self.pristine_sdat)
        self.assertIsNone(patch_game.read_journal(self.usrdir))

    def test_after_installing_the_plan_has_nothing_to_do(self):
        self.install()
        plan = self.plan()
        self.assertEqual(plan["blocked"], [])
        self.assertTrue(plan["nothing_to_do"])
        self.assertFalse(plan["elf"]["install"])
        self.assertFalse(plan["archive"]["install"])
        with self.assertRaisesRegex(ValueError, "Nothing to do"):
            patch_engine.apply(plan)

    def test_restore_brings_the_pristine_pair_back(self):
        self.install()
        patch_game.restore(self.usrdir, confirm=True)
        self.assertEqual((self.usrdir / "EBOOT.BIN").read_bytes(), self.pristine_elf)
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), self.pristine_sdat)

    def test_a_legacy_side_by_side_executable_is_removed(self):
        self.write(self.usrdir / patch_game.LEGACY_ELF_NAME, b"old")
        self.install()
        self.assertFalse((self.usrdir / patch_game.LEGACY_ELF_NAME).exists())

    def test_a_failed_encrypt_leaves_the_game_untouched(self):
        def failing(command, *, expect, label):
            if "-e" in [str(part) for part in command]:
                raise ValueError("Encrypting data.sdat failed (exit 1): boom")
            return self.fake_invoke(command, expect=expect, label=label)

        with patch.object(patch_engine, "_invoke", side_effect=failing):
            with self.assertRaisesRegex(ValueError, "Encrypting data.sdat failed"):
                self.install()
        self.assertEqual((self.usrdir / "EBOOT.BIN").read_bytes(), self.pristine_elf)
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), self.pristine_sdat)
        self.assertFalse((self.usrdir / patch_engine.WORK_DIRNAME).exists())
        journal = patch_game.read_journal(self.usrdir)
        self.assertEqual(journal["installs"], [])
        self.assertEqual(journal["backups"]["data.sdat"]["sha256"], sha(self.pristine_sdat))

    def test_a_rebuild_that_does_not_read_back_is_refused(self):
        def corrupt(command, *, expect, label):
            command = [str(part) for part in command]
            if "-e" in command:
                dat, sdat = Path(command[3]), Path(command[4])
                image = bytearray(make_sdat(dat.read_bytes()))
                image[80:96] = self.salt
                image[-16:] = b"\x00" * 16
                sdat.write_bytes(bytes(image))
                return "File successfully encrypted!\nFile successfully forged!"
            if "-d" in command and Path(command[3]).parent.name == patch_engine.WORK_DIRNAME:
                sdat, dat = Path(command[3]), Path(command[4])
                dat.write_bytes(sdat.read_bytes()[144:-16])
                return "File successfully parsed!\nFile successfully decrypted!"
            return self.fake_invoke(command, expect=expect, label=label)

        with patch.object(patch_engine, "_invoke", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "does not contain the patched data"):
                self.install()
        self.assertEqual((self.usrdir / "EBOOT.BIN").read_bytes(), self.pristine_elf)
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), self.pristine_sdat)
        self.assertFalse((self.usrdir / patch_engine.WORK_DIRNAME).exists())

    def test_a_stale_workspace_is_replaced(self):
        stale = self.usrdir / patch_engine.WORK_DIRNAME
        stale.mkdir()
        (stale / "leftover.bin").write_bytes(b"old attempt")
        self.install()
        self.assertFalse(stale.exists())

    # ---- helpers ---------------------------------------------------------
    def test_a_missing_helper_is_named(self):
        empty = self.root / "no-tools"
        empty.mkdir()
        with patch.object(patch_engine, "search_roots", return_value=[empty]):
            with self.assertRaisesRegex(ValueError, "make_npdata.exe helper is missing"):
                patch_engine.find_tools()

    def test_an_unpinned_helper_is_refused(self):
        folder = self.root / "bad-tools"
        self.write(folder / patch_engine.DECRYPTOR, b"not the pinned binary")
        self.write(folder / patch_engine.PACKER, b"nor this one")
        with patch.object(patch_engine, "search_roots", return_value=[folder]):
            with self.assertRaisesRegex(ValueError, "not the pinned make_npdata build"):
                patch_engine.find_tools()

    def test_the_manifest_round_trips_through_the_installer(self):
        manifest = patch_data.load_manifest(self.patch)
        self.assertEqual(manifest["elf"]["output_sha256"], sha(self.patched_elf))
        self.assertEqual(manifest["archive"]["output_sdat_sha256"], sha(self.patched_sdat))
        self.assertEqual(json.loads((self.patch / "manifest.json").read_text(encoding="utf-8"))
                         ["archive"]["replacements"][0]["name"], "b.bin")


class GuiPlanTextTests(unittest.TestCase):
    def test_describe_plan_explains_a_self_contained_install(self):
        plan = {"usrdir": "C:/game", "blocked": [], "nothing_to_do": False,
                "patch": {"version": "0.1"},
                "elf": {"install": True, "current_kind": "SELF"},
                "archive": {"install": True, "current_kind": "pristine"},
                "free_space_needed": 7 * 1024 ** 3, "free_space_available": 100 * 1024 ** 3}
        text = patch_gui.describe_plan(plan)
        self.assertIn("decrypt", text.lower())
        self.assertIn("7.0 GiB", text)
        self.assertIn(".th2dxp-backup", text)


if __name__ == "__main__":
    unittest.main()
