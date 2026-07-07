-- Users table schema for Multi-User Web Trading Platform
-- Requirements: 1.1, 3.1, 2.4

-- Create custom type for risk profile enum
DO $$ BEGIN
    CREATE TYPE risk_profile_enum AS ENUM ('conservative', 'moderate', 'aggressive');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS users (
    -- Primary key
    id SERIAL PRIMARY KEY,

    -- Authentication
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,

    -- Trading configuration
    capital FLOAT NOT NULL DEFAULT 100000.0,
    risk_profile VARCHAR(50) NOT NULL DEFAULT 'moderate',

    -- Risk thresholds
    daily_loss_limit_percent FLOAT NOT NULL DEFAULT 2.0,
    max_trade_risk_percent FLOAT NOT NULL DEFAULT 1.0,

    -- Kill switch state
    killswitch_state BOOLEAN NOT NULL DEFAULT FALSE,

    -- Broker integration (encrypted tokens)
    broker_access_token VARCHAR(500),
    broker_refresh_token VARCHAR(500),
    broker_token_expiry TIMESTAMP,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Constraints
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT chk_users_capital_positive CHECK (capital > 0),
    CONSTRAINT chk_users_risk_profile CHECK (risk_profile IN ('conservative', 'moderate', 'aggressive')),
    CONSTRAINT chk_users_daily_loss_limit CHECK (daily_loss_limit_percent >= 0.5 AND daily_loss_limit_percent <= 10.0),
    CONSTRAINT chk_users_max_trade_risk CHECK (max_trade_risk_percent >= 0.1 AND max_trade_risk_percent <= 5.0)
);

-- Index on email for fast lookups during authentication
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Comments for documentation
COMMENT ON TABLE users IS 'User accounts for the multi-user web trading platform';
COMMENT ON COLUMN users.email IS 'Unique user email address used for authentication';
COMMENT ON COLUMN users.password_hash IS 'Bcrypt hashed password with cost factor 12';
COMMENT ON COLUMN users.capital IS 'User trading capital in INR (must be positive)';
COMMENT ON COLUMN users.risk_profile IS 'Risk appetite: conservative, moderate, or aggressive';
COMMENT ON COLUMN users.daily_loss_limit_percent IS 'Max daily loss percentage before kill switch triggers (0.5-10.0)';
COMMENT ON COLUMN users.max_trade_risk_percent IS 'Max risk per trade as percentage of capital (0.1-5.0)';
COMMENT ON COLUMN users.killswitch_state IS 'Whether trading is blocked for this user';
COMMENT ON COLUMN users.broker_access_token IS 'Fernet-encrypted Zerodha Kite access token';
COMMENT ON COLUMN users.broker_refresh_token IS 'Fernet-encrypted Zerodha Kite refresh token';
COMMENT ON COLUMN users.broker_token_expiry IS 'Expiry timestamp for broker access token';
COMMENT ON COLUMN users.created_at IS 'Account creation timestamp';
COMMENT ON COLUMN users.last_login IS 'Most recent login timestamp';
COMMENT ON COLUMN users.is_active IS 'Whether the user account is active';
