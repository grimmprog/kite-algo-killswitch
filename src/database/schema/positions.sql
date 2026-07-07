-- Positions table schema for Multi-User Web Trading Platform (Live Snapshot)
-- Requirements: 2.1, 2.2, 2.3

CREATE TABLE IF NOT EXISTS positions (
    -- Primary key
    id SERIAL PRIMARY KEY,

    -- User reference (one position record per user)
    user_id INTEGER NOT NULL,

    -- Greeks exposure
    net_delta FLOAT NOT NULL DEFAULT 0.0,
    net_gamma FLOAT NOT NULL DEFAULT 0.0,
    net_vega FLOAT NOT NULL DEFAULT 0.0,

    -- Risk metrics
    margin_used FLOAT NOT NULL DEFAULT 0.0,
    unrealized_pnl FLOAT NOT NULL DEFAULT 0.0,

    -- Metadata
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_positions_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT uq_positions_user_id UNIQUE (user_id),
    CONSTRAINT chk_positions_margin_non_negative CHECK (margin_used >= 0)
);

-- Trigger function to auto-update updated_at on row change
CREATE OR REPLACE FUNCTION update_positions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to fire before any update on positions
DROP TRIGGER IF EXISTS trg_positions_updated_at ON positions;
CREATE TRIGGER trg_positions_updated_at
    BEFORE UPDATE ON positions
    FOR EACH ROW
    EXECUTE FUNCTION update_positions_updated_at();

-- Index on user_id for fast lookups (unique constraint already creates one, but explicit for clarity)
CREATE INDEX IF NOT EXISTS idx_positions_user_id ON positions (user_id);

-- Comments for documentation
COMMENT ON TABLE positions IS 'Live snapshot of per-user position metrics and Greeks exposure';
COMMENT ON COLUMN positions.user_id IS 'Reference to users.id (one record per user)';
COMMENT ON COLUMN positions.net_delta IS 'Net delta exposure across all positions';
COMMENT ON COLUMN positions.net_gamma IS 'Net gamma exposure across all positions';
COMMENT ON COLUMN positions.net_vega IS 'Net vega exposure across all positions';
COMMENT ON COLUMN positions.margin_used IS 'Total margin used by open positions (cannot be negative)';
COMMENT ON COLUMN positions.unrealized_pnl IS 'Current unrealized profit/loss across all open positions';
COMMENT ON COLUMN positions.updated_at IS 'Timestamp of last update (auto-updated via trigger)';
