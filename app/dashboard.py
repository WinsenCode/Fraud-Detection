'''One-page triage demo. No training or direct model loading in the UI.'''
import json
import os
from pathlib import Path
import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
API_URL = os.getenv('FRAUD_API_URL', 'http://127.0.0.1:8000').rstrip('/')
st.set_page_config(page_title = 'Fraud Review Desk', page_icon = '🔎', layout = 'wide')
st.title('Fraud Review Desk')
st.caption('IEEE-CIS public data · Offline investigation demo · Human review required')

try:
    response  =  requests.get(f'{API_URL}/health', timeout = 5)
    response.raise_for_status()
    health = response.json()
except requests.RequestException:
    st.error('Scoring service is unavailable. Start FastAPI on port 8000, then refresh this page.')
    st.stop()

queue = pd.read_csv(ROOT / 'data/demo_queue.csv')
records = json.loads((ROOT / 'data/demo_requests.json').read_text(encoding = 'utf-8'))
by_id = {r['transaction_id']: r for r in records}
if set(queue.model_version) != {health['model_version']}:
    st.error('Queue/model version mismatch. Regenerate the demo using the same trained artifact.')
    st.stop()

st.info('This 200-record demo contains the 100 highest holdout scores plus 100 random remaining records. '
        'Its fraud distribution is not representative. Portfolio metrics use the full chronological holdout.')
a, b, c = st.columns(3)
a.metric('Demo transactions', f'{len(queue):,}')
b.metric('Above frozen threshold', f'{int(queue.is_alert.sum()):,}')
c.metric('Model', health['model_version'])
st.caption('Risk scores are not calibrated probabilities. An alert is a review suggestion, not a fraud verdict.')

products = st.multiselect('Product filter', sorted(queue.product_cd.unique()), default = [])
filtered = queue[queue.product_cd.isin(products)] if products else queue
filtered = filtered.sort_values(['risk_score', 'transaction_id'], ascending = [False, True])
try:
    response = requests.get(
        f'{API_URL}/reviews',
        params={'model_version': health['model_version']},
        timeout=10
    )
    response.raise_for_status()

    reviews = {
        item['transaction_id']: item['action']
        for item in response.json()
    }

except (requests.RequestException, ValueError) as exc:
    st.error(f'Unable to load saved review decisions: {exc}')
    st.stop()
view = filtered[['transaction_id', 'transaction_amt', 'product_cd', 'device_type', 'risk_score', 'is_alert']].copy()
view['review_status'] = view.transaction_id.map(reviews).fillna('Unreviewed')
st.subheader('Ranked queue')
st.dataframe(view, hide_index = True, width = 'stretch')
if filtered.empty:
    st.warning('No transactions match the current filter.')
    st.stop()

selected = st.selectbox('Transaction to investigate', filtered.transaction_id.tolist())
left, right = st.columns([1, 1])
with left:
    st.subheader('Transaction detail')
    st.json(by_id[selected], expanded = False)
    if st.button('Score selected transaction via API', type = 'primary'):
        try:
            response = requests.post(f'{API_URL}/predict', json = by_id[selected], timeout = 30)
            response.raise_for_status()
            result = response.json()
            st.session_state['scored_case'] = result
        except (requests.RequestException, ValueError) as exc:
            st.error(f'Scoring failed: {exc}')
    result = st.session_state.get('scored_case')
    if result and result['transaction_id'] == selected:
        st.metric('Live API risk score', f'{result["risk_score"]:.6f}')
        st.write(f'Alert: {result["is_alert"]} · threshold: score > {result["threshold"]:.6f}')
        st.subheader('Factors influencing the model score')
        st.dataframe(pd.DataFrame(result['top_factors']), hide_index = True, width = 'stretch')
        st.caption('Native TreeSHAP, raw log-odds. Positive contributions increase the model score; '
                   'negative contributions decrease it. Top 5 shown; these are not causal explanations.')
with right:
    st.subheader('Analyst decision')

    notice = st.session_state.pop('review_notice', None)
    if notice:
        st.success(notice)

    try:
        response = requests.get(
            f'{API_URL}/reviews/{int(selected)}',
            params={'model_version': health['model_version']},
            timeout=10
        )
        response.raise_for_status()
        history = response.json()

    except (requests.RequestException, ValueError) as exc:
        st.error(f'Unable to load review history: {exc}')
        st.stop()

    current_status = history[0]['action'] if history else 'Unreviewed'
    st.write('Current status:', current_status)

    action = st.radio(
        'Review outcome',
        ['Review', 'Escalate', 'Close'],
        horizontal=True,
        key=f'review_action_{health["model_version"]}_{int(selected)}'
    )

    if st.button('Apply review outcome'):
        payload = {
            'transaction_id': int(selected),
            'model_version': health['model_version'],
            'action': action
        }

        try:
            response = requests.post(
                f'{API_URL}/reviews',
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            saved = response.json()

        except (requests.RequestException, ValueError) as exc:
            st.error(
                f'Could not confirm that the decision was saved: {exc}. '
                'Check the review history before submitting again.'
            )

        else:
            st.session_state['review_notice'] = (
                f'Transaction {saved["transaction_id"]}: '
                f'{saved["action"]} saved '
                f'(review ID {saved["review_id"]}).'
            )
            st.rerun()

    st.caption(
        'Decisions are stored in PostgreSQL. '
        'Each submission adds a new history entry. '
        'No transaction is blocked.'
    )

    st.subheader('Review history')

    if history:
        st.dataframe(
            pd.DataFrame(history)[
                ['review_id', 'transaction_id', 'model_version', 'action']
            ],
            hide_index=True,
            width='stretch'
        )
        st.caption(
            'Up to 100 entries, ordered by descending review ID. '
            'Decision timestamps are not recorded.'
        )
    else:
        st.info('No saved decisions for this transaction and model version.')

    st.subheader('Actual holdout results')

    metrics = pd.read_csv(ROOT / 'reports/metrics.csv')

    st.dataframe(
        metrics.loc[
            metrics.split == 'test',
            ['model', 'average_precision', 'precision_at_k', 'recall_at_k']
        ],
        hide_index=True,
        width='stretch'
    )

    st.caption(
        'Top-K metrics use the top 2% of the whole holdout, '
        'independently of the API threshold policy.'
    )