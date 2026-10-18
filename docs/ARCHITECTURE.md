# Architecture and Data Contract

## Components

| Stage | Implementation | Main output |
|---|---|---|
| Source preparation | `src/data.py prepare` | Selected-column CSVs and source manifest |
| PostgreSQL loading and audit | `src/data.py load`, `sql/` | Joined model data, SQL gates, descriptive KPIs |
| Preprocessing and time split | `src/features.py` | Training-fitted transformations and separate time partitions |
| Training and evaluation | `src/train.py`, `src/evaluate.py` | Fitted model, frozen decisions, metrics, explanations, exports |
| Online scoring | `src/inference.py`, `api/` | Validated prediction response and local contributions |
| Investigation interface | `app/dashboard.py` | Ranked demo queue, API-based review submission, and saved history |
| Review storage | `api/reviews.py`, `sql/4_review_events.sql` | Persistent decisions in `fraud.review_events` |
| Reporting | Notebook and Power BI | Audit summaries and offline evaluation views |

The API loads the serialized pipeline once during application startup. Streamlit calls the API and does not load or retrain the model. Power BI reads exported CSV files independently of the API. PostgreSQL is required for data loading, review reads/writes, the investigation dashboard, and integration tests. `/predict` can score an existing model without PostgreSQL. `/health` reports the loaded scorer; it does not verify review storage readiness.

## Data preparation and SQL

The source population contains 590,540 transactions and 144,233 identity rows. The join uses transaction ID and keeps every transaction, including those without identity data. A total of 446,307 transactions have no matching identity row in the reference run.

Numeric-looking categorical IDs are preserved as strings. PostgreSQL primary keys prevent duplicate IDs; label constraints accept only 0 and 1. SQL quality checks cover nonempty transaction/identity tables, duplicate keys, join row preservation, invalid labels, invalid time offsets, and orphan identity keys.

Descriptive KPIs over the complete dataset are reports, not model features. `transaction_dt` is an offset used for ordering and relative-day reporting; it is not a calendar date.

## Leakage controls and selection

- Sort by `transaction_dt`, then `transaction_id`.
- Target a 60/20/20 chronological split. Keep equal timestamps in the same partition.
- Fit imputers and encoders on training rows only.
- Use validation data for early stopping, candidate selection, and the API threshold.
- Save frozen decisions before scoring the test partition.
- Exclude `is_fraud`, transaction ID, and time offset from the feature set.

LightGBM must outperform both baselines on validation Average Precision for the training gate to pass. The selected pipeline remains fitted on training data; there is no train-plus-validation refit. The reference LightGBM run stopped at iteration 392 within a 400-tree budget.

A later experiment informed by the current test results needs a new untouched evaluation period for an honest final assessment.

## Feature contract

The contract identifier is `ieee-cis-v1-25-features`.

| Group | Fields |
|---|---|
| Numeric, 14 | `transaction_amt`, `dist1`, `c1`, `c2`, `c6`, `c11`, `c13`, `c14`, `d1`, `d2`, `d3`, `d10`, `d15`, `id_02` |
| Categorical, 11 | `product_cd`, `card1`, `card2`, `card4`, `card6`, `addr1`, `p_emaildomain`, `r_emaildomain`, `device_type`, `id_12`, `id_15` |

The API request also requires integer metadata fields `transaction_id` and `transaction_dt`. They are returned or used for identification, not passed to the model as features.

All request fields are required. Nullable features may explicitly contain JSON `null`; omitting a required field is different. `product_cd` must be one of `W`, `C`, `R`, `H`, or `S`. Categorical IDs such as `card1` must be strings. The amount must be nonnegative, numeric values must be finite, and extra fields such as `is_fraud` are rejected.

Use `data/sample_request.json` as the complete request example after training. The request and response definitions are in `api/schemas.py`.

## API behavior

| Endpoint | Behavior |
|---|---|
| `GET /health` | Returns service status, loaded model version, and feature count |
| `POST /predict` | Validates one transaction and returns its score, alert decision, threshold, version, and top five contributions |
| `POST /reviews` | Validates and commits a new review entry; returns HTTP 201 and its generated review ID |
| `GET /reviews` | Returns the latest review for each transaction within the requested model version |
| `GET /reviews/{transaction_id}` | Returns up to 100 entries for that transaction and model version, ordered by descending review ID |

The alert operator is strictly `>`. Equality with the threshold does not create an alert.

Native LightGBM TreeSHAP contributions use raw log-odds. The complete contribution vector, including the bias term, is checked against prediction. The response displays only the five largest absolute feature contributions, so those five alone do not reconstruct the full margin. Contributions are not percentages, causal explanations, or proof of fraud.

## Artifact consistency

`models/metadata.json` records the feature contract, source/configuration/data hashes, package versions, model version, threshold policy, and artifact checksum. The API checks model completeness, feature order, contract, and artifact checksum at startup. The output tests additionally check source and configuration hashes.

Byte-level source hashes include changes to comments, quotes, whitespace, and line endings. A mismatch is evidence that file bytes differ from the training record; it does not by itself establish a behavioral change. Restore a verified original file or perform an intentional rebuild after reviewing the change. Never edit expected hashes merely to make a test pass.

Training replaces the model, reports, and demo exports together. Restart the API after a rebuild; an already-running process retains its previously loaded model. Refresh Power BI and rerun the report notebook afterward.

## Investigation and reporting boundaries

The 200-record demonstration queue is enriched for investigation. It cannot estimate population fraud prevalence or model precision. Labels appear in offline evaluation files but are excluded from API payloads and the main investigation queue.

Power BI keeps transaction-level `fact_scores` separate from aggregate `model_metrics`. A relationship on model version would not represent a useful reporting grain: the summary contains several models and partitions, while the fact table contains the selected model's test predictions.

Review decisions are persisted in PostgreSQL. Each submission creates a new history entry. Decision timestamps are not recorded.

The table contains `review_id`, `transaction_id`, `model_version`, and `action`. The API uses a new `INSERT` for each submission; it does not overwrite the previous decision. PostgreSQL commits the transaction before the POST handler returns. Review endpoints require `fraud_detection_database`, and a new submission must reference an existing transaction and the currently loaded model version. History is isolated by transaction ID and model version.

The dashboard reads saved decisions through the API after each rerun. Session state is used for temporary scoring results and success messages, not as the review record store. Restarting the API or Streamlit does not clear committed database rows.

The loader runs only SQL steps 0-3. Apply `sql/4_review_events.sql` separately as described in [REVIEW_STORAGE.md](REVIEW_STORAGE.md). Review order is based on generated IDs, not event timestamps; there is no analyst identity field or concurrency guarantee based on wall-clock time. Access control, monitoring, calibrated probabilities, measured financial impact, and deployment validation remain outside this local demo.