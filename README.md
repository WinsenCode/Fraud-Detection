# Fraud Detection & Investigation MVP

An independent portfolio project for prioritizing suspicious transactions with machine learning, validating data in PostgreSQL, and presenting results through an investigation app and Power BI.

The project uses the public [IEEE-CIS Fraud Detection dataset](https://www.kaggle.com/competitions/ieee-fraud-detection/data). It demonstrates an offline evaluation and a local scoring workflow with human review. It does not automatically block transactions.

## What the project includes

- PostgreSQL ingestion, a transaction–identity LEFT JOIN, and eight SQL quality checks.
- A chronological train/validation/test split with preprocessing fitted on training data only.
- Dummy, Logistic Regression, and LightGBM comparisons using Average Precision and capacity-aware metrics.
- A saved scoring pipeline, input validation, and native TreeSHAP explanations through FastAPI.
- A Streamlit investigation queue with PostgreSQL-backed review decisions and ordered history.
- Two Power BI report pages: threshold-based transaction analysis and model comparison.
- Automated tests for data handling, metrics, API behavior, dashboard integration, review persistence, and artifact consistency.

## Evaluation results

These values come from `reports/metrics.csv` for model version `p0-39b5acba90af`. They describe the chronological test partition of the labeled training data, not the unlabeled competition test files. Regenerated reports are the source of truth for subsequent runs.

| Partition | Transactions | Fraud labels |
|---|---:|---:|
| Train | 354,324 | 11,988 |
| Validation | 118,108 | 4,611 |
| Test | 118,108 | 4,064 |

The test partition has a fraud prevalence of **3.44%**.

| Model | Average Precision | ROC AUC | Precision @ Top 2% | Recall @ Top 2% |
|---|---:|---:|---:|---:|
| Dummy | 0.0344 | 0.5000 | 4.61% | 2.68% |
| Logistic Regression | 0.1929 | 0.7725 | 30.51% | 17.74% |
| LightGBM | **0.4474** | **0.8597** | **62.08%** | **36.10%** |

Average Precision is the scikit-learn AP metric; it is not trapezoidal PR-AUC. LightGBM was selected on validation AP before test scoring.

### Two alert policies

| LightGBM policy | Alerts | True positives | False positives | Missed fraud | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| Top 2% of the complete test batch | 2,363 | 1,467 | 896 | 2,597 | 62.08% | 36.10% |
| Frozen validation threshold | 2,002 | 1,357 | 645 | 2,707 | 67.78% | 33.39% |

Top-K selects `ceil(0.02 × batch size)` transactions, with transaction ID breaking score ties. This is a batch ranking budget, not a daily capacity guarantee.

The API and the Power BI Overview use the separate rule `risk_score > threshold`. The threshold is selected on validation data and stored in `models/metadata.json`; its value in this run is approximately `0.3842220601593206`. Its alert rate can change on later data.

Performance varies by segment. For example, product W has **8.95% recall** under the frozen threshold. See `reports/error_slices.csv` for the full breakdown.

## Local setup

The reference workflow uses **Python 3.10.9**, Conda, local PostgreSQL, and Power BI Desktop. DBeaver is optional for inspecting the database. Follow the [setup and run guide](docs/START_HERE_ID.md) for step-by-step instructions.

For a new installation, create a Conda environment and install the project dependencies from the project root:

```powershell
conda create -n fraud_detection python=3.10.9
conda activate fraud_detection
python -m pip install -r requirements.txt
python -m pip check
```

If you already use the compatible `machine_learning` environment, activate it instead. Use the same environment for training, scoring, and testing. Recorded model package versions are available in `models/metadata.json`.

Before the first pipeline run:

1. Create the folders `data/raw`, `data/processed`, `reports/figures`, `models`, and `powerbi/exports` manually if they are missing.
2. Download `train_transaction.csv` and `train_identity.csv` from the dataset page and place them in `data/raw`.
3. Create a dedicated PostgreSQL database named `fraud_detection_database`.
4. Copy `.env.example` to `.env` and set `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`. Ensure `PGDATABASE=fraud_detection_database`.

For a fresh clone, run the reproduction pipeline from the directory containing `config.json`:

```powershell
python -m src.data prepare
python -m src.data load
python -m src.train --overwrite
```

This repository includes reference `models/metadata.json` but excludes `models/pipeline.joblib`. The training guard checks whether metadata exists, so a fresh clone needs `--overwrite` to intentionally regenerate the model, metadata, reports, and demo exports. Without this flag, training stops with `FileExistsError` even when the model binary is absent. If your local trained app already works, skip this reproduction sequence; publishing the repository does not require retraining. On a completely empty project with no metadata, `python -m src.train` is sufficient.

The load command runs SQL steps 0-3 and exports `data/processed/model_data.csv`. It does not execute `sql/4_review_events.sql`. After loading, run that entire SQL file once in DBeaver against `fraud_detection_database`, before using review endpoints or the dashboard. Follow [REVIEW_STORAGE.md](docs/REVIEW_STORAGE.md) to inspect an existing table and confirm the four-column schema. Manual CSV import in DBeaver is unnecessary. If rebuilding an existing installation, read the overwrite guidance in [START_HERE_ID.md](docs/START_HERE_ID.md) first.

## Run the investigation app

Keep PostgreSQL running with the transaction data and review table available. Start the API in one terminal:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Keep it running. In a second terminal with the same Conda environment active:

```powershell
python -m streamlit run app/dashboard.py --server.address 127.0.0.1 --server.port 8501
```

- API health: <http://127.0.0.1:8000/health>
- Interactive API documentation: <http://127.0.0.1:8000/docs>
- Investigation app: <http://127.0.0.1:8501>

The app contains a deliberately enriched 200-record queue: the 100 highest test scores and 100 randomly selected remaining transactions. It calls the API for live scoring. Review decisions are persisted in PostgreSQL. Each submission creates a new history entry. Decision timestamps are not recorded. Full-population metrics come from the complete test partition, not this queue.

## Power BI and tests

Import `powerbi/exports/fact_scores.csv` and `powerbi/exports/model_metrics.csv` as separate tables without a relationship. Follow [POWER_BI.md](docs/POWER_BI.md) to build or refresh the two report pages.

To run the full test configuration, keep PostgreSQL and the API running. In a separate PowerShell terminal:

```powershell
$env:RUN_DATABASE_TESTS = "1"
$env:FRAUD_LIVE_TESTS = "1"
python -m pytest -q -rs --tb=short --junitxml=reports/test_results.xml
```

See [TESTING.md](docs/TESTING.md) for individual test groups, skipped tests, warnings, and release checks. The report notebook reads existing outputs; it does not train models.

## Project guide

| Location | Purpose |
|---|---|
| `src/` | Data preparation, preprocessing, training, evaluation, and scoring |
| `sql/` | Data schema, LEFT JOIN, quality checks, descriptive KPIs, and review table setup |
| `api/` | Prediction endpoints and review write/read endpoints |
| `app/` | Streamlit investigation interface |
| `tests/` | Automated checks |
| `notebooks/audit_and_results.ipynb` | Audit and evaluation report reader |
| `models/` | Fitted pipeline and metadata |
| `reports/` | Metrics, checks, explanations, and figures |
| `powerbi/` | Reporting exports and local `.pbix` file |
| `docs/` | [Setup](docs/START_HERE_ID.md), [architecture](docs/ARCHITECTURE.md), [review storage](docs/REVIEW_STORAGE.md), [testing](docs/TESTING.md), and [Power BI](docs/POWER_BI.md) |

## Scope and limitations

Risk scores are not calibrated fraud probabilities. SHAP contributions describe model behavior, not causal evidence. Features are assumed available at simulated scoring time; real feature availability and label delays have not been verified. Entities may recur across time partitions, so results do not establish performance on entirely new customers.

This local MVP includes persistent review history. It has no production authentication, analyst identity tracking, transaction blocking, decision timestamps, or operational monitoring. The review history supports a local demo; it is not a complete production audit trail. Further model development should use training/validation data and a new untouched evaluation period rather than repeatedly optimizing against the reported test results.

The implementation covers the agreed P1 demo scope: global and local explanations, error slices, persistent review decisions, and automated checks. Decision timestamps are deliberately excluded from this scope. The `p0-` prefix in the model version identifies the existing trained artifact; adding review storage does not require renaming or retraining that model.

The repository excludes credentials, raw/processed datasets, fitted model binaries, demo payloads, transaction-level reporting exports, and local `.pbix` files under the current `.gitignore`. Reproduce the artifacts locally. Obtain source data separately and follow the dataset's terms.

Detailed model assumptions and measured results are recorded in `reports/model_card.md`.