# Arduino UNO Q : API capteurs

L'UNO Q a deux processeurs :

- **Linux (Debian)** : fait tourner l'API FastAPI sur le port 8000, en Wi-Fi.
- **Microcontrôleur STM32** : lit les capteurs (`sketch/sensors/sensors.ino`) et
  les expose au Linux via le **Bridge** (RPC msgpack sur `/run/arduino-router.sock`).

La caméra est une ESP32-CAM séparée (voir [`../esp32cam`](../esp32cam)), relayée par l'API.

## Contenu

| Fichier | Rôle |
|---|---|
| `setup.sh` | Installe tout sur une carte neuve depuis un Mac/PC (une commande) |
| `api/main.py` | API FastAPI : capteurs, caméra, WebSocket |
| `api/bridge.py` | Client du Bridge (appels vers le microcontrôleur) |
| `api/realtime.py` | WebSocket temps réel du détecteur de mouvement |
| `api/camera.py` | Relais du flux de l'ESP32-CAM (multi-spectateurs) |
| `api/live.html` | Page de test du détecteur de mouvement |
| `sketch/sensors/sensors.ino` | Sketch du microcontrôleur (DHT11, PIR, servo, écran OLED) |
| `sensor-api.service` | Service systemd utilisateur (démarrage au boot) |
| `cam-wifi.sh` | Bascule le Wi-Fi de la carte vers celui de la caméra (mode point d'accès) |

## Installer sur une carte neuve

### 1. Première configuration (Arduino App Lab)

Branche la carte en USB-C, ouvre **Arduino App Lab** et suis l'assistant :
nom de la carte (ex. `talos`), Wi-Fi, mot de passe Linux, mises à jour.
Mets la carte sur le **même Wi-Fi** que la caméra et les appareils qui
consulteront l'API (ex. partage de connexion du téléphone, avec
*Maximiser la compatibilité* activé pour la caméra).

> Deux cartes sur le même réseau doivent avoir **des noms différents**
> (`talos`, `talos2`…), sinon `<nom>.local` est ambigu.

### 2. Autoriser la clé SSH

```bash
ssh-copy-id arduino@talos.local
```

