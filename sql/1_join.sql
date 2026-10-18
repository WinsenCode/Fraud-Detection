CREATE OR REPLACE VIEW fraud.model_data AS
SELECT t.*, i.id_02, i.id_12, i.id_15, i.device_type,
       CASE WHEN i.transaction_id IS NULL THEN 0 ELSE 1 END AS identity_present
FROM fraud.transactions AS t
LEFT JOIN fraud.identities AS i ON t.transaction_id = i.transaction_id;