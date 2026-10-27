"""Headless coverage for the GUI installer's text/planning helpers; no display."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import patch_engine
import patch_game
import patch_gui


def install_plan(**overrides):
    plan = {"usrdir": "C:/game", "blocked": [], "nothing_to_do": False,
            "patch": {"version": "0.1"},
            "elf": {"install": True, "current_kind": "SELF"},
            "archive": {"install": True, "current_kind": "pristine"},
            "free_space_needed": 7 * 1024 ** 3,
            "free_space_available": 100 * 1024 ** 3,
            "backups": {patch_game.GAME_ELF_NAME: None, patch_game.SDAT_NAME: None},
            "last_install": None}
    plan.update(overrides)
    return plan


class HelpersTests(unittest.TestCase):
    def test_human_bytes_scales_and_keeps_units_readable(self):
        self.assertEqual(patch_gui.human_bytes(0), "0 B")
        self.assertEqual(patch_gui.human_bytes(999), "999 B")
        self.assertEqual(patch_gui.human_bytes(6598772), "6.3 MiB")
        self.assertEqual(patch_gui.human_bytes(2185195888), "2.0 GiB")

    def test_describe_plan_explains_the_decrypt_patch_verify_flow(self):
        text = patch_gui.describe_plan(install_plan())
        self.assertIn("Install into: C:/game", text)
        self.assertIn("back up the original encrypted executable", text)
        self.assertIn("decrypt it, apply the executable patch", text)
        self.assertIn("back up the original retail archive", text)
        self.assertIn("re-encrypt it", text)
        self.assertIn("about 7.0 GiB", text)
        self.assertIn("100.0 GiB", text)
        self.assertIn(".th2dxp-backup", text)
        self.assertIn("Backups: none yet", text)

    def test_describe_plan_reports_what_blocks_a_folder(self):
        text = patch_gui.describe_plan(install_plan(
            blocked=["data.sdat is neither the pristine BLJM60381 archive nor this patch's "
                     "archive."]))
        self.assertIn("cannot be patched yet", text)
        self.assertIn("neither the pristine", text)
        self.assertNotIn("Free space needed", text)

    def test_describe_plan_says_when_nothing_is_left_to_do(self):
        text = patch_gui.describe_plan(install_plan(nothing_to_do=True))
        self.assertIn("Nothing to do", text)

    def test_describe_plan_names_a_previous_install_and_its_backups(self):
        text = patch_gui.describe_plan(install_plan(
            last_install={"installed_at": "2026-10-27T00:00:00+00:00",
                          "elf_sha256": "a" * 64, "sdat_sha256": "b" * 64},
            backups={patch_game.GAME_ELF_NAME: {"size": 1, "sha256": "0" * 64},
                     patch_game.SDAT_NAME: None}))
        self.assertIn("Last install: 2026-10-27T00:00:00+00:00", text)
        self.assertIn("Backups: EBOOT.BIN", text)

    def test_describe_plan_only_mentions_the_file_it_would_touch(self):
        plan = install_plan(archive={"install": False, "current_kind": "patched"})
        text = patch_gui.describe_plan(plan)
        self.assertIn("EBOOT.BIN:", text)
        self.assertNotIn("data.sdat:", text)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "nested" / "ui.json"

    def test_round_trip_creates_parents_and_writes_lf(self):
        patch_gui.save_settings({"game_dir": "C:/game", "build_dir": "C:/patch"}, self.path)
        self.assertEqual(patch_gui.load_settings(self.path),
                         {"game_dir": "C:/game", "build_dir": "C:/patch"})
        self.assertNotIn(b"\r\n", self.path.read_bytes())

    def test_missing_and_corrupt_settings_read_as_empty(self):
        self.assertEqual(patch_gui.load_settings(self.path), {})
        self.path.parent.mkdir(parents=True)
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(patch_gui.load_settings(self.path), {})
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(patch_gui.load_settings(self.path), {})

    def test_settings_path_stays_per_user(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": r"C:\Users\me\AppData\Local"},
                        clear=False):
            path = patch_gui.settings_path()
        self.assertEqual(path.name, patch_gui.SETTINGS_NAME)
        self.assertEqual(path.parent.name, "th2dxp_en")


class GameFolderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.usrdir = self.root / "PS3_GAME" / "USRDIR"
        self.usrdir.mkdir(parents=True)
        (self.usrdir / patch_game.GAME_ELF_NAME).write_bytes(b"SCE\0self")

    def test_accepts_the_game_folder_ps3_game_or_usrdir(self):
        for candidate in (self.root, self.root / "PS3_GAME", self.usrdir):
            self.assertEqual(patch_game.require_usrdir(candidate), self.usrdir.resolve())

    def test_rejects_a_folder_that_holds_no_game(self):
        empty = self.root / "elsewhere"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "Not a game USRDIR"):
            patch_game.require_usrdir(empty)

    def test_a_pointed_at_file_selects_its_folder(self):
        self.assertEqual(patch_game.require_usrdir(self.usrdir / patch_game.GAME_ELF_NAME),
                         self.usrdir.resolve())


class PatchFolderDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def make_patch(self, folder):
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(
            json.dumps({"schema": 1, "elf": {}, "archive": {}}), encoding="utf-8", newline="\n")
        return folder

    def test_finds_patch_data_beside_the_program(self):
        expected = self.make_patch(self.root / "patch-data")
        self.assertEqual(patch_gui.find_build(self.root), expected)

    def test_accepts_the_patch_folder_itself(self):
        expected = self.make_patch(self.root / "own")
        self.assertEqual(patch_gui.find_build(expected), expected)

    def test_returns_none_instead_of_guessing(self):
        self.assertIsNone(patch_gui.find_build(self.root))
        (self.root / "patch-data").mkdir()
        self.assertIsNone(patch_gui.find_build(self.root))

    def test_prefers_the_patch_data_folder(self):
        self.make_patch(self.root / "patch-data")
        self.make_patch(self.root / "elsewhere")
        self.assertEqual(patch_gui.find_build(self.root), self.root / "patch-data")


class SelfTestTests(unittest.TestCase):
    def test_self_test_passes_and_prints_ok(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertIsNone(patch_gui.self_test())
        self.assertIn("self-test OK", buffer.getvalue())

    def test_version_flag_returns_zero_without_a_window(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(patch_gui.main(["--version"]), 0)
        self.assertIn(patch_gui.VERSION, buffer.getvalue())

    def test_self_test_flag_returns_zero(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(patch_gui.main(["--self-test"]), 0)

    def test_every_plan_key_the_window_reads_stays_public(self):
        """The window renders a plan; a rename must break this test, not the window."""
        plan = install_plan()
        rendered = patch_gui.describe_plan(plan)
        self.assertIsInstance(rendered, str)
        for key in ("usrdir", "blocked", "nothing_to_do", "elf", "archive",
                    "free_space_needed", "free_space_available", "backups", "last_install"):
            self.assertIn(key, plan)
        self.assertTrue(json.dumps(plan))


if __name__ == "__main__":
    unittest.main()
