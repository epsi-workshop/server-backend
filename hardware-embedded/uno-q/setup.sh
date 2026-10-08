#!/usr/bin/env bash
# Installe l'API capteurs sur un Arduino UNO Q, depuis un Mac ou un PC Linux.
# Prérequis : carte configurée avec Arduino App Lab (nom, Wi-Fi, mot de passe Linux)
#             et clé SSH autorisée : ssh-copy-id arduino@<nom>.local
# Usage : ./setup.sh [hôte]      (défaut : talos.local)
set -euo pipefail
cd "$(dirname "$0")"

HOST="${1:-talos.local}"
TARGET="arduino@$HOST"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=10 $TARGET"

echo "==> Connexion à $TARGET"
if ! $SSH true 2>/dev/null; then
  echo "ERREUR : connexion SSH impossible sans mot de passe. Lance d'abord :" >&2
  echo "  ssh-copy-id arduino@$HOST" >&2
  exit 1
fi

echo "==> Copie des fichiers"
$SSH 'mkdir -p ~/sensor-api ~/sketches/sensors ~/.config/systemd/user'
scp -q api/*.py api/live.html api/requirements.txt "$TARGET:sensor-api/"
scp -q sketch/sensors/sensors.ino "$TARGET:sketches/sensors/"
scp -q cam-wifi.sh "$TARGET:"
scp -q sensor-api.service "$TARGET:.config/systemd/user/"

echo "==> Environnement Python (uv, sans sudo)"
$SSH 'bash -s' <<'EOF'
set -e
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
cd ~/sensor-api
[ -x .venv/bin/python ] || uv venv -q --python /usr/bin/python3 .venv
uv pip install -q --python .venv/bin/python -r requirements.txt
chmod +x ~/cam-wifi.sh
EOF

echo "==> Sketch du microcontrôleur (compilation + flash)"
$SSH 'bash -s' <<'EOF'
set -e
arduino-cli lib install Arduino_RouterBridge Servo U8g2 >/dev/null
cd ~/sketches/sensors
arduino-cli compile --fqbn arduino:zephyr:unoq . | tail -2
# Après un flash, le MCU ne se réenregistre pas toujours auprès du Bridge :
# on vérifie qu'il répond, sinon on reflashe (jusqu'à 3 fois).
for try in 1 2 3; do
  arduino-cli upload --fqbn arduino:zephyr:unoq . >/dev/null 2>&1
  sleep 12
  if ~/sensor-api/.venv/bin/python - <<'PY'
import socket, msgpack, sys
s = socket.socket(socket.AF_UNIX); s.settimeout(5); s.connect("/run/arduino-router.sock")
s.sendall(msgpack.packb([0, 1, "get_pir", []]))
u = msgpack.Unpacker(raw=False)
while True:
    u.feed(s.recv(4096)); r = next(u, None)
    if r: sys.exit(0 if r[2] is None else 1)
PY
  then echo "MCU OK (tentative $try)"; exit 0; fi
  echo "MCU pas encore joignable via le Bridge, nouveau flash..."
done
echo "ERREUR : le MCU ne répond pas via le Bridge." >&2; exit 1
EOF

echo "==> Service (démarrage automatique au boot)"
$SSH 'systemctl --user daemon-reload && systemctl --user enable sensor-api >/dev/null 2>&1 && systemctl --user restart sensor-api && loginctl enable-linger "$USER"'
sleep 5

echo "==> Test"
curl -sf -m 10 "http://$HOST:8000/health" && echo
curl -sf -m 10 "http://$HOST:8000/sensors" && echo
echo "OK : http://$HOST:8000/docs"
