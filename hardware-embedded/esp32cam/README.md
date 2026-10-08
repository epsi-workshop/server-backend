# ESP32-CAM : flux vidéo en direct

Programme pour **ESP32-CAM AI-Thinker** (capteur OV2640) qui diffuse un flux vidéo
**MJPEG en Wi-Fi**. La carte est autonome : une fois flashée, il suffit de
l'alimenter avec un chargeur USB.

## Deux modes Wi-Fi

Le mode se choisit dans `secrets.h` :

| Mode | `secrets.h` | Fonctionnement | Adresse de la caméra |
|---|---|---|---|
| **Point d'accès** (par défaut) | `#define WIFI_AP_MODE` | La caméra **crée son propre Wi-Fi** ; les appareils s'y connectent | `192.168.4.1` (fixe) |
| **Client** | ligne `WIFI_AP_MODE` commentée | La caméra **rejoint un Wi-Fi existant** (box, partage de connexion) | `esp32cam.local` ou IP affichée dans les logs |

Le mode point d'accès ne dépend d'aucun réseau extérieur, mais il supporte peu
d'appareils connectés à la fois (4 au maximum) et n'a pas d'accès Internet.

## Endpoints

Les trois routes demandent l'identifiant et le mot de passe de `secrets.h` (un navigateur les demande).

| URL | Description |
|---|---|
| `http://<adresse>:81/stream` | Flux vidéo en direct (MJPEG) |
| `http://<adresse>/capture` | Une photo (JPEG) |
| `http://<adresse>/status` | Infos JSON : mode, SSID, IP, clients ou signal, uptime, PSRAM |

`<adresse>` vaut `192.168.4.1` en mode point d'accès, `esp32cam.local` en mode client.
Le flux s'ouvre directement dans un navigateur, ou dans une page avec
`<img src="http://192.168.4.1:81/stream">`.

