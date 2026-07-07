-- Orders table schema for Multi-User Web Trading Platform
-- Requirements: 1.1, 7.1, 7.4

-- Create custom type for order status enum
DO $$ BEGIN
    CREATE TYPE order_status_enum AS ENUM ('PENDING', 'COMPLETE', 'REJECTED', 'CANCELLED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS orders (
    -- Primary key
    id SERIAL PRIMARY KEY,

    -- User reference
    user_id INTEGER NOT NULL,

    -- Order details
    broker_order_id VARCHAR(100),
    symbol VARCHAR(50) NOT NULL,
    qty INTEGER NOT NULL,
    price FLOAT,

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    retries INTEGER NOT NULL DEFAULT 0,
    error_message VARCHAR(500),

    -- Metadata
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Foreign keys
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,

    -- Constraints
    CONSTRAINT chk_orders_symbol_non_empty CHECK (LENGTH(TRIM(symbol)) > 0),
    CONSTRAINT chk_orders_qty_positive CHECK (qty > 0),
    CONSTRAINT chk_orders_status CHECK (status IN ('PENDING', 'COMPLETE', 'REJECTED', 'CANCELLED')),
    CONSTRAINT chk_orders_retries_non_negative CHECK (retries >= 0)
);

-- Index on user_id for fast lookups
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders (user_id);

-- Comments for documentation
COMMENT ON TABLE orders IS 'Order records for trade execution tracking';
COMMENT ON COLUMN orders.id IS 'Auto-incrementing primary key';
COMMENT ON COLUMN orders.user_id IS 'Reference to the user who placed the order';
COMMENT ON COLUMN orders.broker_order_id IS 'Order ID returned by Zerodha Kite API (nullable until confirmed)';
COMMENT ON COLUMN orders.symbol IS 'Trading symbol (e.g., NIFTY23JUNFUT)';
COMMENT ON COLUMN orders.qty IS 'Order quantity (must be positive)';
COMMENT ON COLUMN orders.price IS 'Execution price (nullable for market orders)';
COMMENT ON COLUMN orders.status IS 'Order status: PENDING, COMPLETE, REJECTED, or CANCELLED';
COMMENT ON COLUMN orders.retries IS 'Number of retry attempts for failed orders (cannot be negative)';
COMMENT ON COLUMN orders.error_message IS 'Error details if order was rejected or failed';
COMMENT ON COLUMN orders.timestamp IS 'Order creation timestamp';
