// Copie ce fichier en secrets.h (fait automatiquement par flash.sh / flash.ps1)
// puis remplis-le. secrets.h n'est jamais commité.

// Mode point d'accès : la caméra crée son propre Wi-Fi (IP fixe 192.168.4.1).
// Commente cette ligne pour que la caméra rejoigne un Wi-Fi existant à la place.
#define WIFI_AP_MODE

// Nom et mot de passe du Wi-Fi (créé par la caméra, ou à rejoindre).
// Le mot de passe doit faire au moins 8 caractères (WPA2), sinon la compilation échoue.
// En mode client, l'ESP32 ne supporte que le 2,4 GHz.
// Authentification HTTP Basic de la caméra (photo, flux, état). Mot de passe de 12 caractères minimum :
// openssl rand -base64 12. Côté UNO Q : ESP32CAM_USER / ESP32CAM_PASSWORD dans ~/sensor-api/.env.
#define CAM_USER      "sentinel"
#define CAM_PASSWORD  "a-remplacer-12car"

#define WIFI_SSID     "NOM_DU_WIFI"
#define WIFI_PASSWORD "MOT_DE_PASSE"
