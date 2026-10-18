# Power BI Report Guide

The report uses CSV exports from the Python evaluation pipeline. PostgreSQL remains the ingestion and audit layer; these report pages do not query PostgreSQL or call the prediction API.

## Sources and reporting grain

| Table | Source file | Grain |
|---|---|---|
| `fact_scores` | `powerbi/exports/fact_scores.csv` | One transaction in the selected model's chronological test partition |
| `model_metrics` | `powerbi/exports/model_metrics.csv` | One evaluation row per model and split |

Keep these tables **without a relationship**. The reference export contains 118,108 fact rows and six model-metric rows: three models evaluated on validation and test.

If `powerbi/fraud_detection.pbix` is already available locally, open it and refresh its sources. To reconstruct the report, follow the steps below.

## Import the CSV files

1. Select **Home → Get data → Text/CSV**.
2. Select the source file, set the delimiter to **Comma**, and set **File Origin** to **65001: Unicode (UTF-8)**.
3. Choose **Transform Data**, name the query `fact_scores` or `model_metrics`, and verify its data types.
4. Select **Close & Apply** after both queries are ready.

If decimal values are interpreted incorrectly, revisit the automatic type-conversion step and use **Change Type → Using Locale → Decimal Number → English (United States)**. The exported numbers use a decimal point. Changing the display format later does not fix numbers already parsed incorrectly.

Do not remove transactions merely because `device_type` is blank. Missing identity information is expected in this dataset.

### `fact_scores` data types

| Data type | Columns |
|---|---|
| Text | `transaction_id`, `product_cd`, `device_type`, `model_version`, `split` |
| Decimal Number | `transaction_amt`, `risk_score`, `threshold` |
| Whole Number | `transaction_dt`, `relative_day`, `risk_rank`, `is_fraud`, `is_alert`, `selected_topk`, `threshold_tp`, `threshold_fp`, `threshold_fn`, `topk_tp`, `topk_fp`, `topk_fn` |

Transaction ID is displayed as an identifier rather than a quantity. `relative_day` is an offset day, not a calendar Date. No currency is assigned to the amount because the project does not establish one.

### `model_metrics` data types

| Data type | Columns |
|---|---|
| Text | `model`, `split`, `model_version` |
| Decimal Number | `prevalence`, `average_precision`, `roc_auc`, `precision_at_k`, `recall_at_k`, `threshold`, `threshold_precision`, `threshold_recall` |
| Whole Number | `rows`, `fraud_count`, `k`, `topk_tp`, `topk_fp`, `topk_fn`, `topk_tn`, `threshold_alerts`, `threshold_tp`, `threshold_fp`, `threshold_fn`, `threshold_tn` |

Power Query data types and report display formats are separate settings. Store ratios as decimal numbers; use Percentage formatting where specified below. Do not multiply the underlying ratios by 100.

## Page 1: Fraud Detection Overview

Use the page title **Offline Holdout Evaluation — Frozen Validation Threshold**. Every visual on this page should use `fact_scores` fields or measures based on that table.

### Measures

Create each measure separately in `fact_scores`. If the measures already exist, verify them rather than creating duplicates.

```dax
Total Transactions = COUNTROWS(fact_scores)
```

```dax
Actual Fraud = SUM(fact_scores[is_fraud])
```

```dax
Alerts = SUM(fact_scores[is_alert])
```

```dax
True Positives = SUM(fact_scores[threshold_tp])
```

```dax
False Positives = SUM(fact_scores[threshold_fp])
```

```dax
Missed Fraud = SUM(fact_scores[threshold_fn])
```

```dax
Precision = DIVIDE([True Positives], [Alerts])
```

```dax
Recall = DIVIDE([True Positives], [Actual Fraud])
```

```dax
Fraud Rate = DIVIDE([Actual Fraud], [Total Transactions])
```

Format `Precision`, `Recall`, and `Fraud Rate` as **Percentage, two decimal places**. Format the other six measures as **Whole Number**. `DIVIDE` returns a blank for a zero denominator; a blank precision with no alerts is not a calculation failure.

### Visuals

