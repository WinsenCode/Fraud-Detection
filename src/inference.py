'''Load the exact fitted pipeline; score and explain with one feature contract.'''
import numpy as np
import pandas as pd
import joblib
from src.common import ROOT, FEATURES, CONTRACT_VERSION, read_json, sha256

class FraudScorer:
    def __init__(self, model_dir = None):
        model_dir = model_dir or ROOT / 'models'
        self.metadata = read_json(model_dir / 'metadata.json')
        if self.metadata['status'] != 'complete' or self.metadata['contract_version'] != CONTRACT_VERSION:
            raise ValueError('Incomplete model or incompatible feature contract.')
        if self.metadata['features'] != FEATURES:
            raise ValueError('Feature order does not match the saved model.')
        artifact = model_dir / 'pipeline.joblib'
        if sha256(artifact) != self.metadata['artifact_sha256']:
            raise ValueError('Artifact checksum mismatch. Restore or retrain; do not edit the hash.')
        # Only load artifacts you trust; joblib/pickle is executable serialization.
        self.pipeline = joblib.load(artifact)
        self.threshold = self.metadata['thresholds']['lightgbm']
        self.version = self.metadata['model_version']

    def predict(self, record):
        frame = pd.DataFrame([{name: record[name] for name in FEATURES}], columns = FEATURES)
        frame = frame.replace({None: np.nan})
        risk_score = float(self.pipeline.predict_proba(frame)[0, 1])
        encoded = self.pipeline.named_steps['preprocessor'].transform(frame)
        values = self.pipeline.named_steps['model'].booster_.predict(encoded, pred_contrib = True)[0]
        # Sum includes the bias term. The resulting sigmoid must reproduce inference.
        reconstructed = float(1 / (1 + np.exp(-np.clip(values.sum(), -700, 700))))
        if not np.isclose(risk_score, reconstructed, atol = 1e-7):
            raise ValueError('Explanation and prediction do not match.')
        order = np.argsort(-np.abs(values[:-1]))[:5]
        return {
            'transaction_id': record['transaction_id'], 'risk_score': risk_score,
            'is_alert': risk_score > self.threshold, 'threshold': self.threshold,
            'threshold_operator': '>', 'model_version': self.version,
            'contribution_unit': 'raw_log_odds', 'expected_log_odds': float(values[-1]),
            'top_factors': [{'feature': FEATURES[i], 'value': record[FEATURES[i]],
                             'contribution': float(values[i])} for i in order],
        }