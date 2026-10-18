'''Two commands: prepare selected columns, then load/join/audit in PostgreSQL.'''
import argparse
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from src.common import (ROOT, TRANSACTION_COLUMNS, IDENTITY_COLUMNS, CATEGORICAL,
                        FEATURES, CONTRACT_VERSION, check_folders, sha256, read_json, write_json)

def validate_source(frame, labeled = False):
    ids = frame['transaction_id']
    if ids.isna().any() or ids.duplicated().any() or (ids < 0).any() or (ids % 1 != 0).any():
        raise ValueError('transaction_id must be unique, non-null, non-negative integers.')
    if labeled:
        if not frame['is_fraud'].isin([0, 1]).all():
            raise ValueError('is_fraud must contain only 0 and 1, with no missing labels.')
        for name in ['transaction_dt', 'transaction_amt']:
            if frame[name].isna().any() or not np.isfinite(frame[name]).all() or (frame[name] < 0).any():
                raise ValueError(f'Invalid values in {name}.')
        if (frame['transaction_dt'] % 1 != 0).any():
            raise ValueError('transaction_dt must be an integer offset.')

def prepare():
    check_folders()
    manifest = {'contract_version': CONTRACT_VERSION, 'sampling': 'none; all training rows',
                'features': FEATURES, 'sources': {}}
    for name, mapping in [('transaction', TRANSACTION_COLUMNS), ('identity', IDENTITY_COLUMNS)]:
        source = ROOT / f'data/raw/train_{name}.csv'
        # Selecting columns reduces RAM; selecting rows could change the population.
        frame = pd.read_csv(source, usecols = list(mapping), low_memory = False).rename(columns = mapping)
        frame = frame[list(mapping.values())]
        validate_source(frame, labeled = (name == 'transaction'))
        # Numeric-looking IDs are categories, never quantities. Keep a stable string format.
        for col in ['card1', 'card2', 'addr1']:
            if col in frame:
                frame[col] = frame[col].astype('Int64').astype('string')
        target = ROOT / f'data/processed/{name}.csv'
        frame.to_csv(target, index = False)
        manifest['sources'][name] = {
            'path': str(source.relative_to(ROOT)).replace('\\', '/'),
            'source_sha256': sha256(source), 'rows': len(frame),
            'selected_columns': list(frame.columns), 'selected_sha256': sha256(target),
        }
        print(f'Prepared {name}: {len(frame):,} rows, {len(frame.columns)} columns', flush = True)
    write_json(ROOT / 'reports/source_manifest.json', manifest)

def connect():
    load_dotenv(ROOT / '.env', override = False)
    # Separate fields avoid password URL-escaping problems. Nothing is printed.
    return psycopg.connect(host = os.getenv('PGHOST', 'localhost'),
                           port = os.getenv('PGPORT', '5432'),
                           dbname = os.getenv('PGDATABASE', 'fraud_detection_database'),
                           user = os.getenv('PGUSER', 'postgres'),
                           password = os.getenv('PGPASSWORD', ''), connect_timeout = 10)

