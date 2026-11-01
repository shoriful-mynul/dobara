# Dobara 0.3.1

**Do your sources still support your claim?**

Dobara compares a claim you wrote against an earlier and a current source excerpt using local `qwen3:4b` through Ollama. It shows original evidence passages and leaves the final judgement to you. It does not establish universal factual truth, authenticate pasted text, or fetch a supplied source URL.

## Features

- Independent earlier/current assessments: supported, contradicted, not found, uncertain.
- Source-specific evidence IDs constrained and checked by Python; quotations come from original source passages.
- Deterministic word differences, separate from AI interpretation.
- Opt-in local saving, history, deletion and linked rechecks without overwriting a saved baseline.
- Human reviewer decisions and notes, stored separately from immutable comparison inputs and model results.
- JSON export and browser printing / Save as PDF, including explicitly saved human reviews.
- Local frontend assets; controls locked during inference and saved-record operations.

## Update an existing installation

Read [UPDATE.md](UPDATE.md). Stop Uvicorn and back up the existing `data` folder before copying files. Keep your `.venv` and data. No new production dependency was added.

The update adds an optional `reviews` table. It does not alter the original `comparisons` columns or schema version 1. Existing comparisons and parent links are preserved. The actual original 0.3.0 storage module was tested reading and deleting comparisons after this update; it ignores the optional reviewer table.

## Windows setup

If starting from a new Python environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Ollama must already be installed and running with `qwen3:4b` downloaded. Dobara never installs models. From the folder containing `main.py`:

```powershell
ollama list
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and use Ctrl+F5 if an old page appears. Do not double-click `static/index.html`. The Backend reachable badge means the web server answered, not that Ollama is ready.

## Save, recheck and review

1. Enter a claim and two source excerpts, or use a fictional example. Title and source URL are optional; the URL is metadata only.
2. Tick **Save this comparison on this device** to retain a successful result. This is off by default when the page opens.
3. Open a saved record without running the model again.
4. **Use this current source as my next baseline** copies its current excerpt to the earlier field and clears the new current field. A subsequent saved comparison is a separate linked record. The old record is not overwritten.
5. On a saved comparison, use **Your review**: Not reviewed, Keep claim, Revise claim, or Find more evidence; add an optional note up to 500 characters and click **Save review**.

Review updates never run the model or change its verdict, source excerpts or evidence. Reopening a record or restarting the app retains its saved review. A new linked comparison starts unreviewed; decisions are not inherited. Deleting a comparison also deletes its review, while child comparisons remain with a cleared parent link.

A failed review save retains your typed note. Only explicitly saved reviewer information is exported; unsaved note edits are not included. Review-update timestamps use the server's UTC clock, not a source publication or capture time.

## Reports

Download JSON for exact submitted inputs, results, evidence and saved reviewer information. **Print / Save as PDF** produces a readable report; choose Save as PDF in your browser's print dialog. The form and history are excluded from printing. Check your browser's print preview for clipping; the updated layout has not been visually tested in this build environment.

## Data and privacy

Data lives at `data/dobara.sqlite3` beside the app, for example `D:\Dobara\data\dobara.sqlite3`.

An empty database and tables may be initialized when history is read. Comparison content is stored only after successful analysis with Save selected. Reviewer rows are written only through an explicit Save review action.

- SQLite data is not encrypted by Dobara. Someone with access to these files may read it.
- The browser uses no localStorage/sessionStorage for inputs and loads no external frontend assets.
- Text goes to the local backend and local Ollama endpoint. Dobara does not fetch source URLs or use hosted inference.
- Routine logs do not include claim, source or reviewer-note text.
- Stop the app before copying `data` for a private backup. Do not upload this folder manually to a public repository; it is excluded by `.gitignore`.

## Limits

Claim: 500 characters; each excerpt: 1500; title: 200; source URL: 500; reviewer note: 500. Each non-empty source line is one evidence passage. Comparison fields are trimmed as in 0.3.0; reviewer notes retain entered whitespace.

Valid IDs establish that evidence exists in your input, not that the model interpreted it correctly. Missing information is not contradiction. Changed wording does not automatically change support; identical wording does not automatically support a claim. Pasted text, URLs and saved timestamps are not independently authenticated snapshots.

The model prompt and core inference/evidence/verdict functions are unchanged from 0.3.0. Model accuracy beyond the user's tested examples has not been established. This is a local development prototype, not a hosted multi-user service or general fact checker.

Offline inference needs installed dependencies, local assets and model weights. Test a new comparison with internet disconnected before claiming offline operation. The main app has local assets; `/docs` separately loads Swagger assets externally. Requirements are unpinned; tested versions are in TESTING.md.

## Tests

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py storage.py textdiff.py tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests use temporary databases and mocked inference, not your saved comparisons. No Ollama is required. Optional DOM tests and remaining manual checks are documented in [TESTING.md](TESTING.md).

## Credits and licence

Original Dobara code: Copyright 2026 Shoriful Islam, MIT licence ([LICENSE](LICENSE)). Development assistance: ChatGPT/Codex (OpenAI) and Claude (Anthropic).

FastAPI, Uvicorn, HTTPX, Pydantic, Ollama and Python's standard library retain their own licences. Default Qwen3 4B is from Alibaba's Qwen team, runs through Ollama, is not bundled and retains its own licence terms. jsdom is used only for optional development tests, not by the application.
