# Sentinel-X : mode d'emploi

Le **PC serveur** fait tourner toute la supervision : il reçoit les capteurs du boîtier et la vidéo de la caméra, calcule le niveau de menace, affiche le **dashboard** et envoie les **notifications** sur les téléphones. Tout se pilote avec une seule commande : `./sentinel`.

## 1. Ouvrir un terminal au bon endroit

Ouvrez un terminal (Ctrl + Alt + T), puis tapez :

```bash
cd /opt/sentinel-x
```

Toutes les commandes ci-dessous se tapent depuis ce dossier. Pour revoir la liste : `./sentinel aide`.

## 2. Les commandes du quotidien

| Je veux… | Je tape |
| --- | --- |
| Lancer la supervision | `./sentinel demarrer` |
| Savoir si tout va bien | `./sentinel etat` |
| Voir ce qui se passe en direct | `./sentinel journaux` (Ctrl + C pour quitter) |
| Voir un seul service | `./sentinel journaux vision` (ou `backend`, `anomaly`, `mosquitto`…) |
| Retrouver l'adresse et les mots de passe | `./sentinel identifiants` |
| Vérifier que la chaîne d'alerte marche | `./sentinel test` |
| Tout arrêter (rien n'est effacé) | `./sentinel arreter` |
| Tout relancer | `./sentinel redemarrer` |
| Sauvegarder la base | `./sentinel sauvegarde` |
| Récupérer la dernière version du code | `./sentinel mise-a-jour` |

**Après un redémarrage du PC, il n'y a rien à faire** : Docker démarre tout seul et relance la supervision. Vérifiez simplement avec `./sentinel etat`.

### Lire `./sentinel etat`

- Chaque service doit être « Up » ; `backend` et `db` affichent aussi « (healthy) ».
- ✔ vert : tout va bien. ! jaune : à surveiller. ✘ rouge : problème (voir la section 7).
- « Boîtier jamais connecté » est normal tant que la carte n'est pas branchée (`./sentinel carte`).
- « Caméra injoignable » est normal tant que l'ESP32-CAM n'est pas allumée sur le Wi-Fi du projet.

## 3. Ouvrir le dashboard

1. Dans le navigateur du PC serveur : **https://localhost** (ou **https://127.0.0.1**). Depuis un autre poste du réseau du projet : **https://192.168.50.10**.
2. Le navigateur affiche un avertissement de sécurité : c'est normal, le certificat vient de **notre propre autorité** (la PKI du projet), pas d'une autorité publique. Deux solutions :
   - rapide : « Avancé » puis « Accepter le risque et poursuivre » ;
   - propre (à faire sur chaque poste et pour la démo) : importer `/opt/sentinel-x/pki/ca.crt` dans le navigateur. Firefox : Paramètres > Vie privée et sécurité > Certificats > Afficher les certificats > Autorités > Importer, cocher « identifier des sites web ».
3. Connexion : compte **admin**, mot de passe donné par `./sentinel identifiants`.
4. Créez un compte par personne (Administration > Utilisateurs) plutôt que de partager le compte admin : chaque action est enregistrée au nom de son auteur dans le journal d'audit.

### Ce qu'on trouve dans le dashboard

| Page | Contenu |
| --- | --- |
| Vue d'ensemble | Niveau de menace (Calme, Alerte, Critique), boîtier en ligne ou non, armé ou non, dernières mesures, projection de température à 15 min |
| Caméra | Flux vidéo annoté (cadres rouges sur les personnes). Il ne s'ouvre que pendant une détection et 5 min après (protection de la vie privée) ; un administrateur peut forcer l'accès en donnant un motif |
| Capteurs | Courbes de température, d'humidité et de distance |
| Alertes | Liste des alertes avec la capture et les raisons du score ; bouton « Acquitter » (avec commentaire) |
| Journaux | Tout ce qui se passe (opérateurs et admins) |
| Administration | Onglets Système (état des services, redémarrages), Utilisateurs, Équipe (reconnaissance faciale), Badges, Détection (points, seuils, horaires) |

### Comment le niveau de menace est calculé

Chaque détection ajoute des points pendant 60 secondes, puis le total donne le niveau :

| Détection | Points |
| --- | --- |
| Mouvement PIR | 20 |
| Objet à moins de 50 cm | 20 |
| Anomalie de température ou d'humidité | 30 |
| Personne vue par la caméra, ou visage inconnu | 40 |
| Choc ou déplacement du boîtier | 40 |
| Boîtier muet (plus de nouvelles depuis 45 s) | 50 |
| Caméra masquée | 50 |
| Capot ouvert | 60 |
| Badge refusé | 30 |

Système **armé ou hors des horaires d'occupation** : × 1,5. Badge valide ou visage d'un membre de l'équipe dans les 2 dernières minutes : × 0,3.
**Moins de 30 : Calme** (juste noté dans les journaux). **30 à 69 : Alerte** (dashboard et téléphone). **70 et plus : Critique** (dashboard, téléphone, et buzzer du boîtier si le système est armé).
Exemple : quelqu'un entre à 3 h du matin, système armé : PIR + personne = (20 + 40) × 1,5 = 90, donc Critique.

Les points, les seuils et les horaires se règlent dans Administration > Détection.

## 4. Armer, désarmer, acquitter

- **Armer / désarmer** : bouton dans le bandeau en haut de chaque page (opérateur ou admin), ou passage d'un badge enregistré sur le boîtier (un passage arme, le suivant désarme).
- **Acquitter une alerte** : page Alertes > « Acquitter », avec un commentaire (« fausse alerte, agent d'entretien », par exemple). Tout est tracé dans le journal d'audit.

## 5. Recevoir les alertes sur un téléphone

Il faut que le téléphone soit sur le Wi-Fi du projet.

1. Une seule fois, sur le routeur : déclarer le nom `ntfy.sentinel.lan` vers `192.168.50.10` (menu DNS ou « nom d'hôte local » du routeur).
2. Sur le téléphone : installer le certificat `pki/ca.crt` (envoyez-le-vous, puis Réglages > Sécurité > Installer un certificat).
3. Installer l'application **ntfy** (Android ou iPhone). Ajouter un abonnement : serveur `https://ntfy.sentinel.lan`, sujet `sentinel-alertes`, compte `operateur` avec le mot de passe donné par `./sentinel identifiants`.
4. Vérifier : `./sentinel test` la nuit, ou avec le système armé, doit faire sonner le téléphone. La capture de la caméra est jointe quand il y en a une.

## 6. Brancher le boîtier et la caméra (équipe IoT)

### Avec la carte UNO Q sur le partage de connexion (fonctionnement actuel de l'équipe)

La carte UNO Q (« talos ») publie ses capteurs et relaie la caméra sur une petite API web (port 8000). Le serveur va les chercher lui-même :

```bash
./sentinel carte
```

La commande trouve la carte sur le partage de connexion (en général `172.20.10.2`) et branche le backend (capteurs : PIR, porte, badge, température) et vision (caméra). À relancer si la carte change d'adresse. Adresse connue : `./sentinel carte 172.20.10.2`. `./sentinel etat` indique si la carte est joignable.

À savoir : cette API n'est ni chiffrée ni protégée par mot de passe (n'importe quel appareil du partage pourrait se faire passer pour la carte), et le service d'anomalies ne reçoit ses mesures que par MQTT. La cible du cahier reste le MQTTS ci-dessous.

### Avec la passerelle MQTTS (cible du cahier des charges)

- **Boîtier** : il se connecte au broker en MQTTS (port 8883) avec **son certificat**. Copiez les 3 fichiers de `pki/box01/` (`ca.crt`, `box01.crt`, `box01.key`) sur le PC de la passerelle (`firmware/gateway/certs/`) ou sur l'UNO Q, avec `MQTT_HOST=192.168.50.10`, `MQTT_PORT=8883`, `MQTT_TLS=true`. Le fichier `box01.key` est secret : ne le mettez jamais dans Git.
- **Caméra** : l'ESP32-CAM doit être à l'adresse `192.168.50.21`, flux sur `http://192.168.50.21:81/stream`. Autre adresse ou mot de passe : modifiez `CAMERA_URL`, `CAMERA_USER` et `CAMERA_PASSWORD` dans le fichier `.env`, puis `./sentinel redemarrer`.
- Ça marche quand `./sentinel etat` affiche « Boîtier en ligne », et qu'un passage devant le PIR apparaît sur le dashboard (jalon 3 du cahier).
- **Détection d'anomalies** : elle apprend le fonctionnement normal de la salle. Il lui faut au moins 2 h de mesures, idéalement plusieurs jours : laissez le boîtier mesurer le plus tôt possible.

## 7. Problèmes fréquents

| Problème | Que faire |
| --- | --- |
| Le dashboard ne s'ouvre pas | `./sentinel etat`, puis `./sentinel redemarrer` ; si ça persiste, `./sentinel journaux backend` |
| « Trop de tentatives » à la connexion | Attendre 15 minutes (protection contre les attaques par force brute) |
| Mot de passe admin perdu | `docker compose exec backend python -m app.cli reset-password admin` |
| Boîtier « muet » | Le boîtier n'envoie plus rien depuis 45 s : alimentation, Wi-Fi, ou passerelle arrêtée |
| Caméra « hors ligne » | ESP32-CAM éteinte ou hors du Wi-Fi ; elle a besoin de sa propre alimentation 5 V |
| Pas de notification | Le téléphone est-il sur le Wi-Fi du projet ? Le nom `ntfy.sentinel.lan` est-il déclaré ? `./sentinel journaux backend` pour voir les erreurs d'envoi |
| Un service redémarre en boucle | `./sentinel journaux <service>` et lisez les dernières lignes rouges |

## 8. Réglages du PC à faire une fois (droits administrateur)

Ces commandes demandent votre mot de passe. Elles empêchent la mise en veille (le PC doit tourner en permanence) et ferment les ports inutiles.

Empêcher toute mise en veille ou hibernation :

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Ne pas se mettre en veille quand on ferme l'écran du portable (pris en compte au prochain redémarrage) :

```bash
sudo mkdir -p /etc/systemd/logind.conf.d
```

```bash
printf '[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\nHandleLidSwitchDocked=ignore\nHandleSuspendKey=ignore\nHandleHibernateKey=ignore\nIdleAction=ignore\n' | sudo tee /etc/systemd/logind.conf.d/sentinel-x.conf
```

Ne pas demander de veille dans la session graphique (secteur, puis batterie) :

```bash
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'
```

```bash
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 'nothing'
```

Pare-feu, une fois le PC sur le réseau du projet (192.168.50.0/24) : voir la section « Reste à faire côté hôte » de [DEPLOIEMENT.md](DEPLOIEMENT.md).

## 9. Pour aller plus loin

- Architecture, certificats, services, sécurité : [DEPLOIEMENT.md](DEPLOIEMENT.md).
- Rapport d'audit (brouillon) : [docs/rapport-audit.md](docs/rapport-audit.md).
- Fichiers secrets, à ne jamais partager ni mettre dans Git : `.env`, `pki/`, `.admin-password`, `.ntfy-operateur-password`, `backups/`.
