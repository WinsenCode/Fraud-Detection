'''Training-only preprocessing and time blocks that never split a timestamp.'''
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from src.common import NUMERIC, CATEGORICAL

def chronological_split(frame, train_fraction = 0.6, validation_fraction = 0.2):
    if not (0 < train_fraction < 1 and 0 < validation_fraction < 1 - train_fraction):
        raise ValueError('Invalid split fractions.')
    ordered = frame.sort_values(['transaction_dt', 'transaction_id']).reset_index(drop = True)
    times = ordered.transaction_dt
    train_end = int(times.iloc[int(len(ordered) * train_fraction)])
    val_end = int(times.iloc[int(len(ordered) * (train_fraction + validation_fraction))])
    train = ordered[times < train_end].copy()
    validation = ordered[(times >= train_end) & (times < val_end)].copy()
    test = ordered[times >= val_end].copy()
    for name, part in [('train', train), ('validation', validation), ('test', test)]:
        if part.empty or part.is_fraud.nunique() != 2:
            raise ValueError(f'{name} needs rows from both classes. Check data/time boundaries.')
    assert train.transaction_dt.max() < validation.transaction_dt.min()
    assert validation.transaction_dt.max() < test.transaction_dt.min()
    assert len(train) + len(validation) + len(test) == len(frame)
    return train, validation, test, {'train_end_exclusive': train_end, 'validation_end_exclusive': val_end}

def preprocessing(kind):
    numeric = [('imputer', SimpleImputer(strategy = 'median', keep_empty_features = True))]
    if kind == 'logistic':
        numeric.append(('scale', StandardScaler()))
        encoder = OneHotEncoder(handle_unknown = 'infrequent_if_exist', min_frequency = 20,
                                max_categories = 100, sparse_output = True)
    elif kind == 'lightgbm':
        encoder = OrdinalEncoder(handle_unknown = 'use_encoded_value', unknown_value = -1, dtype = np.float64)
    else:
        raise ValueError(f'Unknown preprocessing kind: {kind}')
    categorical = Pipeline([('imputer', SimpleImputer(strategy = 'constant', fill_value = '__MISSING__',
                                                       keep_empty_features = True)), ('encoder', encoder)])
    return ColumnTransformer([('numeric', Pipeline(numeric), NUMERIC),
                              ('categorical', categorical, CATEGORICAL)],
                             verbose_feature_names_out = False)