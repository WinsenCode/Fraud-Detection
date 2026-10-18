# Review Storage and Setup

## Scope

Review decisions are persisted in PostgreSQL. Each submission creates a new history entry. Decision timestamps are not recorded by the intended four-column schema in `sql/4_review_events.sql`.

This is the selected P1 local-demo scope. The original timestamp-based audit requirement has been deliberately reduced. Review IDs provide an ordering key; the implementation does not record when a decision happened or who made it. It does not block transactions or modify fraud labels.

## Install after loading transaction data

The existing data loader executes SQL steps 0-3 only. After `python -m src.data load`, apply SQL step 4 separately. A completed existing data load does not need to be repeated.

1. Open DBeaver and choose the project database connection.
2. Execute the query below. It must return `fraud_detection_database`.
3. Open `sql/4_review_events.sql` from the project folder and execute the entire script.
4. Commit if DBeaver uses manual transactions.
5. Refresh the table list under the `fraud` schema.

```sql
SELECT current_database();
```

Inspect the actual schema with this read-only query:

```sql
SELECT column_name, data_type, is_nullable, column_default, is_identity
FROM information_schema.columns
WHERE table_schema = 'fraud'
  AND table_name = 'review_events'
ORDER BY ordinal_position;
```

Expected columns:

| Column | PostgreSQL type | Purpose |
|---|---|---|
| `review_id` | `BIGINT`, generated identity, primary key | Unique review entry and history ordering |
| `transaction_id` | `BIGINT NOT NULL` | Reviewed transaction |
| `model_version` | `TEXT NOT NULL` | Model associated with the decision |
| `action` | `TEXT NOT NULL` | `Review`, `Escalate`, or `Close` |

If these four columns already exist and review submission works, preserve the existing rows. Running the setup again may add the index if it was missing; it does not erase decisions.

The older SQL file included `reviewed_at_utc DEFAULT clock_timestamp()`. If the actual table still contains that column, it may record timestamps even though the API returns only four fields. Replacing a SQL file does not change a live table, and `CREATE TABLE IF NOT EXISTS` does not migrate its columns. This update deliberately contains no `DROP`, `TRUNCATE`, or automatic column-removal command. Inspect and reconcile an older schema before presenting it as having no timestamps.

PostgreSQL documents this behavior under [CREATE TABLE: IF NOT EXISTS](https://www.postgresql.org/docs/18/sql-createtable.html).

## Start the services

Keep PostgreSQL running. Use the same Conda environment in both terminals.

Terminal A:

```powershell
conda activate machine_learning
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Terminal B:

```powershell
conda activate machine_learning
python -m streamlit run app/dashboard.py --server.address 127.0.0.1 --server.port 8501
```

Run from the project root. An alternative compatible Conda environment is acceptable. The dashboard uses `FRAUD_API_URL` from its terminal environment, defaulting to `http://127.0.0.1:8000`.

## API contract

| Endpoint | Result |
|---|---|
| `POST /reviews` | Commits a new decision and returns HTTP 201 |
| `GET /reviews?model_version=...` | Latest review per transaction for that model |
| `GET /reviews/{transaction_id}?model_version=...&limit=100` | Up to 100 history entries, descending review ID |

If the model-version query parameter is omitted, the loaded model version is used. POST requires the currently loaded version and an existing transaction. Its request fields are `transaction_id`, `model_version`, and `action`. Its response adds `review_id`.

Invalid actions or malformed fields return HTTP 422. A different model version on POST returns HTTP 409; an unknown transaction returns HTTP 404. An unavailable database, missing review table, or an incorrectly named database returns HTTP 503 through the review handlers. A healthy scorer response from `/health` alone is not a review-database readiness check.

The database transaction commits before a successful POST response is returned. Submissions use `INSERT` rather than replacing earlier decisions. The UI fetches history through the API; session state only holds temporary prediction results and notices.

## Persistence check

1. Select a transaction in the dashboard and submit a decision.
2. Note its `review_id`, transaction ID, and model version.
3. Stop API and Streamlit with Ctrl+C, then start both again using the same database and model.
4. Select that transaction again. Its existing decision and history must still appear.
5. Submit another decision. It must have a new review ID, with earlier entries preserved.

If this check was already completed for the current implementation, retain that evidence instead of repeating it for documentation changes.

## Tests and saved evidence

Keep PostgreSQL and the API running. In a separate PowerShell terminal:

```powershell
conda activate machine_learning
$env:RUN_DATABASE_TESTS = "1"
$env:FRAUD_LIVE_TESTS = "1"
python -m pytest tests/test_reviews.py -q -rs --tb=short
python -m pytest -q -rs --tb=short --junitxml=reports/test_results.xml
```

The focused file has two tests. The current complete suite has 26 cases. The supplied XML is copied unchanged from the submitted project and records 26 tests, zero failures, zero errors, and zero skipped tests. No new full integration run is claimed by this documentation update.

The two review tests inspect committed rows through a separate database connection, retain prior entries, read history/latest decisions through the API, and reject an invalid action without a database change. They clean up only their own created review IDs. The live dashboard test also reads the decision in a fresh Streamlit test session and leaves its submitted entry in the demo history. Automated session recreation is not a recorded restart of the separate API process.

## Boundaries

- There is no analyst identity, decision timestamp, authentication, or production monitoring.
- Ordering is by generated review ID; concurrent transactions are not ordered by event time.
- POST does not provide an idempotency key. If a response is lost, inspect history before retrying to avoid duplicate submissions.
- The API checks transaction existence. The table has no foreign key to the source tables; a deliberate source-data replacement can leave historical reviews referring to transactions no longer present.
- The Power BI pages read offline model exports and do not visualize review history.
- Review storage does not change the trained model or its `p0-` artifact identifier.