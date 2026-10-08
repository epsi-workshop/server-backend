#!/usr/bin/env bash
# Comptes ntfy (accès refusé par défaut, inscription fermée), à lancer une fois la pile démarrée :
#   backend   : écriture seule sur le topic des alertes ; son jeton est écrit dans .env (NTFY_TOKEN)
#   operateur : lecture seule, pour l'application ntfy des téléphones ; mot de passe dans .ntfy-operateur-password
# Idempotent : un compte existant est conservé. Le backend est recréé pour prendre le jeton.
set -euo pipefail
cd "$(dirname "$0")/.."
TOPIC="$(sed -n 's/^NTFY_TOPIC=//p' .env)"
TOPIC="${TOPIC:-sentinel-alertes}"
umask 077

has_user() { docker compose exec -T ntfy ntfy user list 2>&1 | grep -q "^user $1 "; }
add_user() {  # nom, mot de passe
  docker compose exec -T -e NTFY_PASSWORD="$2" ntfy ntfy user add "$1" >/dev/null
}

if ! has_user backend; then
  add_user backend "$(openssl rand -hex 24)"
  docker compose exec -T ntfy ntfy access backend "$TOPIC" write-only >/dev/null
  token="$(docker compose exec -T ntfy ntfy token add --label=sentinel-backend backend | grep -o 'tk_[A-Za-z0-9]*')"
  if grep -q '^NTFY_TOKEN=' .env; then
    sed -i "s/^NTFY_TOKEN=.*/NTFY_TOKEN=$token/" .env
  else
    echo "NTFY_TOKEN=$token" >> .env
  fi
  echo "Compte ntfy « backend » créé (écriture seule sur $TOPIC), jeton enregistré dans .env"
fi

if ! has_user operateur; then
  openssl rand -base64 18 | tr -d '\n' > .ntfy-operateur-password
  add_user operateur "$(cat .ntfy-operateur-password)"
  docker compose exec -T ntfy ntfy access operateur "$TOPIC" read-only >/dev/null
  echo "Compte ntfy « operateur » créé (lecture seule sur $TOPIC), mot de passe dans .ntfy-operateur-password"
fi

docker compose up -d backend >/dev/null 2>&1
echo "Abonnement sur le téléphone : serveur https://ntfy.sentinel.lan, topic $TOPIC, compte operateur."
