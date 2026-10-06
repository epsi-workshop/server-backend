# Sentinel-X : service vision

Seul client de l'ESP32-CAM. Détecte tout mouvement devant la caméra (fixe), enregistre des captures annotées et publie les détections au backend, qui déverrouille alors le flux du dashboard.

```
ESP32-CAM ──MJPEG──► vision ─┬─ flux annoté http://127.0.0.1:8081/stream ──► backend /api/stream
                             ├─ captures snapshots/motion-AAAAMMJJ-HHMMSS-mmm.jpg
                             └─ MQTT sentinel/vision/detection ──► backend (déverrouillage, alerte)
```

## Démarrage en local

```powershell
cd vision
copy .env.example .env      # puis CAMERA_URL = IP ou nom de la caméra
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m vision
```

Le backend doit avoir `CAMERA_URL=http://127.0.0.1:8081/stream`, `SNAPSHOT_DIR=../snapshots` et `MQTT_ENABLED=true` dans `backend/.env`. Le broker est le Mosquitto local (service Windows ou `docker compose -f backend/docker-compose.dev.yml up -d mosquitto`).

Tests : `pytest`.

## Détection

- Soustraction de fond MOG2 sur une image réduite à 320 px de large ; les ombres sont ignorées.
- Une zone compte si elle couvre au moins `MOTION_MIN_AREA` de l'image (0,4 % par défaut).
- Mouvement confirmé sur `MOTION_CONFIRM` images parmi les `MOTION_WINDOW` dernières (3 sur 5) : un parasite isolé ne déclenche rien.
- 30 premières images sans détection, le temps d'apprendre le fond.
- Pendant un mouvement : une capture au plus toutes les `SNAPSHOT_INTERVAL_S` secondes, une publication MQTT au moins toutes les 2 s (le flux reste déverrouillé tant que ça bouge, puis `cameraUnlockSeconds`).
- Objectif masqué (image uniforme) : signalé dans le journal du service.

Trop de déclenchements (reflets, écran dans le champ) : augmenter `MOTION_MIN_AREA` (0.01) ou `MOTION_CONFIRM`.

## Suivi du mouvement (servo)

Avec `SERVO_API_URL` (ex. `http://talos.local:8000`), la caméra montée sur le servo de l'UNO Q
pivote vers le mouvement : en caméra fixe, c'est en général la personne qui se déplace.

1. À chaque mouvement confirmé, on prend la **plus grande zone** en mouvement et son écart au centre.
2. Au-delà de `TRACK_DEADBAND` (15 % de la demi-largeur), l'écart est converti en angle avec le champ
   de vision `TRACK_FOV_DEG` (60°) et le gain `TRACK_GAIN` (0,8 : pas d'oscillation), puis envoyé par
   `POST /servo/{angle}?speed=TRACK_SPEED` (thread dédié : l'analyse n'attend jamais l'API).
3. Pendant la rotation et `TRACK_SETTLE_S` de stabilisation, la détection est **gelée** (l'image entière
   bouge) ; l'état « mouvement » est conservé pour ne pas couper l'alerte. Le fond est ensuite
   **réappris** sur `TRACK_RELEARN_FRAMES` images à la nouvelle position.
4. Au plus une rotation par `TRACK_MIN_INTERVAL_S` ; retour à `TRACK_HOME_ANGLE` (90°) après
   `TRACK_HOME_AFTER_S` sans mouvement, et au démarrage.

Le flux annoté affiche l'angle (« SUIVI 72 deg », « ... » pendant une rotation) et une croix sur la zone suivie.

Réglages : la caméra part du mauvais côté → `TRACK_INVERT=true` ; elle oscille → baisser `TRACK_GAIN`
ou augmenter `TRACK_DEADBAND` ; elle réagit trop tard → augmenter `TRACK_SPEED` (600 au plus).
Servo injoignable : une ligne dans le journal, la détection continue en caméra fixe.

## Message publié

```json
{"device": "vision", "seq": 1791204793521, "ts": "2026-10-05T13:53:13.521Z", "type": "motion",
 "data": {"confidence": 0.6, "snapshot": "motion-20261005-155313-521.jpg"}}
```

`seq` est l'heure en millisecondes : il reste croissant après un redémarrage (anti-rejeu du backend). `confidence` est la part des dernières images en mouvement. `snapshot` vaut `null` quand le message ne fait que prolonger la détection.

## Reste à faire

- TLS et certificat client `vision` (#11, #12) : `MQTT_PORT=8883`, `MQTT_TLS=true`.
- Détection de personne YOLO (cahier des charges, #19), avec le mouvement comme pré-filtre.
- Publier l'état « objectif masqué » au backend (`camera.masked`).
- Purge des anciennes captures (rétention).
