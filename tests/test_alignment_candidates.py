"""Candidate preparation must not include deferred stories or stale scope."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import alignment_candidates


class BaseReviewScopeTests(unittest.TestCase):
    def setUp(self):
        identities = [("base", "base_game", ["base_game"]),
                      ("terminal", "shared", ["base_game", "anotherdays"]),
                      ("ad_extra", "anotherdays", ["anotherdays", "ikuno_story"]),
                      ("unused", "other", [])]
        self.meta = {"source_eboot_sha256": "source", "entries": [
            {"json_filename": name, "source_name": f"native-{name}", "sha256_bin": f"payload-{name}"}
            for name, status, owners in identities]}
        self.document = {"schema_version": 1, "source_sha256": "source",
                         "review": {"kind": "closed_native_dispatch_ownership_review"},
                         "totals": {"scenarios": 4, "unresolved_membership_scenarios": 0},
                         "scenarios": [dict(entry, script=entry["json_filename"],
                                            payload_sha256=entry["sha256_bin"], status=status,
                                            story_domains=owners, route_feasibility_proved=False,
                                            proof_kind="closed_native_normal_story_dispatch_ownership")
                                       for entry, (_, status, owners) in zip(self.meta["entries"], identities)]}

    def test_base_and_base_shared_are_selected_without_ad_standalone_or_inactive(self):
        rows = alignment_candidates.base_memberships(self.meta, self.document)
        self.assertEqual(set(rows), {"base", "terminal"})

    def test_stale_source_or_payload_cannot_supply_base_ownership(self):
        for mutation in ("source", "payload"):
            document = copy.deepcopy(self.document)
            if mutation == "source":
                document["source_sha256"] = "another-source"
            else:
                document["scenarios"][0]["payload_sha256"] = "another-payload"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                alignment_candidates.base_memberships(self.meta, document)

    def test_partial_duplicate_unresolved_or_contradictory_partition_is_rejected(self):
        for mutation in ("partial", "duplicate", "unresolved", "contradictory", "empty"):
            document = copy.deepcopy(self.document)
            if mutation == "partial":
                document["scenarios"].pop()
            elif mutation == "duplicate":
                document["scenarios"][1] = copy.deepcopy(document["scenarios"][0])
            elif mutation == "unresolved":
                document["totals"]["unresolved_membership_scenarios"] = 1
            elif mutation == "contradictory":
                document["scenarios"][2]["status"] = "shared"
            else:
                for row in document["scenarios"]:
                    row["status"], row["story_domains"] = "other", []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                alignment_candidates.base_memberships(self.meta, document)


if __name__ == "__main__":
    unittest.main()
