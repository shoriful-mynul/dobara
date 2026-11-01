"""Backend tests for Dobara 0.3.1.

IMPORTANT: Everything that would normally call Ollama is MOCKED here
(either by replacing main.query_model or by an httpx.MockTransport). These
tests check Dobara's own logic. They say nothing about how accurate the real
qwen3:4b model is.

Run from the project folder:
    .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import importlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
import storage  # noqa: E402
from textdiff import word_diff  # noqa: E402

ALL = "Applications are open to all undergraduate students."
FINAL_YEAR = "Applications are open only to final-year undergraduate students."
CLAIM = "All undergraduate students can apply."


def reply(earlier, current, earlier_ids=None, current_ids=None, **extra):
    """A mocked model reply (JSON text) with sensible default evidence IDs."""
    def default(status, prefix):
        return ["%s1" % prefix] if status in ("supported", "contradicted") else []
    earlier_ids = default(earlier, "E") if earlier_ids is None else earlier_ids
    current_ids = default(current, "C") if current_ids is None else current_ids
    body = {
        "earlier": {"status": earlier, "reason": "mock reason", "evidence_ids": earlier_ids},
        "current": {"status": current, "reason": "mock reason", "evidence_ids": current_ids},
    }
    body.update(extra)
    return json.dumps(body)


def payload(**overrides):
    body = {"claim": CLAIM, "earlier_source": ALL, "current_source": FINAL_YEAR}
    body.update(overrides)
    return body


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "data" / "test.sqlite3"
        patcher = patch.object(storage, "DB_PATH", self.db_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, main, "_transport", None)
        self.client = TestClient(main.app)

    def mock_model(self, text):
        patcher = patch.object(main, "query_model", new=AsyncMock(return_value=text))
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def analyze(self, model_text, **overrides):
        self.mock_model(model_text)
        return self.client.post("/analyze", json=payload(**overrides))

    def saved_ids(self):
        return [item["id"] for item in self.client.get("/comparisons").json()["comparisons"]]


class VerdictMapping(BaseCase):
    """MOCKED model replies; checks the unchanged final-verdict mapping."""

    def test_three_original_cases(self):
        cases = [
            ("supported", "supported", "still_supported"),
            ("supported", "contradicted", "contradicted"),
            ("contradicted", "contradicted", "baseline_not_supported"),
        ]
        for earlier, current, expected in cases:
            with self.subTest(earlier=earlier, current=current):
                response = self.analyze(reply(earlier, current))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["verdict"], expected)

    def test_remaining_mappings(self):
        cases = [
            ("supported", "not_found", "evidence_not_found"),
            ("supported", "uncertain", "uncertain"),
            ("uncertain", "supported", "uncertain"),
            ("not_found", "supported", "baseline_not_supported"),
            ("not_found", "not_found", "baseline_not_supported"),
        ]
        for earlier, current, expected in cases:
            with self.subTest(earlier=earlier, current=current):
                self.assertEqual(self.analyze(reply(earlier, current)).json()["verdict"], expected)

    def test_current_assessment_kept_when_baseline_not_supported(self):
        data = self.analyze(reply("contradicted", "supported")).json()
        self.assertEqual(data["verdict"], "baseline_not_supported")
        self.assertEqual(data["analysis"]["current"]["status"], "supported")

    def test_identical_sources_are_not_auto_supported(self):
        # The verdict comes only from the (mocked) model, never from text equality.
        data = self.analyze(reply("not_found", "not_found"), earlier_source=ALL, current_source=ALL).json()
        self.assertEqual(data["verdict"], "baseline_not_supported")
        self.assertFalse(data["diff"]["summary"]["changed"])

    def test_quotes_are_filled_in_by_python(self):
        data = self.analyze(reply("supported", "contradicted")).json()
        self.assertEqual(data["analysis"]["earlier"]["evidence"], [{"id": "E1", "quote": ALL}])
        self.assertEqual(data["analysis"]["current"]["evidence"], [{"id": "C1", "quote": FINAL_YEAR}])

    def test_model_cannot_supply_its_own_quote(self):
        text = json.dumps({
            "earlier": {"status": "supported", "reason": "r", "evidence_ids": ["E1"], "quote": "made up"},
            "current": {"status": "supported", "reason": "r", "evidence_ids": ["C1"]},
        })
        self.assertEqual(self.analyze(text).status_code, 502)

    def test_old_three_field_request_still_works(self):
        self.mock_model(reply("supported", "supported"))
        response = self.client.post("/analyze", json={
            "claim": CLAIM, "earlier_source": ALL, "current_source": ALL})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ("claim", "verdict", "analysis", "evidence_references_valid", "model", "elapsed_seconds"):
            self.assertIn(key, body)
        self.assertIsNone(body["saved"])
        self.assertFalse(self.db_path.exists())

    def test_health_version(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["version"], "0.3.1")
        self.assertEqual(body["app"], "Dobara")


class EvidenceValidation(BaseCase):
    """MOCKED model replies with bad evidence must never become a result or a record."""

    def assert_rejected(self, text):
        response = self.analyze(text, save=True)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.saved_ids(), [])

    def test_unknown_id(self):
        self.assert_rejected(reply("supported", "supported", earlier_ids=["E9"]))

    def test_current_id_used_for_earlier(self):
        self.assert_rejected(reply("supported", "supported", earlier_ids=["C1"]))

    def test_earlier_id_used_for_current(self):
        self.assert_rejected(reply("supported", "supported", current_ids=["E1"]))

    def test_supported_without_evidence(self):
        self.assert_rejected(reply("supported", "supported", earlier_ids=[]))

    def test_contradicted_without_evidence(self):
        self.assert_rejected(reply("supported", "contradicted", current_ids=[]))

    def test_not_found_with_evidence(self):
        self.assert_rejected(reply("supported", "not_found", current_ids=["C1"]))

    def test_too_many_ids(self):
        self.assert_rejected(reply("supported", "supported", earlier_ids=["E1"] * 5))

    def test_malformed_model_json(self):
        self.assert_rejected("this is not json")

    def test_wrong_status_value(self):
        self.assert_rejected(reply("probably", "supported"))

    def test_multi_line_sources_use_correct_blocks(self):
        two = ALL + "\n\n" + "Second line."
        data = self.analyze(reply("supported", "supported", earlier_ids=["E2"]), earlier_source=two).json()
        self.assertEqual(data["analysis"]["earlier"]["evidence"][0]["quote"], "Second line.")


class OllamaErrors(BaseCase):
    """Uses an httpx.MockTransport instead of a real Ollama server (MOCK)."""

    def run_with(self, handler, **overrides):
        main._transport = httpx.MockTransport(handler)
        return self.client.post("/analyze", json=payload(save=True, **overrides))

    def test_unreachable(self):
        def handler(request):
            raise httpx.ConnectError("refused")
        response = self.run_with(handler)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.saved_ids(), [])

    def test_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("slow")
        response = self.run_with(handler)
        self.assertEqual(response.status_code, 504)
        self.assertEqual(self.saved_ids(), [])

    def test_http_error(self):
        response = self.run_with(lambda request: httpx.Response(500, text="boom"))
        self.assertEqual(response.status_code, 502)
        self.assertIn("HTTP 500", response.json()["detail"])
        self.assertEqual(self.saved_ids(), [])

    def test_non_json_body(self):
        response = self.run_with(lambda request: httpx.Response(200, text="<html>"))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.saved_ids(), [])

    def test_missing_message_field(self):
        response = self.run_with(lambda request: httpx.Response(200, json={"oops": 1}))
        self.assertEqual(response.status_code, 502)

    def test_request_goes_to_local_ollama_with_expected_shape(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"message": {"content": reply("supported", "supported")}})
        response = self.run_with(handler, earlier_source="a\nb")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["url"], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(seen["body"]["model"], "qwen3:4b")
        enum = seen["body"]["format"]["properties"]["earlier"]["properties"]["evidence_ids"]["items"]["enum"]
        self.assertEqual(enum, ["E1", "E2"])
        self.assertNotIn("save", json.dumps(seen["body"]["messages"][1]["content"]))


class SavingAndHistory(BaseCase):
    def test_not_saved_by_default_or_when_false(self):
        self.mock_model(reply("supported", "contradicted"))
        for extra in ({}, {"save": False}):
            response = self.client.post("/analyze", json=payload(**extra))
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.json()["saved"])
        self.assertFalse(self.db_path.exists())
        self.assertEqual(self.saved_ids(), [])

    def test_explicit_save_and_reload(self):
        response = self.analyze(
            reply("supported", "contradicted"),
            save=True, title="Scholarship page", source_url="https://example.com/page")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        saved = body["saved"]
        self.assertRegex(saved["id"], r"^[0-9a-f]{32}$")
        self.assertTrue(saved["saved_at"].endswith("+00:00"))
        self.assertIsNone(saved["parent_id"])

        listing = self.client.get("/comparisons").json()["comparisons"]
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["title"], "Scholarship page")
        self.assertEqual(listing[0]["verdict"], "contradicted")

        loaded = self.client.get("/comparisons/" + saved["id"]).json()
        self.assertEqual(loaded["input"], {"claim": CLAIM, "earlier_source": ALL, "current_source": FINAL_YEAR})
        result = loaded["result"]
        self.assertEqual(result["verdict"], "contradicted")
        self.assertEqual(result["analysis"], body["analysis"])
        self.assertEqual(result["model"], "qwen3:4b")
        self.assertEqual(result["title"], "Scholarship page")
        self.assertEqual(result["source_url"], "https://example.com/page")
        self.assertEqual(result["saved"]["id"], saved["id"])
        self.assertTrue(result["diff"]["summary"]["changed"])

    def test_loading_a_saved_record_does_not_call_the_model(self):
        mocked = self.mock_model(reply("supported", "supported"))
        saved = self.client.post("/analyze", json=payload(save=True)).json()["saved"]
        self.assertEqual(mocked.await_count, 1)
        self.client.get("/comparisons")
        self.client.get("/comparisons/" + saved["id"])
        self.assertEqual(mocked.await_count, 1)

    def test_client_cannot_supply_a_verdict_or_analysis(self):
        self.mock_model(reply("supported", "supported"))
        for field in ({"verdict": "still_supported"}, {"analysis": {}}, {"result": {}}):
            with self.subTest(field=list(field)):
                response = self.client.post("/analyze", json=payload(save=True, **field))
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.saved_ids(), [])

    def test_saved_verdict_is_the_computed_one(self):
        self.analyze(reply("contradicted", "supported"), save=True)
        record = self.client.get("/comparisons/" + self.saved_ids()[0]).json()
        self.assertEqual(record["result"]["verdict"], "baseline_not_supported")

    def test_newest_first(self):
        self.mock_model(reply("supported", "supported"))
        ids = [self.client.post("/analyze", json=payload(save=True, title="t%d" % i)).json()["saved"]["id"]
               for i in range(3)]
        self.assertEqual(self.saved_ids(), list(reversed(ids)))

    def test_data_survives_restart(self):
        self.mock_model(reply("supported", "supported"))
        saved = self.client.post("/analyze", json=payload(save=True)).json()["saved"]
        importlib.reload(storage)  # a fresh module state, as after restarting the app
        with patch.object(storage, "DB_PATH", self.db_path):
            self.assertEqual([r["id"] for r in storage.list_comparisons()], [saved["id"]])
        with closing_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM comparisons").fetchone()[0], 1)

    def test_missing_record_gives_404(self):
        response = self.client.get("/comparisons/" + "0" * 32)
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_parameterized_queries_handle_hostile_ids(self):
        response = self.client.get("/comparisons/x' OR '1'='1")
        self.assertEqual(response.status_code, 404)

    def test_hostile_text_is_stored_verbatim(self):
        text = '<img src=x onerror=alert(1)> & "quotes" \'; DROP TABLE comparisons;--'
        self.mock_model(reply("supported", "supported"))
        saved = self.client.post("/analyze", json=payload(
            save=True, claim=text, earlier_source=text, current_source=text, title=text)).json()["saved"]
        record = self.client.get("/comparisons/" + saved["id"]).json()
        self.assertEqual(record["input"]["claim"], text)
        self.assertEqual(record["result"]["analysis"]["earlier"]["evidence"][0]["quote"], text)
        self.assertEqual(len(self.saved_ids()), 1)


class RecheckAndLinking(BaseCase):
    def test_recheck_creates_separate_linked_record_and_leaves_baseline_alone(self):
        self.mock_model(reply("supported", "supported"))
        first = self.client.post("/analyze", json=payload(
            save=True, title="v1", earlier_source=ALL, current_source=ALL)).json()["saved"]
        before = self.client.get("/comparisons/" + first["id"]).json()

        # The UI's "use current as next baseline" action: earlier := saved current text,
        # new current text supplied by the user, parent_id := the saved record.
        second = self.client.post("/analyze", json=payload(
            save=True, title="v2", earlier_source=before["input"]["current_source"],
            current_source=FINAL_YEAR, parent_id=first["id"])).json()["saved"]

        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(second["parent_id"], first["id"])
        self.assertEqual(self.client.get("/comparisons/" + first["id"]).json(), before)
        self.assertIsNone(before["result"]["saved"]["parent_id"])
        self.assertEqual(len(self.saved_ids()), 2)
        child = self.client.get("/comparisons/" + second["id"]).json()
        self.assertEqual(child["input"]["earlier_source"], ALL)
        self.assertEqual(child["input"]["current_source"], FINAL_YEAR)
        self.assertEqual(child["result"]["saved"]["parent_id"], first["id"])

    def test_parent_id_ignored_when_not_saving(self):
        self.mock_model(reply("supported", "supported"))
        first = self.client.post("/analyze", json=payload(save=True)).json()["saved"]
        response = self.client.post("/analyze", json=payload(parent_id=first["id"]))
        self.assertIsNone(response.json()["saved"])
        self.assertEqual(len(self.saved_ids()), 1)

    def test_missing_parent_saves_unlinked_with_warning(self):
        response = self.analyze(reply("supported", "supported"), save=True, parent_id="f" * 32)
        body = response.json()
        self.assertIsNone(body["saved"]["parent_id"])
        self.assertIn("no link", body["save_warning"])

    def test_deleting_parent_leaves_child_intact(self):
        self.mock_model(reply("supported", "supported"))
        parent = self.client.post("/analyze", json=payload(save=True, title="parent")).json()["saved"]
        child = self.client.post("/analyze", json=payload(
            save=True, title="child", parent_id=parent["id"])).json()["saved"]
        before = self.client.get("/comparisons/" + child["id"]).json()
        self.assertEqual(self.client.delete("/comparisons/" + parent["id"]).status_code, 200)
        after = self.client.get("/comparisons/" + child["id"])
        self.assertEqual(after.status_code, 200)
        after = after.json()
        self.assertIsNone(after["result"]["saved"]["parent_id"])
        self.assertEqual(after["input"], before["input"])
        self.assertEqual(after["result"]["analysis"], before["result"]["analysis"])
        self.assertEqual(self.saved_ids(), [child["id"]])


class Deletion(BaseCase):
    def test_delete_one_record_only(self):
        self.mock_model(reply("supported", "supported"))
        a = self.client.post("/analyze", json=payload(save=True, title="a")).json()["saved"]["id"]
        b = self.client.post("/analyze", json=payload(save=True, title="b")).json()["saved"]["id"]
        self.assertEqual(self.client.delete("/comparisons/" + a).json(), {"deleted": a})
        self.assertEqual(self.saved_ids(), [b])
        self.assertEqual(self.client.get("/comparisons/" + a).status_code, 404)

    def test_delete_missing_record(self):
        self.assertEqual(self.client.delete("/comparisons/" + "a" * 32).status_code, 404)

    def test_delete_twice(self):
        self.mock_model(reply("supported", "supported"))
        a = self.client.post("/analyze", json=payload(save=True)).json()["saved"]["id"]
        self.assertEqual(self.client.delete("/comparisons/" + a).status_code, 200)
        self.assertEqual(self.client.delete("/comparisons/" + a).status_code, 404)


class DatabaseFailures(BaseCase):
    def test_save_failure_keeps_result_and_warns(self):
        blocker = Path(self.tmp.name) / "blocker"
        blocker.write_text("a file, not a folder")
        with patch.object(storage, "DB_PATH", blocker / "dobara.sqlite3"):
            response = self.analyze(reply("supported", "supported"), save=True)
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertIsNone(body["saved"])
            self.assertIn("could not be saved", body["save_warning"])
            self.assertEqual(body["verdict"], "still_supported")
            listing = self.client.get("/comparisons")
            self.assertEqual(listing.status_code, 500)
            self.assertNotIn(str(blocker), listing.text)  # no internal paths leaked

    def test_corrupt_database_file(self):
        self.db_path.parent.mkdir(parents=True)
        self.db_path.write_bytes(b"this is not a sqlite database" * 50)
        response = self.client.get("/comparisons")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "The local database could not be accessed.")

    def test_newer_schema_version_is_refused(self):
        self.db_path.parent.mkdir(parents=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA user_version = 99")
        conn.commit()
        conn.close()
        self.assertEqual(self.client.get("/comparisons").status_code, 500)

    def test_failed_save_does_not_leave_partial_record(self):
        # A result without a verdict makes the INSERT fail inside storage.
        with self.assertRaises(KeyError):
            storage.save_comparison(title=None, source_url=None, claim="c", earlier_source="e",
                                    current_source="u", result={"model": "m"})
        self.assertEqual(storage.list_comparisons(), [])


class InputValidation(BaseCase):
    def test_url_rules(self):
        self.mock_model(reply("supported", "supported"))
        bad = ["ftp://example.com/x", "javascript:alert(1)", "example.com", "https://",
               "http://exa mple.com", "https://user:pw@example.com/", "https://example.com:99999/",
               "data:text/html,hi", "//example.com"]
        for url in bad:
            with self.subTest(url=url):
                self.assertEqual(self.client.post("/analyze", json=payload(source_url=url)).status_code, 422)
        for url in ("https://example.com/a?b=c#d", "http://127.0.0.1:8000/x", "HTTPS://EXAMPLE.COM"):
            with self.subTest(url=url):
                self.assertEqual(self.client.post("/analyze", json=payload(source_url=url)).status_code, 200)

    def test_blank_optional_fields_become_none(self):
        self.mock_model(reply("supported", "supported"))
        body = self.client.post("/analyze", json=payload(title="   ", source_url="")).json()
        self.assertIsNone(body["title"])
        self.assertIsNone(body["source_url"])

    def test_length_limits_unchanged(self):
        self.mock_model(reply("supported", "supported"))
        self.assertEqual(self.client.post("/analyze", json=payload(claim="x" * 501)).status_code, 422)
        self.assertEqual(self.client.post("/analyze", json=payload(earlier_source="x" * 1501)).status_code, 422)
        self.assertEqual(self.client.post("/analyze", json=payload(current_source="x" * 1501)).status_code, 422)
        self.assertEqual(self.client.post("/analyze", json=payload(claim="x" * 500)).status_code, 200)
        self.assertEqual(self.client.post("/analyze", json=payload(title="x" * 201)).status_code, 422)

    def test_save_must_be_a_real_boolean(self):
        self.assertEqual(self.client.post("/analyze", json=payload(save="yes")).status_code, 422)

    def test_blank_required_fields_rejected(self):
        self.assertEqual(self.client.post("/analyze", json=payload(claim="   ")).status_code, 422)


class WordDiff(unittest.TestCase):
    def words(self, diff, *ops):
        return " ".join(s["text"] for s in diff["segments"] if s["op"] in ops).split()

    def test_unchanged_text(self):
        diff = word_diff(ALL, ALL)
        self.assertEqual(diff["segments"], [{"op": "equal", "text": ALL}])
        self.assertEqual(diff["summary"], {"changed": False, "removed_words": 0, "added_words": 0})

    def test_changed_text(self):
        diff = word_diff(ALL, FINAL_YEAR)
        self.assertTrue(diff["summary"]["changed"])
        self.assertEqual(self.words(diff, "remove"), ["all"])
        self.assertEqual(self.words(diff, "add"), ["only", "final-year"])
        # Original words are all preserved on each side.
        self.assertEqual(self.words(diff, "equal", "remove"), ALL.split())
        self.assertEqual(self.words(diff, "equal", "add"), FINAL_YEAR.split())

    def test_additions_and_removals_only(self):
        self.assertEqual(self.words(word_diff("a b", "a b c"), "add"), ["c"])
        self.assertEqual(self.words(word_diff("a b c", "a b"), "remove"), ["c"])
        self.assertEqual(word_diff("a", "b")["summary"], {"changed": True, "removed_words": 1, "added_words": 1})

    def test_whitespace_only_differences_are_not_word_changes(self):
        self.assertFalse(word_diff("a  b\nc", "a b c")["summary"]["changed"])

    def test_html_like_text_is_preserved_as_plain_text(self):
        earlier = '<script>alert("x")</script> & <b>bold</b>'
        current = '<script>alert("y")</script> & <b>bold</b>'
        diff = word_diff(earlier, current)
        joined = "".join(s["text"] for s in diff["segments"] if s["op"] in ("equal", "remove"))
        self.assertEqual(joined, earlier)
        self.assertTrue(any("<script>" in s["text"] for s in diff["segments"]))

    def test_line_breaks_kept(self):
        diff = word_diff("one\ntwo", "one\nthree")
        self.assertEqual(diff["segments"][0], {"op": "equal", "text": "one\n"})

    def test_empty_side(self):
        self.assertEqual(word_diff("", "x")["summary"]["added_words"], 1)


class StaticFrontend(unittest.TestCase):
    """Static checks of index.html. These are NOT browser tests."""

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        start = cls.html.index("<script>") + len("<script>")
        cls.script = cls.html[start:cls.html.index("</script>")]

    def test_no_unsafe_html_insertion(self):
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(bad, self.script)

    def test_no_automatic_browser_storage(self):
        for bad in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
            self.assertNotIn(bad, self.html)

    def test_no_external_assets(self):
        import re
        self.assertEqual(re.findall(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", self.html), [])
        self.assertNotIn("@import", self.html)
        self.assertEqual(re.findall(r"url\(\s*[\"']?(?:https?:)?//", self.html), [])
        self.assertEqual(re.findall(r"<(?:link|iframe|img|script)\b[^>]*\bsrc=", self.html), [])

    def test_required_elements_and_wording(self):
        for needle in ('id="save"', "Save this comparison on this device",
                       "Use this current source as my next baseline", "Fictional examples:",
                       "Do your sources", "Print / Save as PDF", "Download JSON report"):
            self.assertIn(needle, self.html)
        self.assertNotIn("Your source changed", self.html)
        self.assertNotIn('id="save" name="save" checked', self.html)

    def test_every_getElementById_target_exists(self):
        import re
        ids = set(re.findall(r'\bid="([^"]+)"', self.html))
        used = set(re.findall(r'\bel\("([^"]+)"\)', self.script))
        used |= {m for m in re.findall(r'getElementById\("([^"]+)"\)', self.script)}
        # el(field.id + "-count") style lookups are covered by the three -count ids.
        self.assertEqual(sorted(used - ids), [])

    def test_served_by_backend(self):
        client = TestClient(main.app)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dobara", response.text)


class closing_connection:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        self.conn.close()


if __name__ == "__main__":
    unittest.main()
