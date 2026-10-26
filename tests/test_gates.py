"""Runtime acceptance must not inherit unrelated short-run control passes."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gates
import project


class RuntimeEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        screenshot = root / "observation.png"
        Image.new("RGB", (2, 2)).save(screenshot)
        artifacts = {}
        self.evidence = {}
        for kind, checks in gates.CHECKS.items():
            artifact = root / (kind + ".elf")
            artifact.write_bytes(kind.encode("ascii"))
            artifacts[kind] = artifact
            self.evidence[kind] = {
                "output_sha256": project.digest(artifact.read_bytes()),
                "tester": "synthetic tester", "rpcs3_version": "synthetic version",
                "tested_at": "synthetic run", "scene": "synthetic scene", "notes": "fixture only",
                "checks": {check: True for check in checks}, "screenshots": [str(screenshot)],
            }
        archive = root / "assets/data.sdat"
        archive.parent.mkdir()
        archive.write_bytes(b"synthetic exact UI texture archive")
        self.archive = archive
        self.evidence["windows"]["data_sdat_sha256"] = project.digest(archive.read_bytes())
        project.save(root / "manifest.json", {
            "output_sha256": self.evidence["windows"]["output_sha256"],
            "ui_archive": {"sha256": self.evidence["windows"]["data_sdat_sha256"]}})
        self.form = root / "results.json"
        for name, value in (("ROOT", root), ("ARTIFACTS", artifacts)):
            override = patch.object(gates, name, value)
            override.start()
            self.addCleanup(override.stop)

    def test_old_controls_cannot_accept_unobserved_long_text_behavior(self):
        for name in ("descenders", "word_wrapping"):
            del self.evidence["windows"]["checks"][name]
        project.save(self.form, self.evidence)
        with self.assertRaisesRegex(ValueError, "windows: required manual checks have not all passed"):
            gates.read_evidence(self.form)

    def test_each_new_runtime_failure_blocks_an_otherwise_complete_form(self):
        for name in ("story_state", "skip_after_long_text", "long_text_save_load", "descenders", "word_wrapping",
                     "ui_readability", "ui_credits", "ui_maps"):
            with self.subTest(check=name):
                evidence = copy.deepcopy(self.evidence)
                evidence["windows"]["checks"][name] = False
                project.save(self.form, evidence)
                with self.assertRaisesRegex(ValueError, "windows: required manual checks have not all passed"):
                    gates.read_evidence(self.form)

    def test_complete_results_for_another_elf_are_rejected(self):
        self.evidence["windows"]["output_sha256"] = "0" * 64
        project.save(self.form, self.evidence)
        with self.assertRaisesRegex(ValueError, "windows: manual run does not identify the current staged build"):
            gates.read_evidence(self.form)

    def test_changed_archive_invalidates_an_exact_elf_and_complete_manual_form(self):
        project.save(self.form, self.evidence)
        gates.read_evidence(self.form)
        self.archive.write_bytes(b"an unrelated texture archive")
        with self.assertRaisesRegex(ValueError, "Staged UI archive differs"):
            gates.read_evidence(self.form)

    def test_another_manually_tested_archive_is_not_accepted_with_the_current_elf(self):
        self.evidence["windows"]["data_sdat_sha256"] = "0" * 64
        project.save(self.form, self.evidence)
        with self.assertRaisesRegex(ValueError, "windows: manual run does not identify the paired UI archive"):
            gates.read_evidence(self.form)


if __name__ == "__main__":
    unittest.main()
