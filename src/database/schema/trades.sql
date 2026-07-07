-- Trades table schema for Multi-User Web Trading Platform
-- Requirements: 1.1, 2.1, 2.2, 2.3

-- Create custom type for trade side enum
DO $$ BEGIN
    CREATE TYPE trade_side_enum AS ENUM ('BUY', 'SELL');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Create custom type for trade status enum
DO $$ BEGIN
    CREATE TYPE trade_status_enum AS ENUM ('OPEN', 'CLOSED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Create custom type for exchange enum
DO $$ BEGIN
    CREATE TYPE exchange_enum AS ENUM ('NSE', 'NFO', 'BSE', 'BFO');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS trades (
    -- Primary key
    id SERIAL PRIMARY KEY,

    -- Foreign key to users
    user_id INTEGER NOT NULL,

    -- Trade details
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(10) NOT NULL,
    qty INTEGER NOT NULL,
    side VARCHAR(10) NOT NULL,

    -- Pricing
    entry_price FLOAT NOT NULL,
    exit_price FLOAT,
    pnl FLOAT NOT NULL DEFAULT 0.0,

    -- Risk tracking
    margin_used FLOAT,
    risk_snapshot_json JSON,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',

    -- Timestamps
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    exit_timestamp TIMESTAMP,

    -- Foreign key constraints
    CONSTRAINT fk_trades_user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,

    -- Validation constraints
    CONSTRAINT chk_trades_symbol_non_empty CHECK (LENGTH(TRIM(symbol)) > 0),
    CONSTRAINT chk_trades_exchange CHECK (exchange IN ('NSE', 'NFO', 'BSE', 'BFO')),
    CONSTRAINT chk_trades_qty_non_zero CHECK (qty != 0),
    CONSTRAINT chk_trades_entry_price_positive CHECK (entry_price > 0),
    CONSTRAINT chk_trades_side CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT chk_trades_status CHECK (status IN ('OPEN', 'CLOSED'))
);

-- Index on user_id for fast lookups of user trades
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades (user_id);

-- Index on timestamp for time-based queries and trade history
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades (timestamp);

-- Composite index for filtering user trades by status
CREATE INDEX IF NOT EXISTS idx_trades_user_status ON trades (user_id, status);

-- Comments for documentation
COMMENT ON TABLE trades IS 'Trade records for the multi-user web trading platform';
COMMENT ON COLUMN trades.user_id IS 'Foreign key referencing the user who placed this trade';
COMMENT ON COLUMN trades.symbol IS 'Trading symbol (e.g., NIFTY23DEC18000CE)';
COMMENT ON COLUMN trades.exchange IS 'Exchange: NSE, NFO, BSE, or BFO';
COMMENT ON COLUMN trades.qty IS 'Trade quantity (positive for long, negative for short)';
COMMENT ON COLUMN trades.side IS 'Trade side: BUY or SELL';
COMMENT ON COLUMN trades.entry_price IS 'Entry price at trade execution (must be positive)';
COMMENT ON COLUMN trades.exit_price IS 'Exit price when trade is closed (nullable for open trades)';
COMMENT ON COLUMN trades.pnl IS 'Profit and loss for this trade (default 0.0)';
COMMENT ON COLUMN trades.margin_used IS 'Margin consumed by this trade';
COMMENT ON COLUMN trades.risk_snapshot_json IS 'JSON snapshot of risk metrics at time of entry';
COMMENT ON COLUMN trades.status IS 'Trade status: OPEN or CLOSED';
COMMENT ON COLUMN trades.timestamp IS 'Trade entry timestamp';
COMMENT ON COLUMN trades.exit_timestamp IS 'Trade exit timestamp (nullable for open trades)';
