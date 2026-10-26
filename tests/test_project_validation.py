"""Consumer-visible validation boundaries; no game inputs or emulator required."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import project


class ProjectValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.baseline, self.scripts = root / "baseline", root / "script"
        self.original = [{"items": [{"kind": "text", "original_text": "元の文",
                                      "translated_text": "元の文", "length": 6,
                                      "control_suffix": "\\k\\n", "editable": True}]}]
        self.meta = {"entries": [{"json_filename": "script_0000.json", "text_count": 1}]}
        project.save(self.baseline / "script_0000.json", self.original)
        project.save(self.scripts / "scenario_meta.json", self.meta)
        override = patch.object(project, "BASELINE", self.baseline)
        override.start()
        self.addCleanup(override.stop)

    def edited(self, value):
        units = copy.deepcopy(self.original)
        units[0]["items"][0]["translated_text"] = value
        project.save(self.scripts / "script_0000.json", units)

    def test_unapproved_slot_mode_rejects_a_growing_translation(self):
        self.edited("The complete English sentence is longer than the source.")
        with self.assertRaisesRegex(ValueError, "complete manual engine acceptance"):
            project.validate(self.scripts, self.meta, allow_growth=False)

    def test_growth_mode_rejects_lossy_cp932_wave_dash(self):
        self.edited("\u301c")
        with self.assertRaisesRegex(ValueError, "CP932 encoding would change"):
            project.validate(self.scripts, self.meta, allow_growth=True)

    def test_growth_mode_cannot_delete_dynamic_nickname(self):
        self.original[0]["items"][0].update(
            original_text="Hello, *nnk.", translated_text="Hello, *nnk.", length=12)
        project.save(self.baseline / "script_0000.json", self.original)
        self.edited("Hello, player.")
        with self.assertRaisesRegex(ValueError, "inline engine escapes changed"):
            project.validate(self.scripts, self.meta, allow_growth=True)

    def test_growth_mode_cannot_change_font_selection(self):
        self.original[0]["items"][0].update(
            original_text="<G 1>Hello, *nfk2.", translated_text="<G 1>Hello, *nfk2.", length=19)
        project.save(self.baseline / "script_0000.json", self.original)
        self.edited("<G 0>Hello, *nfk2.")
        with self.assertRaisesRegex(ValueError, "inline engine escapes changed"):
            project.validate(self.scripts, self.meta, allow_growth=True)

if __name__ == "__main__":
    unittest.main()
