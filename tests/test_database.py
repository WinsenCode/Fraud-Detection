import os
import pytest
import psycopg
from psycopg.rows import dict_row
from src.common import ROOT, read_json
from src.data import connect

pytestmark = pytest.mark.skipif(os.getenv('RUN_DATABASE_TESTS') != '1', reason = 'Set RUN_DATABASE_TESTS = 1 after loading PostgreSQL')

def test_actual_database_counts_and_checks():
    with connect() as connection:
        with connection.cursor(row_factory = dict_row) as cur:
            gates = cur.execute((ROOT / 'sql/2_quality.sql').read_text()).fetchall()
            assert all(g['passed'] for g in gates)
            n = cur.execute('SELECT count(*) AS n FROM fraud.model_data').fetchone()['n']
            assert n == read_json(ROOT / 'reports/data_audit.json')['transaction_rows']
            cur.execute('SAVEPOINT bad_row')
            with pytest.raises(psycopg.errors.UniqueViolation):
                cur.execute('INSERT INTO fraud.transactions SELECT * FROM fraud.transactions LIMIT 1')
            cur.execute('ROLLBACK TO SAVEPOINT bad_row')
            cur.execute('SAVEPOINT bad_label')
            with pytest.raises(psycopg.errors.CheckViolation):
               cur.execute(
                   'INSERT INTO fraud.transactions '
                   '(transaction_id, is_fraud, transaction_dt, transaction_amt, product_cd) '
                   'VALUES (%s, %s, %s, %s, %s)',
                   (9223372036854775806, 2, 0, 1, 'W')
                   )
            cur.execute('ROLLBACK TO SAVEPOINT bad_label')