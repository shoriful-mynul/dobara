# Update a working Windows installation to Dobara 0.3.1

1. Stop Uvicorn with Ctrl+C.
2. Back up the current code and entire data folder. The ZIP contains no database.

From `D:\Dobara`, create a timestamped backup without copying `.venv`:

```powershell
Set-Location D:\Dobara
$dobaraBackupPath = "D:\Dobara_backup_" + (Get-Date -Format "yyyyMMdd_HHmmss")
New-Item -ItemType Directory -Path $dobaraBackupPath | Out-Null
Copy-Item main.py, storage.py, textdiff.py, requirements.txt, README.md -Destination $dobaraBackupPath
Copy-Item static -Destination $dobaraBackupPath -Recurse
if (Test-Path data) { Copy-Item data -Destination $dobaraBackupPath -Recurse }
Write-Output $dobaraBackupPath
```

3. Extract Dobara_v0.3.1.zip separately. Copy all files and folders INSIDE it into `D:\Dobara`, replacing matching source files. Keep `.venv`, `check_model.py`, and `data`. There is no extra enclosing folder.
4. No new production package is required. Only if a dependency is missing:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

5. Run tests; they use temporary data and mocked inference:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

6. Keep Ollama running and start:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

7. Open http://127.0.0.1:8000 and press Ctrl+F5. Confirm v0.3.1.
8. Open an existing saved comparison, select Revise claim, add a note and click Save review. Reopen it and check the note remains. This must not run the model.
9. Inspect `reviewer_review` in JSON export and the separate human review section in print preview.
10. Restart the app and confirm earlier comparisons and notes remain.

## Real-model smoke check

Run Unchanged, Eligibility changed and Unsupported baseline. Expected verdicts: still_supported, contradicted, baseline_not_supported. The prompt and core logic are unchanged, but this release has not been run against your local model in the build environment.

## Rollback

Stop the server, restore the earlier code from your backup and restart. Original comparison columns and schema version remain unchanged; 0.3.0 reads comparisons and ignores the optional review table. If restoring a database backup too, do so only with the server stopped; it restores data to that backup's point in time.