> La caméra ne sert **qu'un seul flux à la fois**. Pour plusieurs spectateurs,
> passe par un relais (voir [Relais via l'UNO Q](#relais-via-luno-q)).

Caractéristiques : 640×480 (320×240 sans PSRAM), qualité JPEG 12, image toujours
la plus récente (faible latence), mise en veille Wi-Fi désactivée pour un flux
fluide, reconnexion Wi-Fi automatique.

## Matériel

- ESP32-CAM AI-Thinker + carte de programmation **ESP32-CAM-MB** (port micro-USB, boutons IO0/RST)
- Câble micro-USB **qui transmet les données** (beaucoup ne font que charger)
- Un réseau Wi-Fi **2,4 GHz** : l'ESP32 ne supporte pas le 5 GHz.
  Sur un partage de connexion iPhone, active *Réglages → Partage de connexion → Maximiser la compatibilité*.

## Flasher la caméra

Les scripts installent tout seuls `arduino-cli` et le support ESP32, puis
compilent, flashent et affichent les logs de démarrage.

### 1. Renseigner le Wi-Fi

```bash
cp secrets.example.h secrets.h
```

Puis édite `secrets.h` :

```c
#define CAM_USER      "sentinel"
#define CAM_PASSWORD  "…"                // 12 caractères minimum : openssl rand -base64 12
#define WIFI_AP_MODE                     // à commenter pour le mode client
#define WIFI_SSID     "nom-du-wifi"
#define WIFI_PASSWORD "mot-de-passe"     // 8 caractères minimum
```

`CAM_USER` / `CAM_PASSWORD` protègent la photo, le flux et l'état (authentification HTTP Basic, cahier 7.6).
La compilation s'arrête si `CAM_PASSWORD` est absent, trop court ou laissé à la valeur d'exemple. Le même mot de
passe va dans `~/sensor-api/.env` de l'UNO Q (`ESP32CAM_PASSWORD=…`), qui relaie le flux.

Le mot de passe doit faire **au moins 8 caractères** (exigence WPA2) : sinon la
compilation s'arrête avec un message explicite. `secrets.h` est ignoré par git :
les identifiants ne sont jamais commités.

### 2. Brancher et lancer le script

Branche la caméra en micro-USB, puis dans ce dossier :

**macOS / Linux**

```bash
./flash.sh
```

Port spécifique : `./flash.sh /dev/ttyUSB0`

**Windows** : clic droit sur `flash.ps1` → *Exécuter avec PowerShell*, ou :

```powershell
powershell -ExecutionPolicy Bypass -File flash.ps1
```

Port spécifique : `-Port COM5`

La première exécution télécharge le support ESP32 (5 à 10 min).

### 3. Vérifier

À la fin du flash, le script affiche les logs de la caméra :

```
Point d'acces "nom-du-wifi" cree, IP: 192.168.4.1
Flux: http://192.168.4.1:81/stream
```

En mode client :

```
Connexion Wi-Fi.....
OK, IP: 172.20.10.4
Flux: http://esp32cam.local:81/stream
```

`Ctrl+C` pour quitter. Débranche ensuite la caméra et alimente-la avec
**n'importe quel chargeur USB d'au moins 1 A** : elle se reconnecte toute seule.

### Flasher depuis Arduino IDE (alternative)

1. *Préférences → URL de gestionnaire de cartes supplémentaires* :
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. *Gestionnaire de cartes* → installer **esp32** (Espressif)
3. Ouvrir `esp32cam.ino`, carte **AI Thinker ESP32-CAM**, *Flash Mode* **DIO**, *Flash Frequency* **40 MHz**, choisir le port, *Téléverser*

## Dépannage

| Problème | Solution |
|---|---|
| `Unable to verify flash chip connection` | Liaison série instable : les scripts flashent déjà à 115200 bauds en mode DIO. Change de câble ou de port USB (sans hub), maintiens IO0 pendant le flash |
| Moniteur série muet après le flash | Appuie sur **RST** (le moniteur désactive DTR/RTS, qui maintiendraient la carte en reset) |
| Bloqué sur `Connecting....` | Maintiens **IO0**, appuie brièvement sur **RST**, relâche IO0 |
| Caméra introuvable (Windows) | Installe le pilote **CH340** ([wch-ic.com](https://www.wch-ic.com/downloads/CH341SER_EXE.html)) ou change de câble |
| Caméra introuvable (macOS) | Vérifie le câble ; sur les anciens macOS, installe le pilote CH340 |
| Redémarre en boucle | Alimentation trop faible : utilise un chargeur ≥ 1 A |
| `static assertion failed: WIFI_PASSWORD...` | Mot de passe trop court : 8 caractères minimum |
| `Connexion Wi-Fi.....` sans fin | Wi-Fi en 5 GHz ou identifiants erronés (redémarre au bout de 30 s) |
| `ERREUR: camera non initialisee` | Nappe du capteur mal enfichée dans son connecteur |
| `esp32cam.local` ne répond pas | Utilise l'IP affichée dans les logs (mDNS bloqué sur certains réseaux) |

## Relais via l'UNO Q

Dans notre montage, l'**Arduino UNO Q** (hôte `talos.local`) expose une API
FastAPI qui relaie ce flux : une seule connexion vers la caméra, redistribuée à
autant de spectateurs que nécessaire.

| URL | Description |
|---|---|
| `http://talos.local:8000/camera/stream` | Flux en direct, multi-spectateurs |
| `http://talos.local:8000/camera/snapshot` | Une photo |
| `http://talos.local:8000/camera/status` | État de la caméra et du relais |

Le relais cherche la caméra sur `esp32cam.local`, puis sur `192.168.4.1`. Pour
d'autres adresses, définis la variable d'environnement `ESP32CAM_HOST`
(liste séparée par des virgules).

En mode point d'accès, l'UNO Q doit rejoindre le Wi-Fi de la caméra. Le script
`~/cam-wifi.sh` sur la carte gère la bascule :

```bash
./cam-wifi.sh setup zzz   # enregistre le Wi-Fi de la caméra (demande le mot de passe)
./cam-wifi.sh on          # bascule sur le Wi-Fi de la caméra
./cam-wifi.sh off         # revient au Wi-Fi habituel
./cam-wifi.sh status      # réseau actuel + test de la caméra
```

L'UNO Q n'a qu'une seule interface Wi-Fi : sur le réseau de la caméra, elle
quitte le Wi-Fi habituel. Les spectateurs doivent alors eux aussi rejoindre le
Wi-Fi de la caméra pour accéder à `http://<ip-uno-q>:8000/camera/stream`.
