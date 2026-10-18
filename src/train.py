'''One command trains, freezes decisions, evaluates holdout, and exports the MVP.'''
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from datetime import datetime, timezone

import joblib
import lightgbm as lgb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.pipeline import Pipeline

from src.common import (ROOT, FEATURES, NUMERIC, CONTRACT_VERSION, check_folders,
                        read_json, write_json, sha256)
from src.data import read_model_data
from src.features import chronological_split, preprocessing
from src.evaluate import evaluate, capacity_k, rank_indices, validation_threshold

def plot_results(metrics, test, scores, global_shap):
    plt.rcParams.update({'figure.dpi': 140, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, ax = plt.subplots(figsize = (8, 5))
    for name, values in scores.items():
        precision, recall, _ = precision_recall_curve(test.is_fraud, values)
        ap = average_precision_score(test.is_fraud, values)
        # A straight line between a constant-score dummy's endpoints is misleading.
        ax.step(recall, precision, where = 'post', label = f'{name} (AP = {ap:.3f})')
    ax.axhline(test.is_fraud.mean(), color = 'grey', linestyle = '--', label = 'Holdout prevalence')
    ax.set(xlabel = 'Recall', ylabel = 'Precision', title = 'Chronological holdout: precision-recall')
    ax.legend()
    fig.tight_layout()
    fig.savefig(ROOT / 'reports/figures/precision_recall.png')
    plt.close(fig)  
    
    fig, ax = plt.subplots(figsize = (8, 5))
    top = global_shap.head(12).iloc[::-1]
    ax.barh(top.feature, top.mean_abs_shap, color = 'aqua')
    ax.set(xlabel = 'Mean absolute TreeSHAP contribution (raw log-odds)',
           title = 'Global model contributions: 1,000 validation rows')
    fig.tight_layout()
    fig.savefig(ROOT / 'reports/figures/global_shap.png')
    plt.close(fig)
    
    m = metrics[(metrics.model == 'lightgbm') & (metrics.split == 'test')].iloc[0]
    matrix = np.array([[m.threshold_tn, m.threshold_fp], [m.threshold_fn, m.threshold_tp]], dtype = int)
    fig, ax = plt.subplots(figsize = (6, 4))
    ax.imshow(matrix, cmap = 'Blues')
    for (i, j), value in np.ndenumerate(matrix):
        ax.text(j, i, f'{value:,}', ha = 'center', va = 'center', color = 'white' if value > matrix.max()/2 else 'black')
    ax.set(xticks = [0, 1], yticks = [0, 1], xticklabels = ['No alert', 'Alert'],
           yticklabels = ['Not fraud', 'Fraud'], xlabel = 'Frozen threshold decision', ylabel = 'Offline label',
           title = 'Holdout confusion matrix (threshold policy)')
    fig.tight_layout()
    fig.savefig(ROOT / 'reports/figures/confusion_matrix.png')
    plt.close(fig)

def export_holdout(test, scores, threshold, config, version):
    out = test[['transaction_id', 'transaction_dt', 'transaction_amt', 'product_cd', 'device_type', 'is_fraud']].copy()
    out['relative_day'] = out.transaction_dt // 86400
    out['risk_score'] = scores
    out['threshold'] = threshold
    out['is_alert'] = (scores > threshold).astype(int)
    out['selected_topk'] = 0
    order = rank_indices(scores, test.transaction_id)
    out.iloc[order[:capacity_k(len(test), config['alert_rate'] )], out.columns.get_loc('selected_topk')] = 1
    out['risk_rank'] = np.argsort(order) + 1
    out['model_version'] = version
    out['split'] = 'test'
    for prefix, flag in [('threshold', out.is_alert), ('topk', out.selected_topk)]:
        out[prefix + '_tp'] = ((flag == 1) & (out.is_fraud == 1)).astype(int)
        out[prefix + '_fp'] = ((flag == 1) & (out.is_fraud == 0)).astype(int)
        out[prefix + '_fn'] = ((flag == 0) & (out.is_fraud == 1)).astype(int)
    out.to_csv(ROOT / 'powerbi/exports/fact_scores.csv', index = False)
    slices = out.groupby(['product_cd'], dropna = False).agg(
        transactions = ('transaction_id', 'size'), fraud = ('is_fraud', 'sum'),
        alerts = ('is_alert', 'sum'), tp = ('threshold_tp', 'sum'),
        fp = ('threshold_fp', 'sum'), fn = ('threshold_fn', 'sum')).reset_index()
    slices['precision'] = slices.tp / slices.alerts.replace(0, np.nan)
    slices['recall'] = slices.tp / slices.fraud.replace(0, np.nan)
    slices.to_csv(ROOT / 'reports/error_slices.csv', index = False)
    # A clearly documented, enriched demo: 100 highest scores plus 100 uniformly selected others.
    rest = order[100:]
    rng = np.random.default_rng(config['seed'])
    demo_indices = np.concatenate([order[:100], rng.choice(rest, size = min(100, len(rest)), replace = False)])
    demo = test.iloc[demo_indices][['transaction_id', 'transaction_dt'] + FEATURES]
    write_json(ROOT / 'data/demo_requests.json', json.loads(demo.to_json(orient = 'records')))
    out.iloc[demo_indices].drop(columns = ['is_fraud', 'threshold_tp', 'threshold_fp', 'threshold_fn',
                                      'topk_tp', 'topk_fp', 'topk_fn', 'selected_topk', 'risk_rank']).to_csv(
        ROOT / 'data/demo_queue.csv', index = False)
    write_json(ROOT / 'data/sample_request.json', json.loads(demo.iloc[:1].to_json(orient = 'records'))[0])
    return out

def explain(model, preprocessor, validation, test, scored, seed):
    sample = validation.sample(n = min(1000, len(validation)), random_state = seed)
    transformed = preprocessor.transform(sample[FEATURES])
    contributions = model.booster_.predict(transformed, pred_contrib = True)
    raw = model.booster_.predict(transformed, raw_score = True)
    np.testing.assert_allclose(contributions.sum(axis = 1), raw, rtol = 1e-6, atol = 1e-6)
    global_shap = pd.DataFrame({'feature': FEATURES, 'mean_abs_shap': np.abs(contributions[:, :-1]).mean(axis=0)})
    global_shap = global_shap.sort_values('mean_abs_shap', ascending = False)
    global_shap.to_csv(ROOT / 'reports/global_shap.csv', index = False)
    examples = []
    for kind, mask in [('true_positive', scored.threshold_tp == 1),
                       ('false_positive', scored.threshold_fp == 1), ('false_negative', scored.threshold_fn == 1)]:
        cases = scored.loc[mask].sort_values(['risk_score', 'transaction_id'], ascending = [False, True])
        if cases.empty:
            continue
        case = cases.iloc[0]
        row = test.loc[test.transaction_id == case.transaction_id, FEATURES]
        values = model.booster_.predict(preprocessor.transform(row), pred_contrib = True)[0]
        examples.append({'case': kind, 'transaction_id': int(case.transaction_id),
                         'is_fraud': int(case.is_fraud), 'risk_score': float(case.risk_score),
                         'expected_log_odds': float(values[-1]),
                         'contributions': {f: float(v) for f, v in zip(FEATURES, values[:-1])}})
    write_json(ROOT / 'reports/local_explanations.json', examples)
    return global_shap

def main(overwrite = False):
    started = time.perf_counter()
    check_folders()
    if (ROOT / 'models/metadata.json').exists() and not overwrite:
        raise FileExistsError('A completed model already exists. Use --overwrite only for an intentional reproduction.')
    config = read_json(ROOT / 'config.json')
    audit = read_json(ROOT / 'reports/data_audit.json')
    if audit['status'] != 'passed' or sha256(ROOT / 'data/processed/model_data.csv') != audit['model_data_sha256']:
        raise ValueError('Data audit is missing/stale. Rerun data prepare/load.')
    data = read_model_data()
    train, val, test, boundaries = chronological_split(data, config['train_fraction'], config['validation_fraction'])
    del data
    split_summary = []
    for name, part in [('train', train), ('validation', val), ('test', test)]:
        split_summary.append({'split': name, 'rows': len(part), 'fraud_count': int(part.is_fraud.sum()),
                              'prevalence': float(part.is_fraud.mean()),
                              'time_min': int(part.transaction_dt.min()), 'time_max': int(part.transaction_dt.max())})
    pd.DataFrame(split_summary).to_csv(ROOT / 'reports/split_summary.csv', index = False)
    print('Time blocks:', [(x['split'], x['rows']) for x in split_summary], flush = True)
    x_train, x_val = train[FEATURES], val[FEATURES]
    candidates = {}
    print('Fitting DummyClassifier...', flush = True)
    candidates['dummy'] = DummyClassifier(strategy = 'prior').fit(x_train, train.is_fraud)
    print('Fitting LogisticRegression...', flush = True)
    candidates['logistic'] = Pipeline([
        ('preprocessor', preprocessing('logistic')),
        ('model', LogisticRegression(solver = 'liblinear', max_iter = 500, random_state = config['seed']))
    ]).fit(x_train, train.is_fraud)
    print('Fitting LightGBM (validation early stopping; no test input)...', flush = True)
    preprocessor = preprocessing('lightgbm')
    train_encoded = preprocessor.fit_transform(x_train)
    val_encoded = preprocessor.transform(x_val)
    model = lgb.LGBMClassifier(**config['lightgbm'], random_state = config['seed'],
                               verbosity = -1, deterministic = True, force_col_wise = True, metric = 'average_precision')
    model.fit(train_encoded, train.is_fraud, eval_set = [(val_encoded, val.is_fraud)],
              eval_metric = 'average_precision', categorical_feature = list(range(len(NUMERIC), len(FEATURES))),
              callbacks = [lgb.early_stopping(40, first_metric_only = True, verbose = False)])
    candidates['lightgbm'] = Pipeline([('preprocessor', preprocessor), ('model', model)])
    validation_scores = {name: pipeline.predict_proba(x_val)[:, 1] for name, pipeline in candidates.items()}
    val_ap = {name: float(average_precision_score(val.is_fraud, values)) for name, values in validation_scores.items()}
    if val_ap['lightgbm'] <= max(val_ap['dummy'], val_ap['logistic']):
        raise RuntimeError(f'Validation gate failed: {val_ap}. Do not open holdout; revisit training/validation only.')
    thresholds = {name: validation_threshold(values, config['alert_rate']) for name, values in validation_scores.items()}
    versions = {p: importlib.metadata.version(p) for p in ['numpy', 'pandas', 'scikit-learn', 'lightgbm', 'joblib']}
    source_hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): sha256(p)
                     for p in sorted((ROOT / 'src').glob('*.py'))}
    frozen = {'contract_version': CONTRACT_VERSION, 'features': FEATURES, 'config': config,
              'config_sha256': sha256(ROOT / 'config.json'), 'source_sha256': source_hashes,
              'data_sha256': audit['model_data_sha256'], 'boundaries': boundaries,
              'selected_model': 'lightgbm', 'selection_rule': 'LightGBM must beat both baselines on validation AP',
              'validation_ap': val_ap, 'thresholds': thresholds, 'threshold_operator': '>',
              'best_iteration': model.best_iteration_, 'package_versions': versions,
              'trained_on': 'train only; no train+validation refit', 'test_used_for_selection': False}
    version = 'p0-' + hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()[:12]
    frozen['model_version'] = version
    frozen['frozen_at_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(ROOT / 'reports/frozen_decisions.json', frozen)
    joblib.dump(candidates['lightgbm'], ROOT / 'models/pipeline.joblib', compress = 3)
    print('Model and policy frozen. Evaluating holdout once for each frozen candidate.', flush = True)
    test_scores = {name: pipeline.predict_proba(test[FEATURES])[:, 1] for name, pipeline in candidates.items()}
    rows = []
    for split, part, scores in [('validation', val, validation_scores), ('test', test, test_scores)]:
        for name, values in scores.items():
            rows.append({'model': name, 'split': split, 'model_version': version,
                         **evaluate(part.is_fraud, values, part.transaction_id, config['alert_rate'], thresholds[name])})
    metrics = pd.DataFrame(rows)
    metrics.to_csv(ROOT / 'reports/metrics.csv', index = False)
    metrics.to_csv(ROOT / 'powerbi/exports/model_metrics.csv', index = False)
    scored = export_holdout(test, test_scores['lightgbm'], thresholds['lightgbm'], config, version)
    global_shap = explain(model, preprocessor, val, test, scored, config['seed'])
    plot_results(metrics, test, test_scores, global_shap)
    metadata = {**frozen, 'status': 'complete', 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
                'python_version': platform.python_version(), 'artifact_sha256': sha256(ROOT / 'models/pipeline.joblib'),
                'risk_score_is_calibrated_probability': False, 'elapsed_seconds': round(time.perf_counter() - started, 2)}
    write_json(ROOT / 'models/metadata.json', metadata)
    write_model_card(metrics, metadata, split_summary)
    print(metrics[['model', 'split', 'average_precision', 'precision_at_k', 'recall_at_k']].to_string(index = False))
    print(f'Completed {version} in {metadata["elapsed_seconds"]:.1f}s', flush = True)

def write_model_card(metrics, metadata, splits):
    m = metrics[(metrics.model == 'lightgbm') & (metrics.split == 'test')].iloc[0]
    rows = ['| Model | Split | AP | ROC-AUC | Precision@K | Recall@K |',
            '|---|---|---:|---:|---:|---:|']
    for r in metrics.itertuples():
        rows.append(f'| {r.model} | {r.split} | {r.average_precision:.6f} | {r.roc_auc:.6f} | {r.precision_at_k:.6f} | {r.recall_at_k:.6f} |')
    text = f'''# Model card - {metadata['model_version']}

Generated by `python -m src.train`; all numbers below are measured, not targets.

## Purpose and population
Offline investigation prioritization using public IEEE-CIS competition training data.
All {sum(s['rows'] for s in splits):,} supplied transaction rows were used in this run.
25 predefined features; no resampling, no label-derived features, no competition-test labels.
This is an independent portfolio prototype using public competition data, not an automated fraud verdict.

## Training and validation
Chronological 60/20/20 row targets; identical timestamps remain in one split.
Training-only imputation/encoding; categories unseen in training map to unknown.
Logistic categorical encoding is capped at 100 categories per feature.
LightGBM uses native categorical splits on training-only ordinal codes.
400-tree budget, validation early stopping; best iteration: {metadata['best_iteration']}.
LightGBM was selected using validation AP, then frozen before holdout scoring.
No train+validation refit. All three frozen candidates were evaluated on holdout once.
No post-holdout model/feature/threshold tuning was performed for this release.

## Actual evaluation
AP means sklearn Average Precision; it is not trapezoidal PR-AUC.

{chr(10).join(rows)}

Holdout prevalence: **{m.prevalence:.4%}** across **{int(m.rows):,}** transactions.
The offline capacity policy selects the top **{int(m.k):,}** transactions (ceil(2% of the whole holdout)).
It captures **{int(m.topk_tp):,}** fraud labels, with **{int(m.topk_fp):,}** false alerts
and **{int(m.topk_fn):,}** fraud labels outside the selected set.
This is batch ranking, not a daily/live capacity claim. Ties use ascending transaction ID.

The separate API policy uses `risk_score > {m.threshold:.12g}`;
this threshold comes exclusively from validation. Score ties may reduce validation alerts.
On holdout it flags **{int(m.threshold_alerts):,}** transactions: TP = {int(m.threshold_tp)},
FP={int(m.threshold_fp)}, FN={int(m.threshold_fn)}, TN = {int(m.threshold_tn)}.
A frozen threshold does not guarantee a 2% alert rate after distribution shift.

## Explainability and limitations
Native LightGBM TreeSHAP contributions use raw log-odds, not probability percentages.
Global importance uses 1,000 seeded validation samples; local cases are diagnostic holdout examples.
Additivity is checked against the model's raw margin. Anonymous C/D/id fields retain their names.
No causal interpretation, no calibrated probability, no measured financial savings.
Offset days are not calendar dates. Entities may recur across time splits; no new-customer generalization claim.
Feature availability/label latency in a real deployment is unverified; a real system needs as-of joins,
delayed-label validation, monitoring, security, and domain review.
All fields are assumed available at simulated transaction scoring, as supplied by the competition.
The demo queue is deliberately enriched (top 100 + random 100), so never compute portfolio metrics from it.
Review choices in Streamlit last only for the current session; persistent decision storage is P1.

## Reproduction
See README.md and docs/START_HERE_ID.md. `models/metadata.json` records versions, source hashes,
data hash, policy, feature order, boundaries and artifact hash. The API checks the artifact hash on load.
Training elapsed time in the build environment: {metadata['elapsed_seconds']:.1f} seconds.
Hardware/OS and package differences may change runtime and floating-point results.
'''
    (ROOT / 'reports/model_card.md').write_text(text, encoding = 'utf-8')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('--overwrite', action = 'store_true')
    main(parser.parse_args().overwrite)