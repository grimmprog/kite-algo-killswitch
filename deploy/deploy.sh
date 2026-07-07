#!/bin/bash
# =============================================================================
# Full Deployment Script for kite-algo on Ubuntu EC2
# Installs: Redis, Python venv, Node dependencies, Nginx config, Systemd services
# =============================================================================

set -e

APP_DIR="/var/www/kite-algo"
APP_USER="ubuntu"

echo "===== 1. System packages ====="
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip redis-server nginx postgresql-client curl

# Enable and start Redis
sudo systemctl enable redis-server
sudo systemctl start redis-server

echo "===== 2. Create app directory ====="
sudo mkdir -p $APP_DIR
sudo chown $APP_USER:$APP_USER $APP_DIR

echo "===== 3. Setup Python virtual environment ====="
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

echo "===== 4. Setup PostgreSQL database ====="
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = 'trading_platform'" | grep -q 1 || \
  sudo -u postgres createdb trading_platform
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname = 'postgres'" | grep -q 1 || \
  sudo -u postgres createuser postgres
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'admin';" 2>/dev/null || true

echo "===== 5. Run Alembic migrations ====="
cd $APP_DIR
source venv/bin/activate
alembic upgrade head || echo "Migrations may need manual review"

echo "===== 6. Build frontend ====="
cd $APP_DIR/frontend
npm install
npm run build

echo "===== 7. Setup Nginx ====="
sudo cp $APP_DIR/deploy/nginx.conf /etc/nginx/sites-available/kite-algo
sudo ln -sf /etc/nginx/sites-available/kite-algo /etc/nginx/sites-enabled/kite-algo
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "===== 8. Setup systemd services ====="
sudo cp $APP_DIR/deploy/kite-algo-backend.service /etc/systemd/system/
sudo cp $APP_DIR/deploy/kite-algo-celery.service /etc/systemd/system/
sudo cp $APP_DIR/deploy/kite-algo-celery-beat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kite-algo-backend kite-algo-celery kite-algo-celery-beat
sudo systemctl restart kite-algo-backend kite-algo-celery kite-algo-celery-beat

echo "===== 9. Verify ====="
sleep 3
sudo systemctl status kite-algo-backend --no-pager | head -10
sudo systemctl status kite-algo-celery --no-pager | head -10
curl -s http://localhost:8000/docs | head -5 && echo "Backend OK" || echo "Backend may still be starting..."

echo ""
echo "===== DEPLOYMENT COMPLETE ====="
echo "Frontend: http://13.233.14.215"
echo "Backend API: http://13.233.14.215/api/v1/"
echo "API Docs: http://13.233.14.215/api/docs"
echo "Kite Callback: http://13.233.14.215/callback"
