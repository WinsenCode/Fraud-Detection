SELECT product_cd, COUNT(*) AS transactions, SUM(is_fraud) AS fraud_count,
       AVG(is_fraud::DOUBLE PRECISION) AS fraud_rate,
       AVG(transaction_amt) AS mean_amount,
       AVG(identity_present::DOUBLE PRECISION) AS identity_coverage
FROM fraud.model_data
GROUP BY product_cd
ORDER BY product_cd;