# Dobara 0.3.1

**Do your sources still support your claim?**

Dobara compares a claim you wrote against an earlier and a current source excerpt using local `qwen3:4b` through Ollama. It shows original evidence passages and leaves the final judgement to you. It does not establish universal factual truth, authenticate pasted text, or fetch a supplied source URL.

## Why Dobara exists

A scholarship notice changes its eligibility rules. A researcher updates a source. A writer's original citation no longer says what it used to say. The claim based on the earlier text can remain in circulation.

Dobara helps students, writers and researchers take a second look: paste the claim and two source excerpts, inspect the evidence, then record your own decision about what needs to change.

It works with excerpts you supply. It does not monitor websites or retrieve historical versions.

## Ghost in the Machine

Built for the Hacktoberfest Open-Source AI Challenge, Week 4, Dobara interprets the theme as the ghost of old evidence: an outdated source can continue to haunt a claim after its wording changes. Comparing the earlier and current excerpts makes that lingering assumption visible.

## Why open AI matters

The core assessment runs through an open-weight Qwen3 model using local Ollama inference. Source excerpts can be assessed on your own computer without sending them to a hosted model provider. Python checks the model's evidence references and constructs quotations from the supplied text.

The application code is available under MIT, so others can inspect how verdicts are derived and adapt the workflow. Model weights are downloaded separately and retain their own licence. Initial setup needs downloads; disconnected operation still needs a manual check on the target machine.

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

## Run locally on Windows

You need Python, Git and [Ollama](https://ollama.com/download) installed. The developer's laptop has 16 GB RAM and Intel UHD graphics; performance will depend on your hardware, model state and input length. Automated checks used Python 3.12.14; see [TESTING.md](TESTING.md) for the test environment and boundaries.

### 1. Get the project

Open a PowerShell terminal, including the terminal inside VS Code:

```powershell
git clone https://github.com/shoriful-mynul/dobara.git
cd dobara
```

Alternatively, download and extract the repository ZIP, then open a terminal in the extracted folder containing `main.py`.

### 2. Install Python dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

These commands use the environment's Python directly, so activating the environment is optional.

### 3. Download the model

Start the Ollama application, then run:

```powershell
ollama pull qwen3:4b
ollama list
```

Confirm that `qwen3:4b` appears in the list. The model is a separate download and is not included in this repository. Dobara does not install it automatically.

### 4. Start Dobara

From the project folder:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Keep this terminal open and visit [http://127.0.0.1:8000](http://127.0.0.1:8000). Stop the server with Ctrl+C.

Use the app through this address rather than double-clicking `static/index.html`. If you updated an existing installation and see the old page, press Ctrl+F5. The **Backend reachable** badge confirms that the web server answered; it does not establish that Ollama or the model is ready.

### 5. Try the fictional examples

| Example | Expected overall verdict |
| --- | --- |
| Unchanged | `still_supported` |
| Eligibility changed | `contradicted` |
| Unsupported baseline | `baseline_not_supported` |

These are smoke checks, not an accuracy benchmark. Read the passages and reasoning even when the displayed verdict matches the expectation.

## If something does not work

- **Ollama cannot be reached:** confirm the Ollama application is running. Dobara uses its local endpoint at `http://127.0.0.1:11434`.
- **Model missing:** run `ollama list`, then `ollama pull qwen3:4b` if needed.
- **Page will not open:** check that Uvicorn is still running and that you opened port 8000.
- **Analysis takes time:** local inference can be slow, especially with a cold model or CPU inference. Check the terminal for errors before retrying.
- **Model or evidence error:** the comparison has not completed successfully. Review the error, check Ollama, and retry; do not treat the error as a verdict.

## Save, recheck and review

1. Enter a claim and two source excerpts, or use a fictional example. Title and source URL are optional; the URL is metadata only.
2. Tick **Save this comparison on this device** to retain a successful result. This is off by default when the page opens.
3. Open a saved record without running the model again.
4. **Use this current source as my next baseline** copies its current excerpt to the earlier field and clears the new current field. A subsequent saved comparison is a separate linked record. The old record is not overwritten.
5. On a saved comparison, use **Your review**: Not reviewed, Keep claim, Revise claim, or Find more evidence; add an optional note up to 500 characters and click **Save review**.

Review updates never run the model or change its verdict, source excerpts or evidence. Reopening a record or restarting the app retains its saved review. A new linked comparison starts unreviewed; decisions are not inherited. Deleting a comparison also deletes its review, while child comparisons remain with a cleared parent link.

A failed review save retains your typed note. Only explicitly saved reviewer information is exported; unsaved note edits are not included. Review-update timestamps use the server's UTC clock, not a source publication or capture time.

## Reports

Download JSON for exact submitted inputs, results, evidence and saved reviewer information. **Print / Save as PDF** produces a readable report; choose Save as PDF in your browser's print dialog. The form and history are excluded from printing. Check your browser's print preview for clipped text or page breaks. Automated report-content checks do not establish visual layout or PDF pagination.

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

Offline inference needs installed dependencies, local assets and model weights. Test a new comparison with internet disconnected before claiming offline operation. The main app has local assets; `/docs` separately loads Swagger assets externally. Requirements are unpinned; tested versions are in [TESTING.md](TESTING.md).

## Tests

The release's recorded automated checks include 80 passing backend/static tests and a passing optional DOM interaction script. They check application behavior with mocked inference; they do not measure Qwen3's accuracy. See [TESTING.md](TESTING.md) for details and manual acceptance checks.


```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py storage.py textdiff.py tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests use temporary databases and mocked inference, not your saved comparisons. No Ollama is required. Optional DOM tests and remaining manual checks are documented in [TESTING.md](TESTING.md).

## Credits and licence

Original Dobara code: Copyright 2026 Shoriful Islam, MIT licence ([LICENSE](LICENSE)). Development assistance: ChatGPT/Codex (OpenAI) and Claude (Anthropic).

FastAPI, Uvicorn, HTTPX, Pydantic, Ollama and Python's standard library retain their own licences. Default Qwen3 4B is from Alibaba's Qwen team, runs through Ollama, is not bundled and retains its own licence terms. jsdom is used only for optional development tests, not by the application.
