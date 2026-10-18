'''Ranking metrics and a frozen score threshold are intentionally separate.'''
import math
import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score

def capacity_k(n, rate):
    if n < 1 or not 0 < rate < 1:
        raise ValueError('Use a nonempty batch and alert_rate strictly between 0 and 1.')
    return min(n, max(1, math.ceil(n * rate)))

def rank_indices(scores, transaction_ids):
    # Labels never participate in ranking. Ascending ID is the fixed tie-break.
    return np.lexsort((np.asarray(transaction_ids), -np.asarray(scores)))

def validation_threshold(scores, rate):
    '''Use strict > to keep validation alerts at or below capacity even with ties.'''
    scores = np.asarray(scores)
    k = capacity_k(len(scores), rate)
    if k == len(scores):
        return float(np.nextafter(scores.min(), -np.inf))
    return float(np.sort(scores)[::-1][k])

def evaluate(y_true, scores, transaction_ids, rate, threshold):
    y = np.asarray(y_true, dtype = int)
    scores = np.asarray(scores, dtype = float)
    if len(y) != len(scores) or not np.isfinite(scores).all():
        raise ValueError('Invalid score vector.')
    k = capacity_k(len(y), rate)
    top = rank_indices(scores, transaction_ids)[:k]
    tp = int(y[top].sum())
    tn_t, fp_t, fn_t, tp_t = confusion_matrix(y, scores > threshold, labels = [0, 1]).ravel()
    positives = int(y.sum())
    return {
        'rows': len(y), 'fraud_count': positives, 'prevalence': float(y.mean()),
        'average_precision': float(average_precision_score(y, scores)),
        'roc_auc': float(roc_auc_score(y, scores)), 'k': k,
        'precision_at_k': tp / k, 'recall_at_k': tp / positives if positives else 0.0,
        'topk_tp': tp, 'topk_fp': k - tp, 'topk_fn': positives - tp,
        'topk_tn': len(y) - positives - (k - tp),
        'threshold': threshold, 'threshold_alerts': int(tp_t + fp_t),
        'threshold_tp': int(tp_t), 'threshold_fp': int(fp_t),
        'threshold_fn': int(fn_t), 'threshold_tn': int(tn_t),
        'threshold_precision': float(tp_t / (tp_t + fp_t)) if tp_t + fp_t else 0.0,
        'threshold_recall': float(tp_t / positives) if positives else 0.0,
    }