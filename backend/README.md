# Sentinel-X : backend

API REST + WebSocket du dashboard, authentification, audit. FastAPI, SQLAlchemy async, TimescaleDB. Python 3.12 ou plus.

## Démarrage en local

```bash
cd backend
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d          # TimescaleDB sur 127.0.0.1:5432

python -m venv .venv
.venv\Scripts\activate                                  # Windows (Linux/macOS : source .venv/bin/activate)
pip install -e ".[dev]"

python -m app.cli create-admin admin                    # premier compte, mot de passe de 12 caractères minimum
uvicorn app.main:app --reload --port 8000
```

Dans `frontend/.env` :

```
VITE_API_MODE=live
VITE_BACKEND_URL=http://localhost:8000
```

Puis `npm run dev` dans `frontend/` et connexion sur http://localhost:5173 avec le compte créé.

Documentation interactive de l'API (si `EXPOSE_DOCS=true`) : http://localhost:8000/api/docs. Les routes POST/PUT/PATCH/DELETE y sont refusées (403), car la page n'envoie pas d'en-tête `Origin` autorisé : passer par le dashboard.

Tests : `pytest`.

## Ce qui est fait

| Domaine | État |
| --- | --- |
| Authentification | Session côté serveur (jeton haché en base), cookie `sx_session` HttpOnly + Secure + SameSite=Strict, durée `SESSION_TTL_HOURS` |
| Mots de passe | Argon2id, 12 caractères minimum, rehachage automatique, réponse identique pour un compte inconnu |
| Anti-bruteforce | 5 échecs par (IP, identifiant) ou 20 par IP sur 15 min, puis 429 |
| Anti-CSRF | En-tête `Origin` vérifié sur POST/PUT/PATCH/DELETE et à l'ouverture du WebSocket |
| Rôles | Vérifiés sur chaque route (`Lecteur`, `Operateur`, `Admin` dans `deps.py`) et sur le WebSocket |
| `mustChangePassword` | Toutes les routes répondent 403 sauf `/api/auth/me`, `/password`, `/logout` |
| Audit | Connexions (succès, échecs, blocages), déconnexions, armement, acquittements, redémarrages, accès caméra forcé, comptes, badges, paramètres |
| `/ws/live` | État poussé toutes les 2 s, alertes, journaux (opérateur et plus), fermeture `4401` si session absente ou expirée |
| Comptes, badges, paramètres | CRUD complet, paramètres persistés et appliqués (rétention TimescaleDB) |
| Caméra | `/api/stream` ouvert tant que le PIR détecte un mouvement, puis `cameraUnlockSeconds` (5 min) après le dernier mouvement, ou pendant un accès forcé ; 403 sinon. Relais de `CAMERA_URL` (`http://talos.local:8000/camera/stream`), une seule connexion partagée entre les spectateurs, coupée à la fin de l'accès. Nom en `.local` résolu une fois en IPv4 et gardé 5 min (`netaddr.py`). `camera.online` sondé toutes les 10 s |
| MQTT | Connexion permanente paho-mqtt (thread dédié, fonctionne sous Windows avec `--reload`), TLS optionnel (`MQTT_TLS`) |
| Ingestion | `sentinel/vision/detection` et `sentinel/box01/{telemetry,event,heartbeat,status}` : validation Pydantic, anti-rejeu (`seq` par équipement, horodatage à ± quelques minutes), tables `events` et `measurements`, état des capteurs, signaux de corrélation, boîtier muet après 45 s sans heartbeat ou Last Will. Badges : décision prise par le backend (table `badges`), pas par le boîtier |
| API capteurs de l'UNO Q | `SENSOR_API_URL` (vide = désactivée) : `GET /health` toutes les 15 s (heartbeat), `GET /sensors` toutes les 5 s (température, humidité, PIR), WebSocket `/ws/pir` pour le PIR en temps réel. Réponses traduites en messages du contrat et traitées comme les messages MQTT (`sensor_api.py`) |
| Corrélation | Portage de `computeThreat` / `maybeAlert` (`correlation.py`, testé) : fenêtre 60 s, multiplicateurs, niveaux, escalade sous 90 s, titres par priorité, `buzzer_on` si critique et armé |
| Captures | `GET /api/snapshots/{nom}` (lecteur) : uniquement les captures rattachées à une alerte |
| Rétention des captures | `snapshots.py` : une capture sans alerte est supprimée après 15 min, une capture d'alerte après `retentionDays` (ENF-09) |
| Notifications ntfy (#16) | `notify.py` : alertes Alerte et Critique (création, escalade), capture en pièce jointe, jeton en écriture seule (`scripts/setup-ntfy.sh`) |
| Anomalies | `sentinel/ai/anomaly` (service `anomaly/`) : état du dashboard, signal « anomalie » ; levée si plus de résultat depuis 60 s |
| Personnes, caméra masquée | `sentinel/vision/detection` : `person` (YOLOX) compte dans le score, `motion` seulement sans détection de personnes ; `masked` = signal « Caméra masquée » (50 points) |
| Redémarrages, état des services | `supervisor.py` : superviseur à liste blanche (`supervisor/`), jamais de `docker.sock` dans le backend |

## Ce qui reste (issues)

| Issue | Où |
| --- | --- |
| Migrations Alembic dès que le schéma évolue | `db.py` (`init_db` ne fait que créer les tables manquantes) |

Les commandes vers le boîtier (`arm`, `disarm`, `buzzer_on/off`, `reboot`) sont publiées sur `sentinel/box01/cmd` quand `MQTT_ENABLED=true`. Tant que c'est `false`, l'état est mis à jour et un avertissement est journalisé.

## Écarts au schéma prévu (à valider, issue #1)

- Table `sessions` (jeton haché, utilisateur, expiration, IP) : nécessaire pour la déconnexion côté serveur et la fermeture des sessions d'un compte désactivé.
- Table `logs` (id, ts, level, source, message) : stockage des `LogEntry` de la page Journaux.
- `users.must_change_password` : champ `mustChangePassword` du contrat.
- `audit_log.username` au lieu de `user` (mot réservé SQL).
- Route publique `GET /api/health` pour le healthcheck Docker.
- Route `GET /api/snapshots/{nom}` : cible des `snapshotUrl` des alertes.
- `sentinel/vision/detection` : `type` vaut `motion` (tout mouvement devant la caméra) en plus de `person` ; `data` = `{confidence, snapshot}` (nom de fichier, pas de chemin). Le déverrouillage de la caméra sur tout mouvement, et non plus sur une personne confirmée, est un changement du cahier des charges.
- `sentinel/box01/status` : texte brut `online` / `offline` (et non l'enveloppe JSON), car le Last Will est un message figé enregistré à la connexion : il ne peut pas porter un `seq` ni un `ts` à jour.
- Broker de développement sans TLS (`MQTT_TLS=false`, port 1883 sur 127.0.0.1), en attendant #11 et #12.

## Structure

```
app/
├── main.py         # application, middleware Origin, format d'erreur, démarrage
├── config.py       # variables d'environnement
├── db.py           # tables, hypertables, rétention
├── schemas.py      # modèles Pydantic = frontend/src/types.ts
├── convert.py      # lignes SQL -> modèles du contrat
├── security.py     # Argon2, jetons, limitation des tentatives
├── deps.py         # sessions, rôles (dépendances FastAPI)
├── journal.py      # audit et journal applicatif
├── hub.py          # diffusion WebSocket
├── live.py         # SystemState en mémoire, poussé toutes les 2 s
├── mqtt.py         # connexion MQTT, commandes vers le boîtier
├── ingest.py       # messages MQTT reçus : validation, anti-rejeu, état
├── sensor_api.py   # API capteurs de l'UNO Q (HTTP + WebSocket) -> mêmes traitements que MQTT
├── correlation.py  # score de menace, alertes, escalade
├── camera.py       # relais du flux annoté, sonde de disponibilité
├── cli.py          # create-admin, reset-password
└── routers/        # auth, monitoring (lecture), control (commandes), admin, ws
```
