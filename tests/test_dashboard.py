import os
import pytest
import requests
from streamlit.testing.v1 import AppTest
from src.common import ROOT

def test_api_unavailable_has_clear_message(monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError('API unavailable')
    monkeypatch.setattr(requests,'get', unavailable)
    ui = AppTest.from_file(str(ROOT /'app/dashboard.py')).run(timeout = 20)
    assert not ui.exception
    assert'unavailable' in ui.error[0].value

@pytest.mark.skipif(os.getenv('FRAUD_LIVE_TESTS') !='1', reason ='Start API and set FRAUD_LIVE_TESTS = 1')
def test_live_queue_score_and_review():
    ui = AppTest.from_file(str(ROOT /'app/dashboard.py')).run(timeout = 30)
    assert not ui.exception and not ui.error
    ui.button[0].click().run(timeout = 30)
    assert not ui.exception and not ui.error
    assert ui.session_state['scored_case']['transaction_id'] == ui.selectbox[0].value
    ui.radio[0].set_value('Escalate').run(timeout = 30)
    ui.button[1].click().run(timeout = 30)
    assert not ui.exception
    transaction_id = int(ui.selectbox[0].value)
    model_version = ui.session_state['scored_case']['model_version']
    api_url = os.getenv('FRAUD_API_URL', 'http://127.0.0.1:8000').rstrip('/')

    response = requests.get(
        f'{api_url}/reviews/{transaction_id}',
        params={'model_version': model_version},
        timeout=10
    )
    assert response.status_code == 200

    history = response.json()
    assert history
    assert history[0]['action'] == 'Escalate'

    fresh_ui = AppTest.from_file(
        str(ROOT / 'app/dashboard.py')
    ).run(timeout=30)

    assert not fresh_ui.exception and not fresh_ui.error

    queue = fresh_ui.dataframe[0].value.set_index('transaction_id')
    assert queue.loc[transaction_id, 'review_status'] == 'Escalate'