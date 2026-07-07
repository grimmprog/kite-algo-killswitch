-- KillSwitchLog table schema for Multi-User Web Trading Platform
-- Requirements: 2.4, 6.7

CREATE TABLE IF NOT EXISTS killswitch_logs (
    -- Primary key
    id SERIAL PRIMARY KEY,

    -- User reference
    user_id INTEGER NOT NULL,

    -- Trigger details
    trigger_reason VARCHAR(500) NOT NULL,
    loss_percent FLOAT,
    capital_at_trigger FLOAT,
    positions_closed_count INTEGER NOT NULL DEFAULT 0,

    -- Timestamp
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_killswitch_logs_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT chk_killswitch_logs_trigger_reason_nonempty CHECK (LENGTH(TRIM(trigger_reason)) > 0),
    CONSTRAINT chk_killswitch_logs_positions_closed_nonneg CHECK (positions_closed_count >= 0)
);

-- Index on user_id for fast lookups of kill switch events per user
CREATE INDEX IF NOT EXISTS idx_killswitch_logs_user_id ON killswitch_logs (user_id);

-- Comments for documentation
COMMENT ON TABLE killswitch_logs IS 'Logs of kill switch activations for audit and history';
COMMENT ON COLUMN killswitch_logs.user_id IS 'Reference to the user whose kill switch was triggered';
COMMENT ON COLUMN killswitch_logs.trigger_reason IS 'Human-readable reason for kill switch activation (non-empty)';
COMMENT ON COLUMN killswitch_logs.loss_percent IS 'Loss percentage at time of trigger (nullable)';
COMMENT ON COLUMN killswitch_logs.capital_at_trigger IS 'User capital at time of trigger (nullable)';
COMMENT ON COLUMN killswitch_logs.positions_closed_count IS 'Number of positions closed by the kill switch (>= 0)';
COMMENT ON COLUMN killswitch_logs.timestamp IS 'Timestamp when kill switch was activated';
