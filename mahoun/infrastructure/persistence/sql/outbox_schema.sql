-- =============================================================================
-- MAHOUN Transactional Outbox Schema
-- Purpose: Guarantee eventual consistency between Postgres (SoT) and Neo4j.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS governance;

CREATE TYPE governance.outbox_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');

CREATE TABLE IF NOT EXISTS governance.transactional_outbox (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type  VARCHAR(64) NOT NULL, -- e.g., 'Verdict', 'LawArticle'
    aggregate_id    VARCHAR(128) NOT NULL,
    action          VARCHAR(32) NOT NULL,  -- 'INSERT', 'UPDATE', 'DELETE'
    payload         JSONB NOT NULL,
    status          governance.outbox_status DEFAULT 'PENDING',
    retry_count     INT DEFAULT 0,
    error_log       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    processed_at    TIMESTAMPTZ,
    correlation_id  UUID
);

CREATE INDEX idx_outbox_status_pending ON governance.transactional_outbox (status) WHERE status = 'PENDING';
CREATE INDEX idx_outbox_aggregate ON governance.transactional_outbox (aggregate_type, aggregate_id);

-- Example Trigger Function for Automatic Outbox Population
CREATE OR REPLACE FUNCTION governance.tg_outbox_snapshot()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO governance.transactional_outbox (
        aggregate_type, 
        aggregate_id, 
        action, 
        payload, 
        correlation_id
    ) VALUES (
        TG_TABLE_NAME, 
        NEW.id::text, 
        TG_OP, 
        to_jsonb(NEW), 
        current_setting('mahoun.current_correlation_id', true)::uuid
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
