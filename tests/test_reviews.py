"""Reviewer storage/API tests. Inference uses the same explicit mocks as the base suite."""

import importlib
import json
import sqlite3
from unittest.mock import patch

import test_backend as fixtures
import main
import storage


class ReviewerTests(fixtures.BaseCase):
    def saved_record(self, **extra):
        self.mock_model(fixtures.reply("supported", "contradicted"))
        response = self.client.post("/analyze", json=fixtures.payload(save=True, **extra))
        self.assertEqual(response.status_code, 200)
        return response.json()["saved"]["id"]

    def put_review(self, record_id, decision="revise_claim", note="Use final-year instead of all."):
        return self.client.put(
            f"/comparisons/{record_id}/review",
            json={"decision": decision, "note": note},
        )

    def test_default_review_is_unsaved_and_unreviewed(self):
        record_id = self.saved_record()
        review = self.client.get(f"/comparisons/{record_id}").json()["result"]["review"]
        self.assertEqual(review, {"decision": "not_reviewed", "note": "", "updated_at": None})
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)

    def test_unsaved_analysis_has_no_persistent_review(self):
        self.mock_model(fixtures.reply("supported", "supported"))
        body = self.client.post("/analyze", json=fixtures.payload()).json()
        self.assertIsNone(body["review"])
        self.assertFalse(self.db_path.exists())

    def test_save_reload_and_update_review(self):
        record_id = self.saved_record()
        first = self.put_review(record_id).json()["review"]
        self.assertEqual(first["decision"], "revise_claim")
        self.assertTrue(first["updated_at"].endswith("+00:00"))
        loaded = self.client.get(f"/comparisons/{record_id}").json()["result"]
        self.assertEqual(loaded["review"], first)
        second = self.put_review(record_id, "keep_claim", "Reviewed manually.")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["review"]["decision"], "keep_claim")
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 1)

    def test_review_survives_module_reload(self):
        record_id = self.saved_record()
        review = self.put_review(record_id).json()["review"]
        importlib.reload(storage)
        with patch.object(storage, "DB_PATH", self.db_path):
            loaded = self.client.get(f"/comparisons/{record_id}").json()
        self.assertEqual(loaded["result"]["review"], review)

    def test_review_never_calls_model_or_changes_original_record(self):
        model = self.mock_model(fixtures.reply("supported", "contradicted"))
        record_id = self.client.post("/analyze", json=fixtures.payload(save=True)).json()["saved"]["id"]
        with sqlite3.connect(self.db_path) as conn:
            before = conn.execute("SELECT * FROM comparisons WHERE id=?", (record_id,)).fetchone()
        self.assertEqual(self.put_review(record_id).status_code, 200)
        self.client.get(f"/comparisons/{record_id}")
        self.assertEqual(model.await_count, 1)
        with sqlite3.connect(self.db_path) as conn:
            after = conn.execute("SELECT * FROM comparisons WHERE id=?", (record_id,)).fetchone()
        self.assertEqual(before, after)

    def test_invalid_decision_rejected_without_review_row(self):
        record_id = self.saved_record()
        self.assertEqual(self.put_review(record_id, "automatically_verified").status_code, 422)
        self.assertIsNone(self.client.get(f"/comparisons/{record_id}").json()["result"]["review"]["updated_at"])

    def test_note_limit_and_exact_unicode_storage(self):
        record_id = self.saved_record()
        self.assertEqual(self.put_review(record_id, note="x" * 501).status_code, 422)
        note = "  মানুষের সিদ্ধান্ত।\n<img onerror=alert(1)> & 'quoted'  "
        response = self.put_review(record_id, note=note)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["review"]["note"], note)
        self.assertEqual(self.put_review(record_id, note="x" * 500).status_code, 200)

    def test_server_fields_and_extra_fields_cannot_be_supplied(self):
        record_id = self.saved_record()
        for extra in ({"updated_at": "forged"}, {"verdict": "still_supported"}):
            body = {"decision": "keep_claim", "note": "", **extra}
            self.assertEqual(self.client.put(f"/comparisons/{record_id}/review", json=body).status_code, 422)

    def test_missing_comparison_returns_404(self):
        self.assertEqual(self.put_review("0" * 32).status_code, 404)

    def test_delete_cleans_review_and_keeps_child(self):
        parent = self.saved_record()
        child = self.saved_record(parent_id=parent)
        self.put_review(parent)
        self.put_review(child, "find_more_evidence", "Child note")
        self.assertEqual(self.client.delete(f"/comparisons/{parent}").status_code, 200)
        record = self.client.get(f"/comparisons/{child}").json()
        self.assertIsNone(record["result"]["saved"]["parent_id"])
        self.assertEqual(record["result"]["review"]["note"], "Child note")
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reviews WHERE comparison_id=?", (parent,)).fetchone()[0], 0)

    def test_new_recheck_does_not_inherit_a_review(self):
        parent = self.saved_record()
        self.put_review(parent)
        child = self.saved_record(parent_id=parent)
        record = self.client.get(f"/comparisons/{child}").json()
        self.assertEqual(record["result"]["review"]["decision"], "not_reviewed")
        self.assertIsNone(record["result"]["review"]["updated_at"])

    def test_history_shows_saved_review_decision(self):
        record_id = self.saved_record()
        self.put_review(record_id, "find_more_evidence")
        listing = self.client.get("/comparisons").json()["comparisons"]
        self.assertEqual(listing[0]["review_decision"], "find_more_evidence")

    def test_failed_review_write_keeps_existing_note(self):
        record_id = self.saved_record()
        original = self.put_review(record_id, note="Original note").json()["review"]
        with patch.object(storage, "save_review", side_effect=storage.StorageError("private details")):
            response = self.put_review(record_id, note="New unsaved note")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private details", response.text)
        loaded = self.client.get(f"/comparisons/{record_id}").json()
        self.assertEqual(loaded["result"]["review"], original)

    def test_direct_storage_checks_invalid_review(self):
        record_id = self.saved_record()
        for decision, note in (("invalid", ""), ("keep_claim", "x" * 501)):
            with self.assertRaises(ValueError):
                storage.save_review(record_id, decision=decision, note=note)

    def test_optional_table_preserves_legacy_schema_contract(self):
        record_id = self.saved_record()
        self.put_review(record_id)
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(comparisons)")]
        self.assertEqual(columns, ["id", "parent_id", "title", "source_url", "claim", "earlier_source", "current_source", "result_json", "verdict", "model", "saved_at"])

    def test_upgrade_existing_v030_database_without_review_table(self):
        # Simulate the actual prior file: its original rows and user_version=1,
        # with no reviews helper table. All of this is in a temporary database.
        parent = self.saved_record()
        child = self.saved_record(parent_id=parent)
        with sqlite3.connect(self.db_path) as conn:
            before = conn.execute("SELECT * FROM comparisons ORDER BY id").fetchall()
            conn.execute("DROP TABLE reviews")
        loaded = self.client.get(f"/comparisons/{child}")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["result"]["review"], storage.empty_review())
        self.assertEqual(loaded.json()["result"]["saved"]["parent_id"], parent)
        self.assertEqual(self.put_review(child).status_code, 200)
        with sqlite3.connect(self.db_path) as conn:
            after = conn.execute("SELECT * FROM comparisons ORDER BY id").fetchall()
        self.assertEqual(before, after)

    def test_review_reset_is_an_explicit_saved_update(self):
        record_id = self.saved_record()
        self.put_review(record_id)
        response = self.put_review(record_id, "not_reviewed", "")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["review"]["decision"], "not_reviewed")
        self.assertIsNotNone(response.json()["review"]["updated_at"])
