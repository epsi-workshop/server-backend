#!/usr/bin/env bash
# Bascule le Wi-Fi de l'UNO Q entre le réseau de la caméra et le Wi-Fi habituel.
#   ./cam-wifi.sh setup [SSID]   enregistre le Wi-Fi de la caméra (demande le mot de passe)
#   ./cam-wifi.sh on             se connecte au Wi-Fi de la caméra
#   ./cam-wifi.sh off            revient au Wi-Fi habituel
#   ./cam-wifi.sh status         affiche le réseau actuel et teste la caméra
set -euo pipefail
PROFILE="camera"
HOME_PROFILE="${HOME_WIFI:-iPhone de Victor}"

case "${1:-status}" in
  setup)
    SSID="${2:-zzz}"
    read -rsp "Mot de passe du Wi-Fi \"$SSID\" : " PASS; echo
    if [ ${#PASS} -lt 8 ]; then echo "Le mot de passe doit faire au moins 8 caractères." >&2; exit 1; fi
    nmcli con delete "$PROFILE" >/dev/null 2>&1 || true
    # autoconnect désactivé : on ne bascule que sur demande, pour ne pas perdre l'accès SSH
    nmcli con add type wifi ifname wlan0 con-name "$PROFILE" ssid "$SSID" \
      wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASS" connection.autoconnect no >/dev/null
    echo "Profil \"$PROFILE\" enregistré pour le Wi-Fi \"$SSID\". Lance : ./cam-wifi.sh on"
    ;;
  on)
    echo "Bascule sur le Wi-Fi de la caméra. La connexion SSH actuelle va couper."
    echo "Retour automatique sur \"$HOME_PROFILE\" dans 5 min si la caméra est injoignable."
    # Filet de sécurité : si la caméra ne répond pas, on revient au Wi-Fi habituel
    nohup bash -c "sleep 300; curl -sf -m 3 http://192.168.4.1/status >/dev/null || nmcli con up \"$HOME_PROFILE\"" >/dev/null 2>&1 &
    nmcli con up "$PROFILE"
    ;;
  off)
    nmcli con up "$HOME_PROFILE"
    ;;
  status)
    nmcli -t -f NAME,DEVICE con show --active | grep wlan0 || echo "Wi-Fi non connecté"
    for h in esp32cam.local 192.168.4.1; do
      if curl -sf -m 3 "http://$h/status"; then echo "  <- caméra joignable sur $h"; exit 0; fi
    done
    echo "Caméra injoignable"
    ;;
  *) sed -n '2,6p' "$0"; exit 1 ;;
esac
