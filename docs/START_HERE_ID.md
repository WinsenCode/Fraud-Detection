# Setup and Run Guide

This guide uses Windows, Conda, Python 3.10.9, local PostgreSQL, and the PowerShell terminal in VS Code. Run all commands from the project root: the folder containing `config.json`, `requirements.txt`, `src`, and `tests`.

## 1. Choose your starting point

| Project state | Start here |
|---|---|
| Setting up the project from the repository | Sections 2–5 |
| Model artifacts, reports, and demo data already exist | Section 4a if the review table has not been checked, then section 6 |
| Updating notebook outputs | Section 7 |
| Opening or refreshing Power BI | Section 8 |
| Running the full test suite | Section 9 |

Changes to the README, documentation, Power BI layout, or application presentation do not require repeating data preparation, database loading, or training.

## 2. Activate the environment

If you already have a compatible `machine_learning` environment:

```powershell
conda activate machine_learning
python --version
python -m pip check
```

Use Python 3.10.9 to match the recorded model environment. `pip check` detects dependency conflicts; it does not replace application tests.

For a fresh installation, create a dedicated Conda environment:

```powershell
conda create -n fraud_detection python=3.10.9
conda activate fraud_detection
python -m pip install -r requirements.txt
python -m pip check
```

Activate the same environment in every additional terminal. An existing, complete environment does not need to be recreated or have all its packages reinstalled.

`requirements.txt` must include the model dependencies and the application and test dependencies: `fastapi`, `pydantic`, `uvicorn`, `requests`, `streamlit`, `pytest`, and `httpx` for the test configuration used by this project. When loading a saved model, match the model dependency versions recorded in `models/metadata.json`. Keep requirements specific to this project rather than copying the entire package list from another project.

## 3. Prepare the folders, source data, and database

### Folders

Create these folders manually in File Explorer if they do not already exist:

- `data/raw`
- `data/processed`
- `reports/figures`
- `models`
- `powerbi/exports`

The `check_folders()` function checks that these folders exist and raises an error when a required folder is missing.

### Source data

