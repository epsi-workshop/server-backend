#!/usr/bin/env bash
# Flash de l'ESP32-CAM (macOS / Linux).
# Usage : ./flash.sh            (détecte le port automatiquement)
#         ./flash.sh /dev/ttyUSB0
set -euo pipefail
cd "$(dirname "$0")"

URL=https://espressif.github.io/arduino-esp32/package_esp32_index.json
FQBN=esp32:esp32:esp32cam
BIN="$PWD/.tools"

if grep -q 'MOT_DE_PASSE\|NOM_DU_WIFI' secrets.h; then
  echo "ERREUR : remplis d'abord secrets.h avec le nom et le mot de passe du Wi-Fi." >&2
  exit 1
fi

# 1. arduino-cli (installé localement dans .tools si absent)
if command -v arduino-cli >/dev/null; then
  CLI=arduino-cli
else
  mkdir -p "$BIN"
  [ -x "$BIN/arduino-cli" ] || curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="$BIN" sh
  CLI="$BIN/arduino-cli"
fi

# 2. Support ESP32
echo "==> Installation du support ESP32 (long la première fois)..."
"$CLI" core update-index --additional-urls "$URL"
"$CLI" core install esp32:esp32 --additional-urls "$URL"

# 3. Port série
PORT="${1:-}"
if [ -z "$PORT" ]; then
  PORT=$(ls /dev/cu.usbserial* /dev/cu.wchusbserial* /dev/cu.SLAB* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1 || true)
fi
if [ -z "$PORT" ]; then
  echo "ERREUR : ESP32-CAM introuvable. Vérifie le câble micro-USB (il doit transmettre les données)." >&2
  echo "Ports disponibles :" >&2; "$CLI" board list >&2
  exit 1
fi
echo "==> Port : $PORT"

# 4. Compilation + flash
"$CLI" compile --fqbn "$FQBN" .
echo "==> Flash... (si ça bloque sur 'Connecting...', maintiens le bouton IO0 puis appuie sur RST)"
"$CLI" upload --fqbn "$FQBN" -p "$PORT" .

# 5. Affiche les logs de démarrage (IP, connexion Wi-Fi)
echo "==> Démarrage de la caméra (Ctrl+C pour quitter) :"
"$CLI" monitor -p "$PORT" -c baudrate=115200
