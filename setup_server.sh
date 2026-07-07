#!/bin/bash
# Setup script for GCP server - Phase 1 Web Trading Platform
set -e

echo "=== Setting up PostgreSQL ==="
sudo -u postgres psql -c "SELECT 1;" > /dev/null 2>&1
echo "PostgreSQL is running"

# Create database if not exists
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = 'trading_platform'" | grep -q 1 || sudo -u postgres createdb trading_platform
echo "Database 'trading_platform' ready"

# Create a password for postgres user for TCP connections
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'admin';"
echo "Postgres password set to 'admin'"

# Enable password auth for local TCP connections
PG_HBA=$(sudo -u postgres psql -t -c "SHOW hba_file;" | tr -d ' ')
if ! grep -q "host.*trading_platform.*md5" "$PG_HBA" 2>/dev/null; then
    echo "host    trading_platform    postgres    127.0.0.1/32    md5" | sudo tee -a "$PG_HBA" > /dev/null
    sudo systemctl reload postgresql
    echo "pg_hba.conf updated for TCP auth"
fi

echo ""
echo "=== Setting up Redis ==="
redis-cli ping
echo "Redis is running"

echo ""
echo "=== Setting up Python environment ==="
cd /home/chandrachv/Kite-algo

# Create .env if not exists
if [ ! -f .env ] || ! grep -q "DATABASE_URL" .env; then
    cat >> .env << 'ENVEOF'

# ===== Web Trading Platform Config =====
DATABASE_URL=postgresql://postgres:admin@localhost:5432/trading_platform
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=gcp-trading-platform-jwt-secret-change-me
ENVEOF
    # Generate encryption key
    EKEY=$(.venv/bin/python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    echo "ENCRYPTION_KEY=$EKEY" >> .env
    echo ".env configured"
else
    echo ".env already has DATABASE_URL"
fi

echo ""
echo "=== Running Alembic Migration ==="
source .venv/bin/activate
export DATABASE_URL=postgresql://postgres:admin@localhost:5432/trading_platform
python -m alembic upgrade head
echo "Migration complete"

echo ""
echo "=== Verifying tables ==="
sudo -u postgres psql -d trading_platform -c "\dt"

echo ""
echo "=== Running Unit Tests ==="
python -m pytest tests/ -q --tb=short 2>&1 | tail -5

echo ""
echo "=== Running Integration Test ==="
python manual_test_phase1.py

echo ""
echo "=== SETUP COMPLETE ==="
