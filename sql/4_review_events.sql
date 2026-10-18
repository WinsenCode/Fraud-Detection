-- Run in fraud_detection_database after the data-loading SQL steps.
-- This creates the four-column review table for the no-timestamp demo scope.
-- IF NOT EXISTS does not change an existing table or remove its columns.

CREATE TABLE IF NOT EXISTS fraud.review_events (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    transaction_id BIGINT NOT NULL
        CHECK (transaction_id >= 0),

    model_version TEXT NOT NULL
        CHECK (length(trim(model_version)) > 0),

    action TEXT NOT NULL
        CHECK (action IN ('Review', 'Escalate', 'Close'))
);

CREATE INDEX IF NOT EXISTS idx_review_events_transaction_model
    ON fraud.review_events (
        transaction_id,
        model_version,
        review_id DESC
    );