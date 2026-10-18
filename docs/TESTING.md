# Testing and Reproduction Checks

Run commands from the project root using the same Conda environment as the model. The commands below use PowerShell.

## Preconditions

- Project dependencies are installed and `python -m pip check` has been reviewed.
- The trained pipeline, metadata, reports, and generated demo files exist.
- PostgreSQL is loaded, and `sql/4_review_events.sql` has been applied in `fraud_detection_database`.
- The FastAPI service is running for the live dashboard and review tests.
- API and test terminals use the same database settings and loaded model version.

The tests do not train a model. A clean clone must generate the artifacts before running artifact-dependent tests.

## Fast local checks

Check Python syntax with the actual project interpreter:

```powershell
python --version
python -m compileall -q src api app tests
```

`compileall` checks syntax and may create `__pycache__` directories. Those directories are generated files and are excluded from the public repository.

Run the core, artifact, and API checks:

```powershell
python -m pytest tests/test_core.py tests/test_outputs.py tests/test_api.py -q -rs
```

API tests use `TestClient` and load the app within the test process. They do not require a separately running Uvicorn server.

## Full integration configuration

Start the API in terminal A:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Keep PostgreSQL and terminal A running. In terminal B, activate the same environment and run:

```powershell
$env:RUN_DATABASE_TESTS = "1"
$env:FRAUD_LIVE_TESTS = "1"
python -m pytest -q -rs --tb=short --junitxml=reports/test_results.xml
```

The current suite has 26 test cases when parametrized inputs are counted. The supplied `reports/test_results.xml` records 26 tests with zero failures, errors, or skipped tests. It is the submitted local-run result, not evidence of a new run on another machine. Treat the command's actual output as the result; this document is not a certificate that a particular checkout has passed. For the full configuration, investigate failures and unexpected skipped tests before marking it complete.

| Test file | What it verifies |
|---|---|
| `test_core.py` | Time boundaries, training-only preprocessing, metric arithmetic, tie handling, and source ID validation |
| `test_api.py` | Valid requests, six invalid input cases, explicit nulls, unseen categories, three offline/online comparisons, and SHAP reconstruction |
| `test_database.py` | Live SQL quality checks, row-count reconciliation, duplicate rejection, and invalid-label rejection |
| `test_dashboard.py` | Clear behavior when the API is unavailable, live scoring, saved review read-back, and retrieval in a fresh Streamlit test session |
| `test_reviews.py` | Committed database writes, preservation of earlier entries, API history/latest reads, and HTTP 422 for an invalid action without a database change |
| `test_outputs.py` | Artifact/configuration/source consistency, reporting export reconciliation, and split/audit checks |

The database test uses savepoints to roll back deliberately invalid insert attempts. The review tests remove only the review IDs that they create. The live dashboard test leaves its submitted `Escalate` entry in the demo history. Tests must use the dedicated project database. Avoid submitting manual decisions for the same transaction while these tests run. Identity sequences can have gaps after test cleanup; gaps are not missing history records.

To run one integration group:

```powershell
python -m pytest tests/test_database.py -q -rs
python -m pytest tests/test_dashboard.py -q -rs
python -m pytest tests/test_reviews.py -q -rs --tb=short
```

These commands use the flags already set in terminal B.

## Skipped tests and shell differences

The database, live dashboard, and review tests are opt-in. `test_reviews.py` requires both integration flags to be `1`. With both flags unset, the present suite skips four integration cases; skipped cases are not passes. In PowerShell, `set NAME=1` is not the CMD environment-variable assignment syntax you need. Check the effective values with:

```powershell
python -c "import os; print('RUN_DATABASE_TESTS:', repr(os.getenv('RUN_DATABASE_TESTS'))); print('FRAUD_LIVE_TESTS:', repr(os.getenv('FRAUD_LIVE_TESTS')))"
```

Both values must be `'1'` for the full configuration. `None` means the variable is not visible to that Python process. Variables set in one terminal are not automatically applied to another existing terminal.

If using Anaconda Prompt/CMD instead of PowerShell, use:

```bat
set RUN_DATABASE_TESTS=1
set FRAUD_LIVE_TESTS=1
python -m pytest -q -rs --tb=short --junitxml=reports/test_results.xml
```

## Warnings

The tested workflow has emitted two compatibility warnings:

| Warning | Meaning and follow-up |
|---|---|
| Starlette deprecates `httpx` for `TestClient` | The current environment still runs the tests. Review a migration to `httpx2` as a deliberate dependency change, update the dependency declaration, and rerun API tests. |
| Pandas warns about downcasting in `replace` | Missing-value conversion currently relies on behavior scheduled to change. Make dtype handling explicit when updating this code and verify predictions remain consistent. |

Warnings are different from failed assertions. Do not globally suppress warnings to imply compatibility. Changing `src/inference.py` also changes a recorded source hash, so account for artifact consistency when performing that maintenance.

References: [Starlette TestClient](https://www.starlette.io/testclient/) and [pandas downcasting changes](https://pandas.pydata.org/docs/whatsnew/v2.2.0.html).

## Diagnose an artifact consistency failure

List all source checks without changing any file:

```powershell
python -c "from src.common import ROOT, read_json, sha256; m = read_json(ROOT / 'models/metadata.json'); print('\n'.join(('OK       ' if sha256(ROOT / n) == h else 'DIFFERENT ') + n for n, h in m['source_sha256'].items()))"
```

Compare the reported file with its verified training-time version. Do not assume that a mismatch proves a model defect, and do not assume that every mismatch is cosmetic. Comments, quote styles, and newline encoding also affect the checksum.

After a verified restoration, rerun the affected test:

```powershell
python -m pytest tests/test_outputs.py::test_frozen_config_sources_and_artifact_match -q
```

For an intentional source change, complete the change first and follow the controlled rebuild process in [START_HERE_ID.md](START_HERE_ID.md). Do not overwrite metadata hashes by hand.

## Application restart check

The automated checks open a new HTTP session and a fresh Streamlit test session. They do not stop and restart the separate Uvicorn process. For the manual restart check, save a decision, note its review ID, stop both local app processes, restart them, and confirm that the same entry remains. Adding another decision must preserve earlier entries. See [REVIEW_STORAGE.md](REVIEW_STORAGE.md). Do not repeat this check if it has already been completed for the current implementation.

## Before calling the MVP complete

1. Run the full integration configuration and retain its actual result.
2. Start Streamlit, verify prediction and saved review history, and complete the application restart check.
3. Restart and run all notebook cells; save outputs matching the current model version.
4. Refresh both Power BI sources and compare totals with current evaluation exports.
5. Confirm the setup instructions, `.env.example`, and requirements match the project.
6. Exclude credentials, generated caches, and raw data from public uploads. Check manual ZIP contents separately from `.gitignore`.

After the relevant checks pass, avoid repeated training or repeated tests for documentation-only changes. Rebuild or broaden testing when an actual code, data, environment, or configuration change requires it.