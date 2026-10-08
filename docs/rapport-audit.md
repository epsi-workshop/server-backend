# Sentinel-X : rapport d'audit (brouillon)

Plan d'audit : cahier des charges, section 8.5. Tous les tests sont faits sur notre propre matériel et notre propre réseau.
Ce brouillon couvre les tests réalisés **depuis le PC serveur** le 8 octobre 2026 (pile Docker complète, boîtier simulé avec son vrai certificat `box01`). Les tests qui demandent le réseau dédié 192.168.50.0/24 ou le matériel restent à faire (dernière section), avec captures d'écran à joindre.

## Résultats

| # | Test (cahier 8.5) | Commande | Attendu | Résultat |
| --- | --- | --- | --- | --- |
| 1 | Ports ouverts sur le serveur | `ss -ltn` (puis `nmap -sV -p- 192.168.50.10` depuis le réseau) | Seuls 443 et 8883 | ✔ 443 et 8883 uniquement ; base, backend, vision, ntfy, superviseur sans port publié |
| 2 | Connexion MQTT sans certificat | `mosquitto_sub -h <serveur> -p 8883 --cafile ca.crt -t '#'` | Refusée | ✔ « The connection was lost » |
| 3 | Publication hors ACL | `mosquitto_pub` avec le certificat `box01` sur `sentinel/box01/cmd` | Message ignoré | ✔ Un abonné `backend` reçoit l'événement autorisé de box01, jamais le message interdit |
| 4 | Rejeu d'un message capturé | Même message (même `seq`) publié deux fois | Rejeté | ✔ « numéro de séquence déjà reçu, rejeu possible » (journal backend), idem dans le service anomaly |
| 5 | Force brute du dashboard | 7 tentatives de connexion avec un mauvais mot de passe | Blocage | ✔ 401 ×5 puis 429 ; chaque échec et blocage au journal d'audit |
| 6 | HTTPS | `curl --cacert ca.crt https://<serveur>/` ; `curl --tls-max 1.1` | TLS 1.2+ uniquement, en-têtes | ✔ TLS 1.1 refusé ; HSTS, CSP stricte, X-Frame-Options DENY ; `/api/docs` désactivé (404) |
| 7 | CSRF | POST sans en-tête `Origin` | Refusé | ✔ 403 « Origine de la requête refusée » |
| 8 | Superviseur (accès Docker) | Requêtes depuis l'hôte, depuis vision, sans jeton, vers un service hors liste | Refusées | ✔ Injoignable depuis l'hôte et depuis vision (réseau interne) ; 401 sans jeton ; 403 pour `db` ; pas d'accès Internet |
| 9 | Notifications | Compte anonyme, compte `operateur` qui publie | Refusés | ✔ 403 / 403 ; l'opérateur ne fait que lire `sentinel-alertes` |
| 10 | Caméra masquée | Flux simulé : image uniforme pendant 20 s | Alerte en quelques secondes | ✔ « Sabotage du boîtier » (Critique la nuit) 2 s après le masquage, notification envoyée |
| 11 | Intrusion visuelle | Flux simulé : personne dans le champ | Critique ≤ 5 s avec capture | ✔ Personne confirmée 2,3 s après le mouvement ; alerte avec capture ; notification avec la capture jointe |
| 12 | Images Docker | Trivy `--severity HIGH,CRITICAL --ignore-unfixed` | Aucune faille corrigible | ✔ après correction (voir plus bas), sauf TimescaleDB (risque accepté) |
| 13 | Secrets dans Git | gitleaks sur tout l'historique | Aucun | ✔ « no leaks found » ; `esp32cam/secrets.h` commité ne contient que les valeurs d'exemple (vérifié) ; `.env`, `pki/`, mots de passe ignorés par Git |
| 14 | API HTTP de la carte UNO Q (`openapi.json` de la carte en service) | Lecture de la documentation de l'API, sans appeler les routes d'écriture | Authentification | ✘ Aucune authentification ; `POST /sensors/rfid/simulate/{uid}` et `/sensors/lid/simulate/{state}` ouverts ; CORS « * ». Un badge simulé avec l'UID d'un badge enregistré désarme le système. Corrigé côté serveur (simulation ignorée), correctif carte à installer (voir plus bas) |
| 15 | Flux de l'ESP32-CAM | Lecture du firmware | Authentification (cahier 7.6) | ✘ `/capture`, `:81/stream`, `/status` sans authentification, CORS « * ». Correctif firmware écrit et compilé (à flasher) |

## Corrections apportées pendant l'audit

