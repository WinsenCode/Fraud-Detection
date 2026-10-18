import os
import pytest
import requests
from psycopg.rows import dict_row
from src.common import ROOT, read_json
from src.data import connect

API_URL = os.getenv(
    'FRAUD_API_URL', 'http://127.0.0.1:8000'
).rstrip('/')

pytestmark = pytest.mark.skipif(
    os.getenv('RUN_DATABASE_TESTS') != '1'
    or os.getenv('FRAUD_LIVE_TESTS') != '1',
    reason='Start PostgreSQL/API and enable both integration test flags.'
)

def read_database_reviews(payload):
    with connect() as connection:
        assert connection.info.dbname == 'fraud_detection_database'

        with connection.cursor(row_factory=dict_row) as cursor:
            rows = cursor.execute(
                """
                SELECT review_id, transaction_id, model_version, action
                FROM fraud.review_events
                WHERE transaction_id = %s
                  AND model_version = %s
                ORDER BY review_id
                """,
                (
                    payload['transaction_id'],
                    payload['model_version']
                )
            ).fetchall()

    return {row['review_id']: row for row in rows}

@pytest.fixture
def review_case():
    sample = read_json(ROOT / 'data/sample_request.json')
    metadata = read_json(ROOT / 'models/metadata.json')

    payload = {
        'transaction_id': sample['transaction_id'],
        'model_version': metadata['model_version']
    }
    created_ids = []

    try:
        yield payload, created_ids
    finally:
        # Remove only the rows created by this test.
        if created_ids:
            with connect() as connection:
                assert connection.info.dbname == 'fraud_detection_database'

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM fraud.review_events
                        WHERE review_id = ANY(%s)
                          AND transaction_id = %s
                          AND model_version = %s
                        """,
                        (
                            created_ids,
                            payload['transaction_id'],
                            payload['model_version']
                        )
                    )

def save_test_review(review_case, action):
    payload, created_ids = review_case

    response = requests.post(
        f'{API_URL}/reviews',
        json = {**payload, 'action': action},
        timeout = 10
    )
    assert response.status_code == 201, response.text

    saved = response.json()
    created_ids.append(saved['review_id'])

    assert saved['transaction_id'] == payload['transaction_id']
    assert saved['model_version'] == payload['model_version']
    assert saved['action'] == action

    return saved

def test_reviews_are_committed_readable_and_append_only(review_case):
    payload, _ = review_case
    before = read_database_reviews(payload)

    first = save_test_review(review_case, 'Review')
    second = save_test_review(review_case, 'Escalate')

    assert second['review_id'] > first['review_id']

    # A separate database connection must see the committed rows.
    after = read_database_reviews(payload)

    assert after[first['review_id']] == first
    assert after[second['review_id']] == second

    # Existing history must remain unchanged.
    for review_id, row in before.items():
        assert after[review_id] == row

    assert len(after) == len(before) + 2

    # Read the history through a new HTTP session.
    with requests.Session() as session:
        response = session.get(
            f'{API_URL}/reviews/{payload["transaction_id"]}',
            params = {'model_version': payload['model_version']},
            timeout = 10
        )
        assert response.status_code == 200, response.text

        history = response.json()
        assert first in history
        assert second in history
        assert history[0] == second

        response = session.get(
            f'{API_URL}/reviews',
            params = {'model_version': payload['model_version']},
            timeout = 10
        )
        assert response.status_code == 200, response.text

        latest = {
            row['transaction_id']: row
            for row in response.json()
        }
        assert latest[payload['transaction_id']] == second

def test_invalid_action_is_rejected_without_database_changes(review_case):
    payload, _ = review_case
    before = read_database_reviews(payload)

    response = requests.post(
        f'{API_URL}/reviews',
        json = {**payload, 'action': 'Approve'},
        timeout = 10
    )

    assert response.status_code == 422, response.text
    assert read_database_reviews(payload) == before