| Visual | Fields and settings |
|---|---|
| Six cards | Total Transactions, Actual Fraud, Alerts, Precision, Recall, Missed Fraud |
| Stacked column chart | X: `product_cd`; Y: True Positives and Missed Fraud |
| Clustered bar chart | Y: `product_cd`; X: Precision and Recall |
| Line chart | X: `relative_day`, in ascending time order; Y: Fraud Rate |
| Transaction table | `transaction_id`, `product_cd`, `transaction_amt`, `risk_score`, `is_alert`, `is_fraud` |
| Slicers | `product_cd`, `device_type`, and a range for `relative_day` |

For the transaction table, use **Don't summarize** for numeric columns and sort `risk_score` descending. Select the visual, open **Build visual**, and use the field's dropdown to change aggregation. Aggregation is not the Tooltips field well.

Risk scores can be displayed with four decimal places for readability. Keep them as scores, not percentages labeled as calibrated fraud probability.

Use the `threshold_*` columns for this page. The separate `topk_*` columns describe a different selection policy and should not be substituted into these measures.

## Page 2: Model Comparison

Use the page title **Model Comparison — Test Set**.

1. Open the **Filters** pane. If hidden, enable it through **View → Filters**.
2. Drag `model_metrics[split]` into **Filters on this page**.
3. Select only **test**. This is a page filter, not a filter on all report pages.
4. Add a column chart with `model` on X and `average_precision` on Y. Set its Y aggregation to **Maximum / Max** and sort descending.
5. Give the chart the title **Average Precision by Model**.
6. Add a table containing the five columns below.

| Source column | Display name | Display format | Table aggregation |
|---|---|---|---|
| `model` | Model | Text | None |
| `average_precision` | Average Precision | Decimal, four places | Don't summarize |
| `roc_auc` | ROC AUC | Decimal, four places | Don't summarize |
| `precision_at_k` | Precision @ Top 2% | Percentage, two places | Don't summarize |
| `recall_at_k` | Recall @ Top 2% | Percentage, two places | Don't summarize |

Select the table, open **Build visual → Columns**, and use **Rename for this visual** for display names. In **Format visual → Visual → Totals**, turn totals off. Adding performance ratios across models has no useful interpretation.

The table displays individual evaluation records; the chart uses Max because the test page has one record per model. Retain the test filter so validation and test results are not combined.

## Reconcile the report

For reference model `p0-39b5acba90af`, clear all slicer selections and visual selections on Overview. The values should be:

| Measure | Reference value |
|---|---:|
| Total Transactions | 118,108 |
| Actual Fraud | 4,064 |
| Alerts | 2,002 |
| True Positives | 1,357 |
| False Positives | 645 |
| Missed Fraud | 2,707 |
| Precision | 67.78% |
| Recall | 33.39% |
| Fraud Rate | 3.44% |

Selecting product W should filter all Overview visuals. In the reference run it gives 93,669 transactions, 1,810 fraud labels, 341 alerts, 47.51% precision, and 8.95% recall. Clear that selection again before saving the default report view.

On Model Comparison, LightGBM should show AP **0.4474**, ROC AUC **0.8597**, Precision @ Top 2% **62.08%**, and Recall @ Top 2% **36.10%** for the same reference run.

Those Top-K values differ from the Overview threshold values by design. Use current CSV exports when checking a newly trained model; do not force the report to match an older reference value.

If a card unexpectedly shows one transaction, check whether a table row or chart point is selected. Clear visual selections and slicers before diagnosing a data-load problem.

## Save, refresh, and share

Save the local report as `powerbi/fraud_detection.pbix`. After Python regenerates the CSVs, choose **Home → Refresh** and save again. If the project directory moved, update the file location for both CSV sources through **Data source settings** or the corresponding Power Query source step.

The current `.gitignore` excludes `.pbix` and transaction-level reporting exports. A public source checkout therefore needs its data and model workflow run locally before the report can be rebuilt. A screenshot can illustrate the report, but it does not replace the refreshable `.pbix` or the reconciliation checks.

References: [Text/CSV connector](https://learn.microsoft.com/en-us/power-query/connectors/text-csv), [report filters](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-add-filter), and [DAX DIVIDE](https://learn.microsoft.com/en-us/dax/divide-function-dax).