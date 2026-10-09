#!/bin/bash
# L'enceinte Bluetooth se connecte mais n'apparaît pas comme sortie son ? L'écran de connexion (lightdm)
# fait tourner son propre PipeWire, qui prend le Bluetooth audio à la place de l'utilisateur arduino.
# On coupe le Bluetooth de celui de lightdm, et on l'active pour arduino même sans écran.
# Sur la carte :  sudo bash ~/fix-bluetooth-audio.sh
set -euo pipefail
LD=/var/lib/lightdm/.config/wireplumber/wireplumber.conf.d
install -d -o lightdm -g lightdm "$LD"
printf 'wireplumber.profiles = {\n  main = {\n    monitor.bluez = disabled\n  }\n}\n' > "$LD/90-sans-bluetooth.conf"
chown lightdm:lightdm "$LD/90-sans-bluetooth.conf"

U=/home/arduino/.config/wireplumber/wireplumber.conf.d
install -d -o arduino -g arduino "$U"
printf 'wireplumber.profiles = {\n  main = {\n    monitor.bluez.seat-monitoring = disabled\n  }\n}\n' > "$U/51-bluez-sans-ecran.conf"
chown arduino:arduino "$U/51-bluez-sans-ecran.conf"

# Le PipeWire de lightdm est un service utilisateur (user@<uid>) : redémarrer lightdm ne le relance pas.
sudo -u lightdm XDG_RUNTIME_DIR=/run/user/$(id -u lightdm) systemctl --user restart wireplumber
sleep 3
sudo -u arduino XDG_RUNTIME_DIR=/run/user/$(id -u arduino) systemctl --user restart wireplumber
echo "OK : éteignez puis rallumez l'enceinte, elle se reconnecte en moins de 30 s."
