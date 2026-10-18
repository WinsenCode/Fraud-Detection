CREATE SCHEMA IF NOT EXISTS fraud;

CREATE TABLE IF NOT EXISTS fraud.transactions (
    transaction_id BIGINT PRIMARY KEY CHECK (transaction_id >= 0),
    is_fraud SMALLINT NOT NULL CHECK (is_fraud IN (0, 1)),
    transaction_dt BIGINT NOT NULL CHECK (transaction_dt >= 0),
    transaction_amt DOUBLE PRECISION NOT NULL CHECK (transaction_amt >= 0),
    product_cd TEXT NOT NULL, card1 TEXT, card2 TEXT, card4 TEXT, card6 TEXT,
    addr1 TEXT, dist1 DOUBLE PRECISION, p_emaildomain TEXT, r_emaildomain TEXT,
    c1 DOUBLE PRECISION, c2 DOUBLE PRECISION, c6 DOUBLE PRECISION,
    c11 DOUBLE PRECISION, c13 DOUBLE PRECISION, c14 DOUBLE PRECISION,
    d1 DOUBLE PRECISION, d2 DOUBLE PRECISION, d3 DOUBLE PRECISION,
    d10 DOUBLE PRECISION, d15 DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS fraud.identities (
    transaction_id BIGINT PRIMARY KEY CHECK (transaction_id >= 0),
    id_02 DOUBLE PRECISION, id_12 TEXT, id_15 TEXT, device_type TEXT
);
