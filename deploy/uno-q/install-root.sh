#!/bin/bash
# Installation système, une seule fois, sur l'UNO Q : sudo bash ~/sentinel/deploy/install-root.sh
# PostgreSQL + TimescaleDB, Mosquitto (local) et nginx (port 80, site Sentinel).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "À lancer avec sudo."; exit 1; }
USER_NAME=${SUDO_USER:-arduino}
HERE=$(cd "$(dirname "$0")" && pwd)

apt-get update
apt-get install -y python3-venv postgresql postgresql-17-timescaledb mosquitto nginx

# TimescaleDB doit être préchargé par PostgreSQL.
PGCONF=$(ls -d /etc/postgresql/*/main | tail -1)
echo "shared_preload_libraries = 'timescaledb'" > "$PGCONF/conf.d/timescaledb.conf"
systemctl restart postgresql
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='sentinel'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE ROLE sentinel LOGIN PASSWORD 'sentinel'"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='sentinel'" | grep -q 1 \
  || sudo -u postgres createdb -O sentinel sentinel
sudo -u postgres psql -d sentinel -c "CREATE EXTENSION IF NOT EXISTS timescaledb"

# Mosquitto : écoute locale uniquement (backend et vision sur la carte).
cat > /etc/mosquitto/conf.d/sentinel.conf <<'CONF'
listener 1883 127.0.0.1
allow_anonymous true
CONF
systemctl enable --now mosquitto
systemctl restart mosquitto

# Site : fichiers déposés par deploy.sh (sans sudo) dans /var/www/sentinel.
install -d -o "$USER_NAME" -g "$USER_NAME" /var/www/sentinel
install -m 644 "$HERE/nginx.conf" /etc/nginx/sites-available/sentinel
ln -sf /etc/nginx/sites-available/sentinel /etc/nginx/sites-enabled/sentinel
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

# Services utilisateur lancés au démarrage, sans session ouverte.
loginctl enable-linger "$USER_NAME"
echo "Installation système terminée."
