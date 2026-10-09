#!/bin/bash
# Déploie le site, le backend et la vision sur l'UNO Q depuis le dépôt (Mac ou Linux) :
#   deploy/uno-q/deploy.sh [arduino@talos.local]
# Première fois : lancer ensuite sur la carte  sudo bash ~/sentinel/deploy/install-root.sh  puis relancer ce script.
set -euo pipefail
HOST=${1:-arduino@talos.local}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
HERE="$ROOT/deploy/uno-q"

echo "== Build du site (présentation + tableau de bord)"
(cd "$ROOT/frontend" && VITE_API_MODE=live VITE_DASHBOARD_URL=/dashboard/ npm run build)

echo "== Copie vers $HOST"
ssh "$HOST" 'mkdir -p ~/sentinel/{backend,vision,models,faces,snapshots,deploy,www}'
# Pas de rsync sur la carte : archives tar par SSH (.venv et .env de la carte conservés).
send() {  # send <dossier local> <dossier distant> [--clean]
  local clean=""; [ "${3:-}" = --clean ] && clean="rm -rf ~/sentinel/$2/* && "
  COPYFILE_DISABLE=1 tar -C "$1" -cz --exclude .venv --exclude __pycache__ --exclude '*.egg-info' \
    --exclude .env --exclude .pytest_cache --exclude tests . | ssh "$HOST" "${clean}tar -C ~/sentinel/$2 -xzf - 2>/dev/null"
}
send "$ROOT/backend" backend
send "$ROOT/vision" vision
send "$ROOT/models" models
send "$HERE" deploy --clean
send "$ROOT/frontend/dist" www --clean

echo "== Installation sur la carte"
ssh "$HOST" bash -s <<'REMOTE'
set -euo pipefail
cd ~/sentinel
[ -f backend/.env ] || cp deploy/backend.env backend/.env
[ -f vision/.env ] || cp deploy/vision.env vision/.env
for svc in backend vision; do
  [ -x $svc/.venv/bin/pip ] || { rm -rf $svc/.venv; python3 -m venv $svc/.venv; }
  $svc/.venv/bin/pip install -q --upgrade pip
  $svc/.venv/bin/pip install -q ./$svc
done
mkdir -p ~/.config/systemd/user
cp deploy/sentinel-backend.service deploy/sentinel-vision.service ~/.config/systemd/user/
systemctl --user daemon-reload

if [ -w /var/www/sentinel ]; then
  rm -rf /var/www/sentinel/* && cp -r www/. /var/www/sentinel/
  systemctl --user enable --now sentinel-backend sentinel-vision
  systemctl --user restart sentinel-backend sentinel-vision
  echo "Déployé : http://talos.local"
else
  echo "Étape système manquante : sudo bash ~/sentinel/deploy/install-root.sh, puis relancer deploy.sh"
fi
REMOTE
