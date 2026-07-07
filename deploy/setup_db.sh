#!/bin/bash
set -e

echo "Setting trust auth temporarily..."
sudo sed -i 's/md5/trust/g' /etc/postgresql/14/main/pg_hba.conf
sudo sed -i 's/peer/trust/g' /etc/postgresql/14/main/pg_hba.conf
sudo systemctl restart postgresql
sleep 2

echo "Setting postgres password..."
psql -h 127.0.0.1 -U postgres -c "ALTER ROLE postgres WITH PASSWORD 'admin';"

echo "Creating database..."
psql -h 127.0.0.1 -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='trading_platform'" | grep -q 1 || psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE trading_platform;"

echo "Restoring md5 auth..."
sudo sed -i 's/trust/md5/g' /etc/postgresql/14/main/pg_hba.conf
sudo systemctl restart postgresql
sleep 2

echo "Testing connection with password..."
PGPASSWORD=admin psql -h 127.0.0.1 -U postgres -d trading_platform -c "SELECT 1 as test;"

echo "DB SETUP COMPLETE"
