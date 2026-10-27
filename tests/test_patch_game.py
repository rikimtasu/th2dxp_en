"""Synthetic patch/restore and gt_output import boundaries; no game required."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import project
import patch_game
import import_gt_output as importer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PatchGameTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.usrdir = root / "USRDIR"
        self.usrdir.mkdir()
        self.original_elf = b"SCE\0original-self-bytes"
        self.original_sdat = b"pristine-archive"
        (self.usrdir / "EBOOT.BIN").write_bytes(self.original_elf)
        (self.usrdir / "data.sdat").write_bytes(self.original_sdat)
        self.build = root / "build" / "probe"
        self.build.mkdir(parents=True)
        self.elf = b"\x7fELFpatched-elf"
        (self.build / "EBOOT.elf").write_bytes(self.elf)
        self.sdat = self.build / "assets" / "data.sdat"
        self.sdat.parent.mkdir()
        self.sdat.write_bytes(b"patched-archive")
        self.report = {"output_sha256": hashlib.sha256(self.elf).hexdigest(),
                       "ui_archive": {"path": "assets/data.sdat", "sha256": sha(self.sdat)}}
        self.save_report()
        for name, value in (("rpcs3_running", lambda: False),
                            ("PRISTINE_SDAT_SHA256", sha(self.usrdir / "data.sdat")),
                            ("PRISTINE_SDAT_SIZE", len(self.original_sdat))):
            patcher = patch.object(patch_game, name, value)
            self.addCleanup(patcher.stop)
            patcher.start()

    def save_report(self):
        (self.build / "EBOOT.report.json").write_text(
            json.dumps(self.report), encoding="utf-8", newline="\n")

    def test_dry_run_changes_nothing(self):
        plan = patch_game.apply(self.build, self.usrdir)
        self.assertTrue(plan["dry_run"])
        self.assertEqual([action["file"] for action in plan["actions"]], ["EBOOT.BIN", "data.sdat"])
        self.assertEqual((self.usrdir / "EBOOT.BIN").read_bytes(), self.original_elf)
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), self.original_sdat)
        self.assertFalse((self.usrdir / patch_game.BACKUP_DIRNAME).exists())
        self.assertFalse((self.usrdir / patch_game.JOURNAL_NAME).exists())

    def test_apply_replaces_the_self_and_archive_then_restores_them(self):
        result = patch_game.apply(self.build, self.usrdir, confirm=True)
        self.assertTrue(result["applied"])
        self.assertEqual((self.usrdir / "EBOOT.BIN").read_bytes(), self.elf)
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), b"patched-archive")
        backup = self.usrdir / patch_game.BACKUP_DIRNAME
        self.assertEqual((backup / "EBOOT.BIN").read_bytes(), self.original_elf)
        self.assertEqual((backup / "data.sdat").read_bytes(), self.original_sdat)
        journal = patch_game.read_journal(self.usrdir)
        self.assertEqual(len(journal["installs"]), 1)
        self.assertFalse(journal["installs"][0]["save_data_modified"])
        self.assertEqual(journal["installs"][0]["elf_written_as"], "EBOOT.BIN")
        self.assertEqual(patch_game.status(self.usrdir)["files"]["EBOOT.BIN"]["kind"], "ELF")
        self.assertTrue(patch_game.status(self.usrdir)["installed_elf_matches_journal"])

        patch_game.restore(self.usrdir, confirm=True)
        self.assertEqual((self.usrdir / "EBOOT.BIN").read_bytes(), self.original_elf)
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), self.original_sdat)
        self.assertTrue(patch_game.status(self.usrdir)["sdat_is_pristine"])
        self.assertEqual(patch_game.read_journal(self.usrdir)["installs"], [])

    def test_apply_removes_the_legacy_side_by_side_elf(self):
        (self.usrdir / "EBOOT_EN.elf").write_bytes(b"\x7fELFlegacy")
        patch_game.apply(self.build, self.usrdir, confirm=True)
        self.assertFalse((self.usrdir / "EBOOT_EN.elf").exists())

    def test_restore_requires_a_journal(self):
        with self.assertRaisesRegex(ValueError, "No patch journal"):
            patch_game.restore(self.usrdir, confirm=True)

    def test_refuses_tampered_or_unreported_artifacts(self):
        (self.build / "EBOOT.elf").write_bytes(b"\x7fELFtampered")
        with self.assertRaisesRegex(ValueError, "does not match its report"):
            patch_game.staged_pair(self.build)
        (self.build / "EBOOT.elf").write_bytes(self.elf)
        self.sdat.write_bytes(b"older-archive")
        with self.assertRaisesRegex(ValueError, "never mix an older archive"):
            patch_game.staged_pair(self.build)

    def test_refuses_a_non_elf_executable(self):
        (self.build / "EBOOT.elf").write_bytes(b"SCE\0not-an-elf")
        self.report["output_sha256"] = sha(self.build / "EBOOT.elf")
        self.save_report()
        with self.assertRaisesRegex(ValueError, "not a decrypted ELF"):
            patch_game.staged_pair(self.build)

    def test_refuses_missing_report_and_non_game_directory(self):
        (self.build / "EBOOT.report.json").unlink()
        with self.assertRaisesRegex(ValueError, "no EBOOT.report.json"):
            patch_game.staged_pair(self.build)
        other = Path(self.temporary.name) / "empty"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "Not a game USRDIR"):
            patch_game.apply(self.build, other, confirm=True)

    def test_refuses_an_unidentified_installed_executable(self):
        (self.usrdir / "EBOOT.BIN").write_bytes(b"not a self")
        with self.assertRaisesRegex(ValueError, "neither a PS3 SELF nor a decrypted ELF"):
            patch_game.apply(self.build, self.usrdir, confirm=True)

    def test_refuses_a_foreign_archive_without_a_recorded_backup(self):
        (self.usrdir / "data.sdat").write_bytes(b"someone-elses-archive")
        with self.assertRaisesRegex(ValueError, "neither the pristine BLJM60381 archive"):
            patch_game.apply(self.build, self.usrdir, confirm=True)
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), b"someone-elses-archive")

    def test_backup_tampering_blocks_install(self):
        patch_game.apply(self.build, self.usrdir, confirm=True)
        (self.usrdir / "data.sdat").write_bytes(b"user-edited")
        (self.usrdir / patch_game.BACKUP_DIRNAME / "data.sdat").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "was modified"):
            patch_game.apply(self.build, self.usrdir, confirm=True)

    def test_second_apply_finds_nothing_to_do(self):
        patch_game.apply(self.build, self.usrdir, confirm=True)
        plan = patch_game.apply(self.build, self.usrdir, confirm=True)
        self.assertTrue(plan["nothing_to_do"])
        self.assertEqual(plan["actions"], [])
        self.assertEqual((self.usrdir / "data.sdat").read_bytes(), b"patched-archive")

    def test_archive_at_the_build_root_is_accepted(self):
        root_sdat = self.build / "data.sdat"
        root_sdat.write_bytes(b"root-archive")
        self.report["ui_archive"] = {"path": "data.sdat", "sha256": sha(root_sdat)}
        self.save_report()
        pair = patch_game.staged_pair(self.build)
        self.assertEqual(pair["sdat"], root_sdat)


class ImportGtOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.baseline = root / "baseline"
        self.baseline.mkdir()
        self.units = [{"items": [
            {"kind": "text", "original_text": "元の文", "translated_text": "元の文",
             "control_suffix": "", "length": 8, "editable": True},
            {"kind": "text", "original_text": "", "translated_text": "", "control_suffix": "\\k",
             "length": 0, "editable": True}]}]
        project.save(self.baseline / "script_0000.json", self.units)
        patcher = patch.object(project, "BASELINE", self.baseline)
        self.addCleanup(patcher.stop)
        patcher.start()

    def rows(self, first="The line.", second=""):
        return [{"name": "", "message": first}, {"name": "", "message": second}]

    def records(self):
        return [{"record_id": "script_0000.json:0:0", "unit": 0, "item": 0},
                {"record_id": "script_0000.json:0:1", "unit": 0, "item": 1}]

    def test_accepts_preserved_fragments(self):
        defects, values = importer.check_rows(self.rows(), self.records(), "script_0000.json")
        self.assertEqual(defects, [])
        self.assertEqual(values, ["The line.", ""])

    def test_rejects_structural_and_encoding_defects(self):
        cases = {
            "row count": (self.rows()[:-1], "row count"),
            "speaker": ([{"name": "Haruka", "message": "x"}, {"name": "", "message": ""}], "speaker name"),
            "cp932": (self.rows("caf\u00e9"), "not representable"),
            "blank": (self.rows("The line.", "filled"), "blank carrier"),
            "deleted": ([{"name": "", "message": ""}, {"name": "", "message": ""}], "was deleted"),
            "controls": (self.rows("The line. *nnk"), "engine controls"),
            "literal": (self.rows("line\nbreak"), "literal control"),
        }
        for label, (rows, message) in cases.items():
            with self.subTest(label):
                defects, _ = importer.check_rows(rows, self.records(), "script_0000.json")
                self.assertTrue(any(message in defect for defect in defects), defects)

    def test_writes_only_when_clean(self):
        export = Path(self.temporary.name) / "export"
        (export / "metadata/records").mkdir(parents=True)
        (export / "base-game/gt_output").mkdir(parents=True)
        project.save(export / "metadata/manifest.json", {"format": "LinguaGacha Message-JSON"})
        project.save(export / "metadata/records/010301000.json",
                     {"script": "script_0000.json", "records": self.records()})
        project.save(export / "base-game/gt_output/010301000.json", self.rows("The line."))
        scripts = Path(self.temporary.name) / "script"
        scripts.mkdir()
        project.save(scripts / "script_0000.json", self.units)
        with patch.object(project, "SCRIPTS", scripts):
            report = importer.run(export, "base-game", write=True)
            self.assertEqual(report["defect_count"], 0)
            self.assertTrue(report["written"])
            written = project.load(scripts / "script_0000.json")
            self.assertEqual(written[0]["items"][0]["translated_text"], "The line.")
            self.assertEqual(written[0]["items"][1]["translated_text"], "")
            project.save(export / "base-game/gt_output/010301000.json", self.rows("caf\u00e9"))
            blocked = importer.run(export, "base-game", write=True)
            self.assertFalse(blocked["written"])
            self.assertEqual(project.load(scripts / "script_0000.json")[0]["items"][0]["translated_text"],
                             "The line.")


if __name__ == "__main__":
    unittest.main()
