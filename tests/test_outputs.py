import pandas as pd
from src.common import ROOT, read_json, sha256

def test_frozen_config_sources_and_artifact_match():
    meta = read_json(ROOT / 'models/metadata.json')
    assert meta['status'] == 'complete'
    assert meta['config_sha256'] == sha256(ROOT / 'config.json')
    assert meta['artifact_sha256'] == sha256(ROOT / 'models/pipeline.joblib')
    for name, expected in meta['source_sha256'].items():
        assert sha256(ROOT / name) == expected, f'Changed source: {name}; model lineage is stale.'
    assert meta['test_used_for_selection'] is False

def test_powerbi_exports_reconcile_with_metrics():
    fact = pd.read_csv(ROOT / 'powerbi/exports/fact_scores.csv')
    metrics = pd.read_csv(ROOT / 'reports/metrics.csv')
    m = metrics[(metrics.model == 'lightgbm') & (metrics.split == 'test')].iloc[0]
    assert len(fact) == m.rows and fact.transaction_id.is_unique
    assert fact.is_fraud.sum() == m.fraud_count
    assert fact.selected_topk.sum() == m.k
    assert fact.topk_tp.sum() == m.topk_tp and fact.topk_fp.sum() == m.topk_fp
    assert fact.is_alert.sum() == m.threshold_alerts
    assert fact.threshold_tp.sum() == m.threshold_tp and fact.threshold_fn.sum() == m.threshold_fn
    assert set(fact.model_version) == {read_json(ROOT / 'models/metadata.json')['model_version']}

def test_split_and_sql_reports_pass():
    splits = pd.read_csv(ROOT / 'reports/split_summary.csv').set_index('split')
    audit = read_json(ROOT / 'reports/data_audit.json')
    assert splits.loc['train', 'time_max'] < splits.loc['validation', 'time_min']
    assert splits.loc['validation', 'time_max'] < splits.loc['test', 'time_min']
    assert splits.rows.sum() == audit['transaction_rows'] == audit['joined_rows']
    assert pd.read_csv(ROOT / 'reports/sql_quality.csv').passed.all()