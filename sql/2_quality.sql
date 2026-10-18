SELECT 'transaction_rows' AS gate, COUNT(*) AS actual, COUNT(*) > 0 AS passed FROM fraud.transactions
UNION ALL SELECT 'identity_rows', COUNT(*), COUNT(*) > 0 FROM fraud.identities
UNION ALL SELECT 'transaction_duplicate_keys', COUNT(*) - COUNT(DISTINCT transaction_id),
    COUNT(*) = COUNT(DISTINCT transaction_id) FROM fraud.transactions
UNION ALL SELECT 'identity_duplicate_keys', COUNT(*) - COUNT(DISTINCT transaction_id),
    COUNT(*) = COUNT(DISTINCT transaction_id) FROM fraud.identities
UNION ALL SELECT 'joined_rows', COUNT(*), COUNT(*) = (SELECT COUNT(*) FROM fraud.transactions)
    FROM fraud.model_data
UNION ALL SELECT 'invalid_labels', COUNT(*), COUNT(*) = 0 FROM fraud.transactions
    WHERE is_fraud IS NULL OR is_fraud NOT IN (0, 1)
UNION ALL SELECT 'invalid_time', COUNT(*), COUNT(*) = 0 FROM fraud.transactions
    WHERE transaction_dt IS NULL OR transaction_dt < 0
UNION ALL SELECT 'orphan_identity_keys', COUNT(*), COUNT(*) = 0 FROM fraud.identities AS i
    LEFT JOIN fraud.transactions AS t ON i.transaction_id = t.transaction_id WHERE t.transaction_id IS NULL;