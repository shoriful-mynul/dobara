# Testing Dobara 0.3.1

## Checks actually run in this update

Linux, Python 3.12.14; FastAPI 0.162.0, Starlette 1.10.0, Uvicorn 0.54.0, HTTPX 0.28.1 and Pydantic 2.14.2. Your Windows versions may differ.

- **80 backend/static tests passed:** the original 63 tests, with only the legitimate health-version assertion updated, plus 17 reviewer tests. They cover evidence validation, verdict mapping, opt-in saving, linked rechecks, deletion, errors, input validation, deterministic differences, reviewer defaults and updates, note validation, forbidden fields, missing records, persistence, no inference on review, immutable comparison rows, cascade cleanup, history summaries, failed writes and old-database compatibility.
- **DOM interaction script passed:** saving, loading, rechecking, saved reviewer notes, JSON export and print-report content, retained drafts after failed saves, no-inference review updates, safe text rendering, delayed-load control locking, stale history response suppression, deletion and error recovery. API responses are mocked.
- **Actual legacy-code compatibility check passed:** a database created by the original 0.3.0 storage module was opened and reviewed with 0.3.1. Original comparison rows were unchanged. The original storage module could still read and delete comparisons afterwards; child records and their reviews remained valid after parent deletion.
- **Core preservation check passed:** AST comparisons verified that the model prompt and make_blocks, resolve_evidence, final_verdict, build_payload and query_model functions are unchanged from 0.3.0.
- Python syntax and ZIP integrity are checked during packaging. No databases, environments, model weights or caches are included.

## Boundaries

Automated inference tests use canned replies or HTTPX mock transports. They verify application behavior, not model accuracy. Backend reviewer/storage tests use real temporary SQLite databases.

DOM tests execute JavaScript in jsdom, not a visual browser. They use mocked API responses and verify state transitions and report content, not pixel layout, accessibility or PDF pagination.

This build has **not** been tested on Windows, with real Ollama inference, with internet disconnected, or in a rendered browser/real print dialog. Previous-package visual-test claims are not verification of this update.

On the user's laptop, the original examples and saved linked recheck worked under 0.3.0. A screenshot showed one 8.26-second saved result; it is not a benchmark average. Repeat UPDATE.md's checks on the laptop.

## Backend tests

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py storage.py textdiff.py tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use temporary databases, never your saved data. Expected negative tests can log generic database error classes; a Starlette/httpx deprecation warning can appear. Check the final unittest result.

## Optional frontend DOM tests

For developers with Node.js and jsdom already available:

```text
node tests/test_frontend.cjs
```

The script accepts DOBARA_JSDOM_MODULE as a path to an existing jsdom installation. Node and jsdom are not app dependencies and are not required to run Dobara.

## Manual acceptance

1. Confirm v0.3.1 and existing saved comparisons.
2. Save a human review, reopen it, restart, and confirm it remains without inference.
3. Check saved review details in JSON and print preview, separately from the AI assessment. Unsaved note edits must not be exported.
4. Check print preview for clipped evidence.
5. Repeat the three original samples with qwen3:4b.
6. Recheck from a baseline; the original stays unchanged and the new record starts unreviewed.
7. Before claiming offline use, perform a new comparison with the internet disconnected.

An empty database may be initialized when history is read. Comparison rows require opt-in saving; reviewer rows require explicit Save review.
