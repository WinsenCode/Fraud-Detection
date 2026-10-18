import numpy as np
import pandas as pd
import pytest
from src.common import NUMERIC, CATEGORICAL, FEATURES
from src.features import chronological_split, preprocessing
from src.data import validate_source
from src.evaluate import evaluate, validation_threshold, rank_indices

def test_time_boundaries_keep_equal_timestamps_together():
    data = pd.DataFrame({'transaction_id': range(100),'transaction_dt': np.repeat(range(10), 10),
                        'is_fraud': [0, 1] * 50})
    train, validation, test, _ = chronological_split(data.sample(frac = 1, random_state = 3))
    assert train.transaction_dt.max() < validation.transaction_dt.min()
    assert validation.transaction_dt.max() < test.transaction_dt.min()
    sets = [set(p.transaction_id) for p in [train, validation, test]]
    assert not sets[0] & sets[1] and not sets[1] & sets[2] and not sets[0] & sets[2]
    assert len(set.union(*sets)) == 100

def test_identical_times_cannot_form_three_time_blocks():
    data = pd.DataFrame({'transaction_id': range(10),'transaction_dt': [100] * 10,
                        'is_fraud': [0, 1] * 5})
    with pytest.raises(ValueError):
        chronological_split(data)

def test_preprocessing_does_not_learn_validation_statistics():
    train = pd.DataFrame({**{f: [1.0, 3.0, np.nan] for f in NUMERIC},
                          **{f: ['a','b', np.nan] for f in CATEGORICAL}})
    validation = pd.DataFrame({**{f: [np.nan, 100000.0] for f in NUMERIC},
                               **{f: ['future-only','a'] for f in CATEGORICAL}})
    pre = preprocessing('lightgbm').fit(train)
    encoded = pre.transform(validation)
    assert encoded[0, 0] == 2.0  # Median of training only.
    assert encoded[0, len(NUMERIC)] == -1  # Future category never learned.
    assert'future-only' not in pre.named_transformers_['categorical'].named_steps['encoder'].categories_[0]
    assert'is_fraud' not in FEATURES and'transaction_id' not in FEATURES and'transaction_dt' not in FEATURES

def test_metrics_against_hand_calculation():
    result = evaluate([1, 0, 1, 0], [.9, .8, .7, .1], [1, 2, 3, 4], .5, .75)
    assert result['average_precision'] == pytest.approx((1 + 2/3)/2)
    assert result['precision_at_k'] == .5 and result['recall_at_k'] == .5
    assert [result[k] for k in ['threshold_tp','threshold_fp','threshold_fn','threshold_tn']] == [1, 1, 1, 1]


def test_ties_are_capacity_safe_and_label_independent():
    scores = np.array([.2, .2, .2, .2])
    threshold = validation_threshold(scores, .25)
    assert (scores > threshold).sum() <= 1
    assert rank_indices(scores, [4, 2, 1, 3]).tolist() == [2, 1, 3, 0]

@pytest.mark.parametrize('frame', [pd.DataFrame({'transaction_id': [1, 1]}),
                                 pd.DataFrame({'transaction_id': [1, np.nan]}),
                                 pd.DataFrame({'transaction_id': [1, 2.5]})])
def test_source_duplicate_missing_fractional_ids_rejected(frame):
    with pytest.raises(ValueError):
        validate_source(frame)