Download the data from [IEEE-CIS Fraud Detection](https://www.kaggle.com/competitions/ieee-fraud-detection/data). Place these two files in `data/raw`, keeping their original names:

- `train_transaction.csv`
- `train_identity.csv`

The competition files `test_transaction.csv`, `test_identity.csv`, and `sample_submission.csv` are not used by this evaluation pipeline. The project's test split is a chronological holdout from the labeled training data.

### PostgreSQL

Ensure that the PostgreSQL service is running. Use a dedicated database named `fraud_detection_database`. A connection name in DBeaver is a display label; renaming a connection does not create a database.

If the database does not exist, run the following through an appropriate PostgreSQL administrative connection, outside a transaction block:

```sql
CREATE DATABASE fraud_detection_database;
```

Skip this command if the database already exists. Connect DBeaver to that database to inspect its tables and query results.

### Connection settings

Copy `.env.example` to `.env` in the project root and enter your local connection settings:

```dotenv
PGHOST=localhost
PGPORT=5432
PGDATABASE=fraud_detection_database
PGUSER=postgres
PGPASSWORD=replace_with_your_password
```

Replace the username and password with your PostgreSQL credentials. The password above is a placeholder. Keep the same database name in `.env.example`, while retaining a placeholder password there.

Loading `.env` does not override environment variables already set in the terminal. If the application connects to an unexpected database, also check the terminal's `PGDATABASE` environment variable.

## 4. Prepare and load the data

```powershell
python -m src.data prepare
python -m src.data load
```

`prepare` selects the required columns, validates the source files, and writes the prepared CSV files and a hash manifest. It retains all training rows.

`load` imports the data using `psycopg COPY`, executes the SQL steps, and writes the audit results. The code uses this sequence:

1. Run `sql/0_schema.sql`.
2. Import the transaction and identity CSV files.
3. Run `sql/1_join.sql`.
4. Run `sql/2_quality.sql`.
5. Run `sql/3_business_kpis.sql`.

Manual CSV import through DBeaver is unnecessary. To inspect quality checks manually, run `2_quality.sql` after loading has created the required tables and view.

Key outputs:

| File | Purpose |
|---|---|
| `data/processed/model_data.csv` | Joined data used for training |
| `reports/data_audit.json` | Audit status, row counts, database engine, and data hash |
| `reports/sql_quality.csv` | Results of the individual SQL checks |
| `reports/source_manifest.json` | Source files, selected columns, and hashes |

If the fraud tables already contain data, a normal `load` refuses to overwrite them. To intentionally reload the data:

```powershell
python -m src.data load --replace
```

This option empties and reloads `fraud.transactions` and `fraud.identities` in the configured database. Confirm the connection settings before using it. Resolve the cause of an unexpected error before choosing to replace existing data.

## 4a. Create the review table

Complete this step after the transaction data has been loaded and before starting the investigation dashboard or review integration tests. `python -m src.data load` does not execute SQL step 4.

1. Open DBeaver and select the connection to `fraud_detection_database`.
2. Run `SELECT current_database();` and confirm the returned database name.
3. Open `sql/4_review_events.sql` from this project.
4. Execute the entire SQL script. Commit if your DBeaver connection uses manual transactions.
5. Follow the schema query in [REVIEW_STORAGE.md](REVIEW_STORAGE.md). The intended table has four columns: `review_id`, `transaction_id`, `model_version`, and `action`.

If that table already exists with the intended columns and reviews already save correctly, do not delete or recreate it. `CREATE TABLE IF NOT EXISTS` does not modify existing columns. An older table containing `reviewed_at_utc` can still record timestamps even when the API does not return them; inspect its actual schema before claiming timestamps are absent.

Keep PostgreSQL running when using the dashboard. This step does not require data reload or model retraining.

## 5. Train and export

A fresh clone of this repository includes reference `models/metadata.json` but excludes the fitted `models/pipeline.joblib`. The training guard checks for metadata, not for the model binary. After preparing/loading the data, intentionally reproduce the reference run with:

```powershell
python -m src.train --overwrite
```

This rebuild regenerates the model, metadata, reports, and demo exports. Without `--overwrite`, the included metadata causes `FileExistsError` even on a fresh clone. The same command is used for an intentional rebuild of an existing installation. Do not run it merely to publish code or update documentation when your local model already works.

Only on an empty project where `models/metadata.json` does not exist, use:

```powershell
python -m src.train
```

Training reads `model_data.csv` and checks its hash against the audit. It then creates chronological splits, trains the candidate models, selects the model and threshold using validation data, and evaluates the test split.

Outputs include `models/pipeline.joblib`, `models/metadata.json`, evaluation reports, demo data, and two Power BI exports. Do not edit hashes or metric results manually.

Stop the API before rebuilding the model. After training finishes, restart the API, rerun the notebook, and refresh Power BI so that every component uses the same results.

## 6. Run the API and application

The model artifacts and demo files must already exist. PostgreSQL must be running with the loaded transactions and `fraud.review_events` table for the dashboard and review endpoints. The prediction endpoint alone can score without PostgreSQL. A successful `/health` response does not confirm that review storage is ready.

In the first terminal:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Wait for `Application startup complete`. Open <http://127.0.0.1:8000/health> or <http://127.0.0.1:8000/docs>.

In a second terminal, activate the same environment and run:

```powershell
python -m streamlit run app/dashboard.py --server.address 127.0.0.1 --server.port 8501
```

Open <http://127.0.0.1:8501>. Select a transaction, click **Score selected transaction via API**, and inspect its score and five leading factors. Choose **Review**, **Escalate**, or **Close**, then click **Apply review outcome**.

Review decisions are persisted in PostgreSQL. Each submission creates a new history entry. Decision timestamps are not recorded. After a successful save, Streamlit reruns and reloads the current status and history through the API. Review decisions do not change fraud labels or block transactions. The history displays up to 100 entries for the selected transaction and model version, newest review ID first. See [REVIEW_STORAGE.md](REVIEW_STORAGE.md) for the restart check.

If the API uses a different address, set `FRAUD_API_URL` in the application terminal before starting Streamlit. The standard configuration needs no additional setting. The dashboard reads this variable directly from the terminal environment rather than loading it from `.env`.

Stop each process with **Ctrl+C** when finished.

## 7. Refresh the notebook

Open `notebooks/audit_and_results.ipynb` in VS Code:

1. Select the kernel from the project's environment.
2. Choose **Restart Kernel**.
3. Choose **Run All**.
4. Check for errors and save with **Ctrl+S**.

The notebook reads existing reports. Running it does not start training. The model version displayed in its outputs must match `models/metadata.json`; refresh the outputs instead of editing the displayed version manually.

## 8. Set up or refresh Power BI

Follow [POWER_BI.md](POWER_BI.md). Use the two CSV exports in `powerbi/exports`. If the local file `powerbi/fraud_detection.pbix` already exists, open it and choose **Home → Refresh**.

Refresh reloads report sources; it does not run data preparation, database loading, or training. If the project folder moves, update both CSV paths in the Power BI data source settings.

## 9. Run the tests

Follow [TESTING.md](TESTING.md). For the full test configuration, PostgreSQL and the API must be running. In a separate PowerShell terminal:

```powershell
$env:RUN_DATABASE_TESTS = "1"
$env:FRAUD_LIVE_TESTS = "1"
python -m pytest -q -rs --tb=short --junitxml=reports/test_results.xml
```

`passed` means a check ran and succeeded. `skipped` means a check did not run. Review compatibility warnings separately from test failures.

## 10. Prepare a public repository or ZIP

Include source code, SQL, documentation, requirements, configuration without secrets, and the reports intended for publication. Check that saved notebook outputs match the current model version.

Exclude `.env`, `__pycache__`, test caches, and raw datasets from the public package. Keep the local `.env` for database access. `.gitignore` controls which untracked files Git ignores; it does not filter manually created ZIP files or uploads.

The current `.gitignore` also excludes the model binary, the Power BI transaction CSV, demo files, and `.pbix` files. Repository users must reproduce these artifacts locally. Portfolio screenshots should show report content without credentials.