(demande le mot de passe Linux défini à l'étape 1)

### 3. Lancer l'installation

```bash
API_TOKEN=<jeton du serveur> ./setup.sh talos.local
```

Le jeton est celui du serveur Sentinel-X (`./sentinel identifiants`, ligne « Jeton de la carte UNO Q »). Sans lui,
l'API reste ouverte à tout le réseau (voir « Sécurité » ci-dessous).

Le script copie les fichiers, crée l'environnement Python avec `uv` (sans sudo),
compile et flashe le microcontrôleur (en vérifiant qu'il répond via le Bridge),
active le service et teste l'API. Durée : 3 à 5 minutes.

## Sécurité (api/security.py)

Sans protection, n'importe quel appareil du Wi-Fi (ou une page web piégée ouverte par un opérateur, à cause
du CORS « * ») peut simuler un badge et **désarmer le système**, faire passer la porte pour fermée, regarder
la caméra et piloter le servo ou l'écran. `security.py` ajoute :

- un **jeton obligatoire** sur toutes les routes sauf `/health`, WebSocket `/ws/pir` compris : en-tête
  `Authorization: Bearer <jeton>` (backend, vision) ou authentification Basic avec le jeton comme mot de passe
  (navigateur sur `/live`, lecteurs du flux `/camera/stream`) ;
- les **routes `/simulate` fermées** (403), sauf `ALLOW_SIMULATION=1` pour un essai sans matériel ;
- plus de CORS « * » : seules les origines de `ALLOWED_ORIGINS` peuvent lire l'API depuis un navigateur.

Le backend ignore de son côté tout badge ou état de porte marqué `"source": "simulation"`.

### Activer la protection sur une carte déjà installée

La version qui tourne sur la carte est plus récente que `api/main.py` (routes `/sensors/rfid`, `/sensors/lid`,
`/system/armed`, `/display/badge`) : **ajouter cette version au dépôt**, puis, dans son `main.py`, remplacer la
ligne `app.add_middleware(CORSMiddleware, allow_origins=["*"], …)` par :

```python
from security import install
install(app)
```

Sur la carte (`ssh arduino@talos.local`) :

```bash
cd ~/sensor-api   # après y avoir copié api/security.py et le main.py modifié
printf 'API_TOKEN=<jeton du serveur>\nALLOW_SIMULATION=0\nESP32CAM_PASSWORD=<CAM_PASSWORD de la caméra>\n' > .env
chmod 600 .env
```

Copier aussi `sensor-api.service` (ligne `EnvironmentFile`), puis :

```bash
systemctl --user daemon-reload && systemctl --user restart sensor-api
```

Vérifier : `curl http://talos.local:8000/sensors` répond 401, et `./sentinel etat` sur le serveur indique toujours la
carte joignable avec les données sur le dashboard (le serveur envoie déjà le jeton). Tests : `python -m pytest tests`.

## Branchements

### Capteurs actuels

| Capteur | Broche capteur | Broche UNO Q |
|---|---|---|
| **PIR HC-SR501** (mouvement) | VCC | **5V** |
| | OUT | **D7** |
| | GND | **GND** |
| **DHT11 ou DHT22** (temp./humidité, modèle détecté) | + | **3V3** (jamais 5V : la sortie est tirée vers +) |
| | out | **D2** |
| | − | **GND** |
| **Servo SG90** (rotation caméra) | orange (signal) | **D9** |
| | rouge | **5V** (un seul servo à vide ; sinon alim séparée, voir plus bas) |
| | marron | **GND** |
| **Écran OLED SSD1306** 0,96" I2C | GND | **GND** |
| | VCC | **3V3** (pas 5V : ses résistances de tirage I2C sont reliées à VCC) |
| | SCL | **SCL** (connecteur du haut, à gauche) |
| | SDA | **SDA** (connecteur du haut, à gauche) |

L'écran affiche une interface de type alarme : en veille « SURVEILLANCE / ARME /
R.A.S. » avec le temps depuis le dernier mouvement, le nombre d'alertes et la
température ; en cas de mouvement, « ALERTE INTRUSION / MOUVEMENT » clignote en
plein écran. Il est détecté à chaud (adresse 0x3C ou 0x3D) :
le sketch fonctionne avec ou sans écran.

L'UNO Q n'a qu'une broche 3V3 : sur la breadboard, utiliser une paire de rails
en **5V** (PIR, servo) et l'autre en **3,3 V** (écran OLED, DHT).

Les broches de l'UNO Q fonctionnent en **3,3 V** : ne jamais y envoyer de 5 V
(la sortie du HC-SR501 est en 3,3 V, elle est compatible).

### Extensions prévues (gyrophare, servos, haut-parleur)

Alimentation séparée : **12 V 2 A** pour le gyrophare, abaissée en **5 V** par
un LM2596 pour les servos et le DFPlayer. Les servos ne doivent **pas** être
alimentés par le 5V de l'UNO Q (risque de redémarrage).

| Élément | Broche élément | Raccordé à |
|---|---|---|
| **Alim 12 V** | + | VIN+ du MOSFET **et** IN+ du LM2596 |
| | − | VIN− du MOSFET, IN− du LM2596, **GND de l'UNO Q** |
| **LM2596** | OUT+ | **5 V** des servos et du DFPlayer (régler à 5,0 V au multimètre **avant** de brancher) |
| | OUT− | GND commun |
| **Module MOSFET D4184** | SIG | **D8** |
| | GND (signal) | GND de l'UNO Q |
| | OUT+ / OUT− | + / − du gyrophare |
| **Servo pan** (gauche/droite) | orange (signal) | **D9** (déjà géré par l'API) |
| | rouge / marron | 5 V LM2596 / GND |
| **Servo tilt** (haut/bas) | orange (signal) | **D10** |
| | rouge / marron | 5 V LM2596 / GND |
| **DFPlayer Mini** | VCC / GND | 5 V LM2596 / GND |
| | RX | **D1** (TX UNO Q), via une résistance de 1 kΩ |
| | TX | **D0** (RX UNO Q) |
| | SPK_1 / SPK_2 | haut-parleur 3 W |

**Toutes les masses (GND) doivent être reliées entre elles** : UNO Q, alim 12 V,
LM2596. Sans masse commune, les signaux de commande ne fonctionnent pas.

## API

| Endpoint | Description |
|---|---|
| `GET /health` | État de l'API |
| `GET /sensors` | Toutes les valeurs |
| `GET /sensors/pir` | `{"motion", "last_motion_s_ago", "detections"}` |
| `GET /sensors/pir/hold` | Lissage du PIR : durée de maintien de l'état « mouvement » (5 s par défaut) |
| `POST /sensors/pir/hold/{secondes}` | Règle ce maintien (0 à 60 s ; 0 = signal brut du capteur) |
| `WS /ws/pir` | Événements temps réel : `state`, `motion_start`, `motion_end`, `heartbeat` |
| `GET /sensors/temperature`, `/humidity` | DHT11 (`null` si pas de lecture valide) |
| `GET /servo` | Position du servo : `{"angle", "target", "moving"}` |
| `POST /servo/{angle}?speed=` | Oriente le servo, ex. `POST /servo/45?speed=300` (vitesse en °/s, 180 par défaut, max 600) |
| `POST /servo` | Idem avec un corps JSON : `{"angle": 0-180, "speed": 1-600}` |
| `GET /camera/stream` | Flux MJPEG de l'ESP32-CAM, multi-spectateurs |
| `GET /camera/snapshot` | Une photo JPEG |
| `GET /camera/status` | État de la caméra et du relais |
| `GET /live` | Page de test du détecteur de mouvement |
| `GET /docs` | Documentation interactive |

CORS ouvert (`*`) pour les dashboards servis depuis un autre PC.

## Maintenance

```bash
ssh arduino@talos.local
systemctl --user restart sensor-api          # redémarrer l'API
journalctl --user -u sensor-api -f           # logs de l'API
cd ~/sketches/sensors && arduino-cli compile --fqbn arduino:zephyr:unoq --upload .   # reflasher le MCU
```

Sans Wi-Fi, la carte reste accessible par le câble USB avec ADB (`adb shell`).
