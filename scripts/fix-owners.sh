#!/usr/bin/env bash
# Donne chaque dossier de pki/ à l'utilisateur non-root du conteneur qui le lit, et installe l'ACL Mosquitto.
# À relancer après chaque modification de mosquitto/acl (puis : docker compose restart mosquitto).
# Passe par un conteneur : pas besoin de sudo, il suffit d'être dans le groupe docker.
#   broker  -> 1883  (mosquitto)      backend -> 10001  (backend/Dockerfile)
#   web     -> 0     (caddy)          vision  -> 10002  (vision/Dockerfile)
#   anomaly -> 10003 (anomaly/Dockerfile)
# box01 et les autres clients restent à l'utilisateur courant : ils sont copiés vers le boîtier.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
docker run --rm -v "$ROOT/pki:/pki" -v "$ROOT/mosquitto:/mq" alpine:3.24.2 sh -euc '
  own() { [ -d "/pki/$1" ] && chown -R "$2:$2" "/pki/$1" && chmod 700 "/pki/$1" && chmod 600 /pki/$1/*.key; }
  own broker 1883
  own web 0
  own backend 10001
  own vision 10002
  own anomaly 10003
  # Mosquitto refusera bientôt une ACL lisible par tous ou qui ne lui appartient pas : copie protégée
  # de mosquitto/acl (versionnée) dans mosquitto/config/acl (ignorée par git).
  install -o 1883 -g 1883 -m 600 /mq/acl /mq/config/acl
'
echo "Propriétaires appliqués."