| Constat | Correction |
| --- | --- |
| Images Python sur `python:3.13.1-slim-bookworm` (déc. 2024) : 7 critiques, 37 graves (openssl, gnutls, perl…) | `python:3.13.16-slim-bookworm` ; `pip` retiré des images finales (ses dépendances embarquées étaient signalées) |
| `nginx:stable-alpine` (étiquette mouvante) : 2 graves | `nginx:1.30.5-alpine` épinglé + `apk upgrade` |
| ntfy v2.28.0 : 2 graves (libssl3) | v2.29.0 |
| Un simple mouvement devant la caméra valait 40 points (ombre, reflet = fausse alerte, ENF-05) | Détection de personnes YOLOX ; seul une personne confirmée (3 analyses sur 5) compte |
| Captures conservées sans limite (ENF-09, RGPD) | Rétention : sans alerte supprimées après 15 min, d'alerte après `retentionDays` |
| API de la carte : badge et porte « simulables » sans authentification (désarmement à distance) | Backend : valeurs `source: simulation` ignorées et journalisées (`SENSOR_API_ALLOW_SIMULATION=false`) ; jeton `UNOQ_API_TOKEN` envoyé à la carte |
| API de la carte : aucune authentification, CORS « * », WebSocket ouvert | `hardware-embedded/uno-q/api/security.py` : jeton (Bearer ou Basic), routes `/simulate` fermées, CORS limité, middleware ASGI (WebSocket compris) ; 6 tests. **À installer sur la carte** |
| ESP32-CAM sans authentification | Firmware : HTTP Basic en temps constant (`CAM_USER` / `CAM_PASSWORD`), CORS retiré ; compilation refusée avec le mot de passe d'exemple ; relais `camera.py` authentifié. Compilé pour `esp32:esp32:esp32cam` (33 % de la flash). **À flasher** |
| Dépendances de l'API de la carte non épinglées | `requirements.txt` épinglé (mêmes séries que le backend) |
| `esp32cam/secrets.h` suivi par Git (un vrai mot de passe y serait commité) | Retiré du suivi, `secrets.h` ignoré partout |
| Objectif masqué seulement écrit dans le journal de vision | Signal « Caméra masquée » au backend, alerte |

## Risques acceptés ou ouverts

| Risque | Statut |
| --- | --- |
| TimescaleDB 2.30.2-pg16 : 3 critiques, 79 graves dans les outils de l'image (Go, python3) | Accepté : dernière version, base sans port, joignable par le backend seul. À rescanner à chaque nouvelle version |
| Visage reconnu = badge valide (× 0,3), sans détection du vivant : une photo d'un membre atténue une intrusion | **Ouvert, décision d'équipe** |
| API HTTP de l'UNO Q (`SENSOR_API_URL`) sans TLS ni authentification, pilote l'armement | Désactivée par défaut (le boîtier passe par MQTTS) ; à protéger avant usage |
| Badges MIFARE Classic clonables ; un passage désarme | Connu (cahier 8.1) : désarmement journalisé et notifié ; démonstration du clonage à ajouter ici |
| Superviseur : accès au socket Docker = root sur l'hôte | Réduit : liste blanche figée, jeton, réseau interne, non-root, lecture seule, sans capacité |
| API de la carte en HTTP clair sur le partage de connexion | Jeton capturable par un appareil qui connaît le mot de passe Wi-Fi : cible MQTTS (ENF-07) |
| Code de l'API en service sur la carte absent du dépôt (plus récent que `hardware-embedded/uno-q/api/main.py`) | À commiter pour pouvoir l'auditer et y installer `security.py` |
| Scripts d'installation (`setup.sh`, `flash.sh`) : `curl … \| sh` depuis Internet, sans vérification | Faible (poste de développement) : préférer une version publiée avec somme de contrôle |
| `cam-wifi.sh` : mot de passe Wi-Fi en argument de `nmcli` (visible dans la liste des processus de la carte) | Faible (carte mono-utilisateur) |
| Copies en double : `esp32cam/` et `esp32cam.zip` à la racine, plus anciens que `hardware-embedded/esp32cam/` (sans authentification) | À supprimer pour ne pas flasher l'ancienne version |
| `.claude/launch.json` : chemins du poste d'un membre de l'équipe | Sans risque, inutile dans le dépôt |
| Pare-feu de l'hôte et fail2ban non configurés (droits administrateur) | À faire (DEPLOIEMENT.md) |

## Reste à tester (réseau dédié et matériel)

- [ ] `nmap -sV -p- 192.168.50.10` depuis un poste du réseau : seuls 443 et 8883.
- [ ] Wireshark : MQTT 1883 lisible en clair (broker de développement) / MQTTS 8883 illisible ; HTTPS illisible.
- [ ] Hydra sur le dashboard depuis un poste du réseau (blocage après 5 essais).
- [ ] OWASP ZAP sur `https://192.168.50.10` (aucune vulnérabilité haute).
- [ ] Metasploit `auxiliary/scanner/ssh/ssh_login` : échec (SSH par clé uniquement).
- [ ] `aireplay-ng` (désauthentification Wi-Fi du boîtier) : alerte « boîtier muet » en moins de 45 s.
- [ ] Main devant l'objectif de la vraie ESP32-CAM.
- [ ] Clonage d'un badge MIFARE Classic.