def load(replace = False):
    check_folders()
    manifest = read_json(ROOT / 'reports/source_manifest.json')
    for name, info in manifest['sources'].items():
        if sha256(ROOT / f'data/processed/{name}.csv') != info['selected_sha256']:
            raise ValueError('Prepared CSV has changed. Rerun prepare; do not edit hashes manually.')
    with connect() as conn:
        with conn.cursor(row_factory = dict_row) as cur:
            database = cur.execute('SELECT current_database() AS name').fetchone()['name']
            if database in {'postgres', 'template0', 'template1', 'property_analytics', 'property_portfolio', 'property_analytics_database'}:
                raise ValueError('Use a separate fraud database, not a system/property database.')
            cur.execute((ROOT / 'sql/0_schema.sql').read_text())
            count = cur.execute('SELECT (SELECT count(*) FROM fraud.transactions) + '
                                '(SELECT count(*) FROM fraud.identities) AS n').fetchone()['n']
            if count and not replace:
                raise ValueError('Fraud tables already contain data. Use --replace for an intentional reload.')
            if count:
                cur.execute('TRUNCATE fraud.transactions, fraud.identities')
            for name, table in [('transaction', 'transactions'), ('identity', 'identities')]:
                with cur.copy(f'COPY fraud.{table} FROM STDIN WITH (FORMAT CSV, HEADER TRUE)') as copy:
                    with (ROOT / f'data/processed/{name}.csv').open('rb') as stream:
                        while chunk := stream.read(1024 * 1024):
                            copy.write(chunk)
            cur.execute((ROOT / 'sql/1_join.sql').read_text())
            gates = cur.execute((ROOT / 'sql/2_quality.sql').read_text()).fetchall()
            if not all(gate['passed'] for gate in gates):
                raise ValueError(f'SQL integrity failure: {gates}')
            counts = {r['gate']: r['actual'] for r in gates}
            if counts['transaction_rows'] != manifest['sources']['transaction']['rows']:
                raise ValueError('PostgreSQL/source transaction count mismatch.')
            if counts['identity_rows'] != manifest['sources']['identity']['rows']:
                raise ValueError('PostgreSQL/source identity count mismatch.')
            joined = ROOT / 'data/processed/model_data.csv'
            with cur.copy('COPY (SELECT * FROM fraud.model_data ORDER BY transaction_dt, transaction_id) '
                          'TO STDOUT WITH (FORMAT CSV, HEADER TRUE)') as copy:
                with joined.open('wb') as stream:
                    for block in copy:
                        stream.write(block)
            kpis = cur.execute((ROOT / 'sql/3_business_kpis.sql').read_text()).fetchall()
            pg_version = cur.execute('SHOW server_version').fetchone()['server_version']
    audit_export(gates, kpis, database, pg_version)

def audit_export(gates, kpis, database, pg_version, execution_engine = 'native_postgresql'):
    '''Audit the actual SQL export; engine provenance is recorded, never inferred.'''
    manifest = read_json(ROOT / 'reports/source_manifest.json')
    counts = {r['gate']: int(r['actual']) for r in gates}
    if not all(g['passed'] for g in gates):
        raise ValueError('SQL quality gates failed.')
    for name in ['transaction', 'identity']:
        if counts[f'{name}_rows'] != manifest['sources'][name]['rows']:
            raise ValueError(f'SQL/source row count mismatch for {name}.')
    joined = ROOT / 'data/processed/model_data.csv'
    pd.DataFrame(gates).to_csv(ROOT / 'reports/sql_quality.csv', index = False)
    pd.DataFrame(kpis).to_csv(ROOT / 'reports/data_kpis.csv', index = False)
    frame = read_model_data()
    missing = pd.DataFrame({'feature': FEATURES,
                            'missing_count': frame[FEATURES].isna().sum().values,
                            'missing_pct': frame[FEATURES].isna().mean().values * 100})
    missing.to_csv(ROOT / 'reports/missingness.csv', index = False)
    audit = {'status': 'passed', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
             'contract_version': CONTRACT_VERSION, 'database': database, 'postgres_version': pg_version,
             'execution_engine': execution_engine,
             'transaction_rows': len(frame), 'identity_rows': counts['identity_rows'],
             'joined_rows': counts['joined_rows'], 'fraud_count': int(frame.is_fraud.sum()),
             'fraud_prevalence': float(frame.is_fraud.mean()),
             'missing_identity_rows': int((frame.identity_present == 0).sum()),
             'time_min': int(frame.transaction_dt.min()), 'time_max': int(frame.transaction_dt.max()),
             'model_data_sha256': sha256(joined), 'sql_gates': gates}
    write_json(ROOT / 'reports/data_audit.json', audit)
    print(f'SQL gates passed. Exported {len(frame):,} joined rows; prevalence {frame.is_fraud.mean():.4%}.')

def read_model_data():
    frame = pd.read_csv(ROOT / 'data/processed/model_data.csv',
                        dtype = {col: str for col in CATEGORICAL})
    # sklearn imputers use np.nan; avoid mixing pd.NA and Python None.
    frame[CATEGORICAL] = frame[CATEGORICAL].fillna(np.nan)
    return frame

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('command', choices = ['prepare', 'load'])
    parser.add_argument('--replace', action = 'store_true', help='Reload only the two fraud tables.')
    args = parser.parse_args()
    prepare() if args.command == 'prepare' else load(args.replace)