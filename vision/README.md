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

## Détection de personnes (YOLOX)

YOLOX-S (OpenCV Zoo, licence Apache 2.0, ONNX), sur le CPU avec OpenCV DNN, classe COCO « person » seule.
Modèle : `scripts/download-face-models.sh` (`models/object_detection_yolox_2022nov.onnx`), variable `PERSON_MODEL`
(vide = désactivée).

- **Pré-filtre** : l'analyse ne tourne que pendant un mouvement (ou tant qu'une personne est présente), au plus
  toutes les `PERSON_INTERVAL_S` (0,2 s), dans un thread dédié qui prend toujours l'image la plus récente : le flux
  annoté n'est jamais ralenti.
- **Cadence** : image réduite à `PERSON_INPUT_SIZE` (416 px) : 164 ms par analyse sur le PC serveur, soit 6 par
  seconde (ENF-04). 320 px : 102 ms, moins précis.
- **Confirmation** : personne vue sur `PERSON_CONFIRM` analyses parmi les `PERSON_WINDOW` dernières (3 sur 5).
- **Effets** : cadre rouge sur le flux annoté, capture `person-*.jpg` au plus toutes les `SNAPSHOT_INTERVAL_S`,
  message `person` republié au moins toutes les 2 s tant que la personne est là.
- **Score** : les messages `motion` portent alors `"person_detection": true` ; le backend ne compte plus un simple
  mouvement dans le score (il déverrouille seulement le flux), seule une personne confirmée vaut les 40 points du
  cahier (7.8). Sans modèle, le mouvement compte comme avant.

## Objectif masqué

Image uniforme (écart-type des niveaux de gris sous 6) pendant 2 s : message `masked` (`{"state": 1}`), republié
toutes les 10 s tant que ça dure, puis `{"state": 0}` quand l'image revient. Le backend en fait le signal
« Caméra masquée » (50 points, alerte « Sabotage du boîtier »).

## Reconnaissance faciale

Les membres de l'équipe sont ajoutés dans le dashboard (Administration > Équipe : prénom et photo de face).
Le backend calcule l'empreinte du visage et l'écrit dans `faces/gallery.json`, que ce service relit dès qu'il change.

- **Modèles** : YuNet (détection, 0,2 Mo) et SFace (empreinte, 37 Mo), OpenCV Zoo, sur le CPU, sans LLM ni GPU.
  Téléchargement : `scripts/download-face-models.sh` (dans `models/`, hors dépôt).
- **Analyse** : au plus toutes les `FACE_INTERVAL_S` (0,3 s), environ 40 ms par image 640x480. Un visage
  est reconnu si la similarité cosinus dépasse `FACE_THRESHOLD` (0,363) ; les visages de moins de `FACE_MIN_PX`
  (40 px, au-delà de 3 m environ) sont ignorés.
- **Anti-faux positifs** : un membre doit être vu sur 2 analyses consécutives, un inconnu sur 4, et aucun
  intrus n'est signalé dans les 5 s qui suivent un membre reconnu (un membre de profil paraît souvent inconnu).
  Une même personne est signalée au plus toutes les `FACE_COOLDOWN_S` (30 s).
- **Effets** : capture `face-*.jpg`, message MQTT `face_known` (avec `member_id`) ou `face_unknown`, et écran
  OLED de l'UNO Q (`DISPLAY_API_URL`, route `POST /display/face`) : « BONJOUR LÉA » ou « INTRU DÉTECTÉ ».
- **Limite** : une photo de la personne présentée à la caméra est reconnue (pas de détection du vivant).

Variables : `FACE_MODELS_DIR=../models` (vide = désactivée), `FACES_DIR=../faces` (même valeur côté backend),
`DISPLAY_API_URL=http://talos.local:8000`.

## Message publié

```json
{"device": "vision", "seq": 1791204793521, "ts": "2026-10-05T13:53:13.521Z", "type": "motion",
 "data": {"confidence": 0.6, "snapshot": "motion-20261005-155313-521.jpg"}}
```

`seq` est l'heure en millisecondes : il reste croissant après un redémarrage (anti-rejeu du backend). `confidence` est la part des dernières images en mouvement. `snapshot` vaut `null` quand le message ne fait que prolonger la détection.

## Reste à faire

- Redémarrage de l'ESP32-CAM à distance (aujourd'hui : couper puis rétablir son alimentation).
