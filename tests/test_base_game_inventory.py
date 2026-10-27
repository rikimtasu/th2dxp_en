"""Unchanged records need explicit attributed exceptions, not translation credit."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import base_game_inventory as inventory
import project


class CoverageReviewTests(unittest.TestCase):
    @staticmethod
    def fixture(before, after, kind="translation_completeness", category=None):
        original = [{"items": [{"kind": "text", "original_text": before, "translated_text": before}]}]
        edited = copy.deepcopy(original)
        edited[0]["items"][0]["translated_text"] = after
        records = inventory.script_records("fixture.json", original, edited)
        claim = {"record_id": records[0]["id"], "review_kind": kind,
                 "original_text_sha256": project.digest(before.encode("utf-8")),
                 "translated_text_sha256": project.digest(after.encode("utf-8")),
                 "rationale": "Synthetic isolated review, not approval of a game record"}
        if category is not None:
            claim["exception_category"] = category
        return original, edited, records, claim

    @staticmethod
    def apply(fixture):
        original, edited, records, claim = fixture
        inventory.apply_record_reviews("fixture.json", original, edited, records, {claim["record_id"]: claim})
        return records[0]

    def test_unchanged_dialogue_cannot_receive_generic_translation_credit(self):
        with self.assertRaisesRegex(ValueError, "explicit name/token exception"):
            self.apply(self.fixture("これは未翻訳の文章です。", "これは未翻訳の文章です。"))

    def test_named_exceptions_cover_unchanged_names_and_tokens_without_translation_credit(self):
        for text, category in (("Konomi", "proper_name"), ("...", "nonlinguistic_token")):
            with self.subTest(category=category):
                record = self.apply(self.fixture(text, text, "unchanged_token_exception", category))
                self.assertTrue(record["coverage_complete"])
                self.assertTrue(record["verified_unchanged_exception"])
                self.assertFalse(record["verified_translation_complete"])
                self.assertEqual(record["exception_category"], category)

    def test_changed_reviewed_translation_is_not_an_unchanged_exception(self):
        record = self.apply(self.fixture("こんにちは。", "Hello."))
        self.assertTrue(record["coverage_complete"])
        self.assertTrue(record["verified_translation_complete"])
        self.assertFalse(record["verified_unchanged_exception"])

    def test_original_blank_tokens_need_explicit_nonlinguistic_exceptions(self):
        for text in ("", " ", "\u3000", "\u3000" * 20):
            with self.subTest(text=repr(text)):
                record = self.apply(self.fixture(text, text, "unchanged_token_exception",
                                                 "nonlinguistic_token"))
                self.assertTrue(record["coverage_complete"])
                self.assertTrue(record["verified_unchanged_exception"])
                self.assertFalse(record["verified_translation_complete"])

    def test_blank_exceptions_cannot_hide_deleted_language_or_literal_controls(self):
        for before, after, category in (("未翻訳です。", "", "nonlinguistic_token"),
                                         ("", "", "proper_name"),
                                         ("\n", "\n", "nonlinguistic_token")):
            with self.subTest(before=before, category=category), self.assertRaises(ValueError):
                self.apply(self.fixture(before, after, "unchanged_token_exception", category))

    def test_changed_blank_stale_and_unsupported_exception_claims_are_rejected(self):
        fixtures = [self.fixture("Konomi", "Tamaki", "unchanged_token_exception", "proper_name"),
                    self.fixture("未翻訳です。", " ", "unchanged_token_exception", "nonlinguistic_token"),
                    self.fixture("CD", "CD", "unchanged_token_exception", "dialogue")]
        stale = self.fixture("CD", "CD", "unchanged_token_exception", "nonlinguistic_token")
        stale[3]["translated_text_sha256"] = "stale"
        fixtures.append(stale)
        for ordinal, fixture in enumerate(fixtures):
            with self.subTest(case=ordinal), self.assertRaises(ValueError):
                self.apply(fixture)

    def test_unreviewed_unchanged_token_is_not_automatically_exempt(self):
        original, edited, records, claim = self.fixture("CD", "CD")
        inventory.apply_record_reviews("fixture.json", original, edited, records, {})
        self.assertFalse(records[0]["coverage_complete"])
        self.assertFalse(records[0]["verified_unchanged_exception"])

    def test_a_record_cannot_be_both_a_translation_and_an_exception(self):
        claim = self.fixture("CD", "CD")[3]
        exception = dict(claim, review_kind="unchanged_token_exception", exception_category="nonlinguistic_token")
        data = b"synthetic source"
        document = {"schema_version": 1, "source_sha256": project.digest(data),
                    "review": {"kind": "source_bound_scope_and_translation_review",
                               "reviewer": "isolated test reviewer", "rationale": "Synthetic review"},
                    "memberships": [], "translations": [claim], "unchanged_exceptions": [exception]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            project.save(path, document)
            with self.assertRaises(ValueError):
                inventory.reviewed_evidence(data, [], path)


if __name__ == "__main__":
    unittest.main()
