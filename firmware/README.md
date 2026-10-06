# Sentinel-X : boîtier (version de test : Arduino en USB + passerelle)

En attendant l'agent de l'UNO Q (#6), l'Arduino est branché en USB sur un PC et une passerelle Python publie ses messages sur le broker du PC serveur. Les messages sont ceux du contrat MQTT : le backend ne verra aucune différence quand l'UNO Q prendra le relais.

```
HC-SR501 ──D2──► Arduino ◄─USB série─► serial_gateway.py ◄═Wi-Fi MQTTS 8883═► Mosquitto (PC serveur) ◄─► backend
Buzzer   ◄─D8─── pir_serial.ino          (PC « Arduino »)       certificat box01
```

Mesures et événements montent vers le backend ; les commandes (`arm`, `disarm`, `buzzer_on`, `buzzer_off`, `reboot`) descendent de `sentinel/box01/cmd` jusqu'à l'Arduino.

## 1. Arduino

Câblage du HC-SR501 : `VCC → 5V`, `GND → GND`, `OUT → D2`. Buzzer actif : `+ → D8`, `- → GND`. Cavalier du PIR en position « H », temporisation au minimum.

Téléverser [pir_serial/pir_serial.ino](pir_serial/pir_serial.ino) avec l'IDE Arduino, puis vérifier dans le moniteur série (115200 bauds) : une ligne `heartbeat` toutes les 15 s, et après 1 min de stabilisation une ligne `pir` à chaque mouvement. **Fermer le moniteur série ensuite** : la passerelle a besoin du port.

> Si cet Arduino sert aussi à programmer l'ESP32-CAM (fil RESET → GND), il ne peut pas exécuter le sketch en même temps : retirer ce fil, et alimenter la caméra par sa propre alimentation 5 V.

## 2. Passerelle (sur le PC où l'Arduino est branché)

Copier le dossier `gateway/` sur ce PC (avec `gateway.env`, fourni par l'admin du serveur), puis :

```powershell
cd gateway
python -m pip install -r requirements.txt
python serial_gateway.py --list-ports     # repérer le port de l'Arduino (COM3, COM5…)
```

Mettre ce port dans `gateway.env` (`SERIAL_PORT=COM5`).

**TLS (jalon 3)** : copier dans `gateway/certs/` les fichiers fournis par l'équipe PKI : `ca.crt`, `box01.crt`, `box01.key` (jamais commités). Garder `MQTT_TLS=true` et `MQTT_PORT=8883` comme dans `gateway.env.example`. Le certificat du broker doit contenir l'adresse `192.168.50.10` (SAN), sinon la vérification échoue (`certificate verify failed`). En attendant la PKI, utiliser le bloc « port 1884 » du modèle.

Puis :

```powershell
python serial_gateway.py
```

Attendu : `Connecté au broker 192.168.50.10:8883 (TLS)`, `Arduino connecté sur COM5`, puis `pir {'state': 1}` à chaque mouvement. Sur le dashboard : le boîtier passe « En ligne » et la carte Présence (PIR) s'anime.

| Problème | Cause |
| --- | --- |
| `Port COM… indisponible` | Moniteur série de l'IDE encore ouvert, ou mauvais port |
| `Connexion MQTT refusée : Not authorized` | Mot de passe de `gateway.env` différent de celui du broker, ou CN du certificat absent de l'ACL |
| `certificate verify failed` | `ca.crt` n'est pas la CA qui a signé le certificat du broker, ou l'IP du broker n'est pas dans son SAN |
| `Commande refusée : trop ancienne` | Horloges des deux PC décalées de plus de 30 s : activer la synchronisation de l'heure |
| Aucune connexion au broker | PC serveur pas sur le même Wi-Fi, port 1884 non ouvert (configuration du broker) |
| Boîtier « muet » sur le dashboard | Plus de heartbeat depuis 45 s : Arduino débranché ou passerelle arrêtée |

## Messages publiés

| Ligne du sketch | Topic | Exemple de message |
| --- | --- | --- |
| `{"topic":"event","type":"pir","data":{"state":1}}` | `sentinel/box01/event` | `{"device":"box01","seq":1791227400512,"ts":"2026-10-06T07:30:00.512Z","type":"pir","data":{"state":1}}` |
| `{"topic":"heartbeat",...}` | `sentinel/box01/heartbeat` | uptime, firmware |
| (passerelle) | `sentinel/box01/status` | `online` à la connexion, `offline` en Last Will (retenus) |

## Commandes reçues

| Topic | Reçu du backend | Ligne envoyée à l'Arduino | Effet |
| --- | --- | --- | --- |
| `sentinel/box01/cmd` | `{"device":"box01","seq":…,"ts":…,"type":"buzzer_on","data":{}}` | `{"cmd":"buzzer_on"}` | Buzzer (arrêt automatique après 60 s) |
| | `buzzer_off`, `arm`, `disarm` (coupe aussi le buzzer), `reboot` | idem | `armed` est renvoyé dans le heartbeat |

La passerelle refuse une commande destinée à un autre équipement, inconnue, datée de plus de 30 s, ou dont le `seq` n'est pas plus grand que le précédent (rejeu).

Le sketch peut envoyer les autres messages du contrat de la même façon (`telemetry` avec `temperature`, `humidity`, `distance` ; événements `lid_open`, `imu_shock`, `rfid_ok`, `rfid_refused` avec `{"uid": "04:A3:1F:6B"}`).

Tests de la passerelle : `python -m pytest gateway`.
