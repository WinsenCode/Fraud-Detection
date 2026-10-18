import copy
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from api.main import app
from src.common import ROOT, FEATURES, read_json

@pytest.fixture(scope ='module')
def client():
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def payload():
    return read_json(ROOT /'data/sample_request.json')

def test_health_and_valid_request(client, payload):
    assert client.get('/health').json()['feature_count'] == 25
    response = client.post('/predict', json = payload)
    assert response.status_code == 200
    result = response.json()
    assert 0 <= result['risk_score'] <= 1
    assert result['is_alert'] == (result['risk_score'] > result['threshold'])
    assert len(result['top_factors']) == 5

@pytest.mark.parametrize('mutation', ['missing','label','numeric_string','negative_amount','wrong_product','infinity'])
def test_invalid_input_fails_loudly(client, payload, mutation):
    p = copy.deepcopy(payload)
    if mutation =='missing': p.pop('device_type')
    if mutation =='label': p['is_fraud'] = 1
    if mutation =='numeric_string': p['transaction_amt'] ='10.00'
    if mutation =='negative_amount': p['transaction_amt'] = -1
    if mutation =='wrong_product': p['product_cd'] ='UNSUPPORTED'
    if mutation =='infinity':
        import json
        p['transaction_amt'] = '__NONFINITE__'
        raw = json.dumps(p).replace('"__NONFINITE__"', '1e400')

        response = client.post(
            '/predict',
            content=raw,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 422
    else:
        assert client.post('/predict', json = p).status_code == 422

def test_explicit_nulls_and_unseen_categories_are_supported(client, payload):
    payload['device_type'] = None
    payload['card1'] ='new-card-code'
    assert client.post('/predict', json = payload).status_code == 200

def test_online_scores_match_saved_offline_scores(client):
    records = read_json(ROOT /'data/demo_requests.json')
    queue = pd.read_csv(ROOT /'data/demo_queue.csv').set_index('transaction_id')
    for record in [records[0], records[100], records[-1]]:
        response = client.post('/predict', json = record)
        assert response.status_code == 200
        assert response.json()['risk_score'] == pytest.approx(queue.loc[record['transaction_id'],'risk_score'], abs = 1e-9)

def test_full_shap_reconstructs_model_margin(client, payload):
    scorer = app.state.scorer
    frame = pd.DataFrame([{f: payload[f] for f in FEATURES}]).replace({None: np.nan})
    pre = scorer.pipeline.named_steps['preprocessor'].transform(frame)
    booster = scorer.pipeline.named_steps['model'].booster_
    np.testing.assert_allclose(booster.predict(pre, pred_contrib = True).sum(axis = 1),
                               booster.predict(pre, raw_score = True), atol = 1e-7)