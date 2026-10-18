import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = 'ieee-cis-v1-25-features'
TRANSACTION_COLUMNS = {
    'TransactionID': 'transaction_id', 'isFraud': 'is_fraud',
    'TransactionDT': 'transaction_dt', 'TransactionAmt': 'transaction_amt',
    'ProductCD': 'product_cd', 'card1': 'card1', 'card2': 'card2',
    'card4': 'card4', 'card6': 'card6', 'addr1': 'addr1', 'dist1': 'dist1',
    'P_emaildomain': 'p_emaildomain', 'R_emaildomain': 'r_emaildomain',
    'C1': 'c1', 'C2': 'c2', 'C6': 'c6', 'C11': 'c11', 'C13': 'c13',
    'C14': 'c14', 'D1': 'd1', 'D2': 'd2', 'D3': 'd3', 'D10': 'd10', 'D15': 'd15',
}
IDENTITY_COLUMNS = {
    'TransactionID': 'transaction_id', 'id_02': 'id_02', 'id_12': 'id_12',
    'id_15': 'id_15', 'DeviceType': 'device_type',
}
NUMERIC = ['transaction_amt', 'dist1', 'c1', 'c2', 'c6', 'c11', 'c13', 'c14',
           'd1', 'd2', 'd3', 'd10', 'd15', 'id_02']
CATEGORICAL = ['product_cd', 'card1', 'card2', 'card4', 'card6', 'addr1',
               'p_emaildomain', 'r_emaildomain', 'device_type', 'id_12', 'id_15']
FEATURES = NUMERIC + CATEGORICAL
REQUIRED_DIRS = ['data/raw', 'data/processed', 'reports/figures', 'models', 'powerbi/exports']

def check_folders():
    missing = [d for d in REQUIRED_DIRS if not (ROOT / d).is_dir()]
    if missing:
        raise FileNotFoundError(
            f'Create these folders manually in File Explorer: {missing}'
        )
        
def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent = 2, allow_nan = False) + '\n', encoding = 'utf-8')

def read_json(path):
    return json.loads(Path(path).read_text(encoding = 'utf-8'))
