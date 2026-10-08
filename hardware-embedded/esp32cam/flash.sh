#!/usr/bin/env bash
# Flash de l'ESP32-CAM (macOS / Linux).
# Usage : ./flash.sh            (détecte le port automatiquement)
#         ./flash.sh /dev/ttyUSB0
set -euo pipefail
cd "$(dirname "$0")"

URL=https://espressif.github.io/arduino-esp32/package_esp32_index.json
# DIO / 40 MHz : plus tolérant que QIO / 80 MHz sur les puces flash des clones ESP32-CAM
FQBN=esp32:esp32:esp32cam:FlashMode=dio,FlashFreq=40
# 115200 bauds : le 460800 par défaut est instable sur les cartes ESP32-CAM-MB
SPEED=115200
BIN="$PWD/.tools"

if [ ! -f secrets.h ]; then
  cp secrets.example.h secrets.h
  echo "secrets.h créé : renseigne le nom et le mot de passe du Wi-Fi, puis relance ce script." >&2
  exit 1
fi
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

# 4. Compilation + flash (3 tentatives)
"$CLI" compile --fqbn "$FQBN" .
ok=0
for try in 1 2 3; do
  echo "==> Flash, tentative $try/3 (si ça bloque sur 'Connecting...', maintiens IO0 puis appuie sur RST)"
  if "$CLI" upload --fqbn "$FQBN" -p "$PORT" --upload-property "upload.speed=$SPEED" .; then ok=1; break; fi
  if [ "$try" -lt 3 ]; then
    read -rp "Échec. Maintiens IO0, appuie sur RST, relâche IO0, puis Entrée pour réessayer..." _
  fi
done
if [ "$ok" -ne 1 ]; then
  echo "ERREUR : le flash a échoué 3 fois. Essaie un autre câble ou un autre port USB (sans hub)." >&2
  exit 1
fi

# 5. Logs de démarrage
# DTR/RTS désactivés : sur l'ESP32-CAM-MB ils maintiendraient la carte en reset
echo "==> Flash réussi. Appuie sur RST pour voir le démarrage (Ctrl+C pour quitter) :"
"$CLI" monitor -p "$PORT" -c baudrate=115200,dtr=off,rts=off
