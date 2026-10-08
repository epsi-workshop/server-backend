# Sentinel-X : déploiement du PC serveur

Tout le serveur tient dans `docker-compose.yml` (cahier des charges, section 6). Ports publiés : **443** (Caddy, dashboard + API + ntfy) et **8883** (Mosquitto, MQTTS). Base, backend, vision, anomaly, frontend et ntfy ne sont joignables que par les réseaux Docker internes.

## Installation (une seule fois)

```bash
scripts/download-face-models.sh     # YuNet, SFace et YOLOX-S (OpenCV Zoo) dans models/, sommes SHA-256 vérifiées
scripts/gen-pki.sh                  # CA + certificats broker, web, box01, backend, vision, anomaly dans pki/
scripts/fix-owners.sh               # clés données aux utilisateurs non-root des conteneurs, ACL à mosquitto
cp .env.example .env && chmod 600 .env
sed -i "s/^POSTGRES_PASSWORD=$/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
docker compose up -d --build
docker compose exec backend python -m app.cli create-admin admin   # mot de passe de 12 caractères minimum
scripts/setup-ntfy.sh               # comptes ntfy : backend (écriture, jeton dans .env), operateur (lecture)
```

Redéploiement : `docker compose up -d --build` (ENF-06). `.env`, `pki/`, `models/`, `.admin-password` et `.ntfy-operateur-password` ne sont jamais commités.

## Services

| Service | Image | Rôle |
| --- | --- | --- |
| caddy | `caddy:2.11.7-alpine` | HTTPS 443 (certificat `pki/web`), `/api` `/ws` → backend, reste → frontend, `ntfy.sentinel.lan` → ntfy |
| mosquitto | `eclipse-mosquitto:2.0.22` | MQTTS 8883, certificat client obligatoire, CN = identifiant, ACL `mosquitto/acl` |
| db | `timescale/timescaledb:2.30.2-pg16` | Réseau interne sans accès extérieur, aucun port |
| backend | build `backend/` | uid 10001, lecture seule, aucune capacité ; écrit la galerie des visages (volume `faces`) |
| vision | build `vision/` | uid 10002, lecture seule ; seul client de l'ESP32-CAM : mouvement, personnes (YOLOX-S), visages |
| anomaly | build `anomaly/` | uid 10003, lecture seule ; Isolation Forest + projection à +15 min, historique dans le volume `anomaly_data` |
| frontend | build `frontend/` | nginx, CSP stricte |
| ntfy | `binwiederhier/ntfy:v2.28.0` | Accès refusé par défaut (`deny-all`), pas d'inscription |

Volumes partagés : `snapshots` (vision écrit, backend lit), `faces` (backend écrit `gallery.json`, vision lit), `models/` en lecture seule pour les deux.

## Service anomaly

- Lit `sentinel/box01/telemetry` et `sentinel/box01/event`, publie `sentinel/ai/anomaly` à chaque mesure (backend : `ingest.py`, `on_ai_anomaly`).
- Pas de modèle avant 2 h de mesures (`min_train_hours`) ; réentraînement toutes les heures sur 30 jours d'historique.
- Variables : température, humidité, variations sur 5 min, déclenchements PIR sur 1 h, puis heure (dès 24 h d'historique) et jour de la semaine (dès 7 jours) pour éviter les fausses alertes.
- Anomalie confirmée sur 3 mesures parmi 5. Projection : régression linéaire sur 30 min, alerte si la température projetée à +15 min dépasse `TEMP_LIMIT` (27 °C).
- Ne voit que la télémétrie MQTT : avec `SENSOR_API_URL` (capteurs relus en HTTP par le backend), il ne reçoit rien.

## Notifications push (ntfy)

- Le backend publie chaque alerte Alerte ou Critique (création et escalade) sur le topic `sentinel-alertes`, capture de la caméra en pièce jointe, lien vers la page Alertes du dashboard (`backend/app/notify.py`).
- Compte `backend` en écriture seule (jeton `NTFY_TOKEN` dans `.env`), compte `operateur` en lecture seule (mot de passe dans `.ntfy-operateur-password`), tout autre accès refusé.
- Téléphone : application ntfy, serveur `https://ntfy.sentinel.lan`, topic `sentinel-alertes`, compte `operateur`. Il faut que le nom `ntfy.sentinel.lan` soit déclaré dans le DNS du routeur (vers 192.168.50.10) et que le téléphone fasse confiance à `pki/ca.crt`.

## Certificats

| Dossier | Propriétaire | Usage |
| --- | --- | --- |
| `pki/ca.key` | vous | Ne quitte jamais ce poste |
| `pki/box01/` | vous | À copier dans `firmware/gateway/certs/` (ou sur l'UNO Q) |
| `pki/broker/`, `pki/backend/`, `pki/vision/`, `pki/anomaly/`, `pki/web/` | uid du conteneur | Lus en lecture seule par chaque conteneur |

Nouveau client MQTT : `scripts/gen-pki.sh <nom>`, l'ajouter à `mosquitto/acl`, puis `scripts/fix-owners.sh` et `docker compose restart mosquitto`. Les postes opérateurs doivent faire confiance à `pki/ca.crt` pour éviter l'alerte de certificat du navigateur.

## API HTTP de l'UNO Q (`SENSOR_API_URL`, `SERVO_API_URL`, `DISPLAY_API_URL`)

Vides par défaut : le boîtier passe par MQTTS (certificat `box01`). Les renseigner (adresse IP, les noms `.local` ne sont pas résolus dans les conteneurs) fait lire capteurs, porte et badge en **HTTP sans TLS ni authentification**, et pousse l'armement par `POST /system/armed/on|off` : n'importe quel poste du réseau peut alors se faire passer pour le boîtier. Contraire à ENF-07 ; à réserver aux essais tant que l'API de l'UNO Q n'est pas protégée.

## Reste à faire côté hôte (droits administrateur)

Pare-feu (cahier 8.4) : 443 et 8883 uniquement depuis le réseau dédié.

```bash
sudo ufw default deny incoming
sudo ufw allow from 192.168.50.0/24 to any port 443 proto tcp
sudo ufw allow from 192.168.50.0/24 to any port 8883 proto tcp
sudo ufw allow from 192.168.50.0/24 to any port 22 proto tcp
sudo ufw enable
```

Attention : Docker publie ses ports avant les règles ufw (chaîne `DOCKER-USER`). Pour une restriction stricte, mettre `BIND_ADDR=192.168.50.10` dans `.env` une fois l'adresse attribuée au PC serveur.
