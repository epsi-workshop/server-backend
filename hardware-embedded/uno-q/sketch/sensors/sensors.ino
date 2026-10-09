// Capteurs UNO Q (MCU STM32) -> Bridge -> API Python (Linux)
//   DHT11 ou DHT22 (temp./humidité) : données sur D2, + sur 3V3, - sur GND (modèle détecté auto)
//   PIR HC-SR501 (mouvement)       : OUT sur D7, VCC sur 5V, GND sur GND
//   Servo SG90 (rotation caméra)   : signal (orange) sur D9, rouge sur 5V, marron sur GND
//   Porte (HW-201 infrarouge)      : OUT sur D4, VCC sur 3V3, GND sur GND
//   Badge RFID (RC522, SPI)        : SDA D10, SCK D13, MOSI D11, MISO D12, RST D6, 3.3V sur 3V3 (jamais 5 V)
//   Verrou (sortie)                : D3, à l'état haut quand le système est armé
//   Haut-parleur (module MOS IRF520): SIG sur D5 ; VIN 5V, haut-parleur sur V+ / V-
//   Écran OLED SSD1306 128x64 I2C  : SDA sur SDA, SCL sur SCL, VCC sur 3V3, GND sur GND
#include <Arduino_RouterBridge.h>
#include <Servo.h>
#include <Wire.h>
#include <U8g2lib.h>
#include <SPI.h>
#define MFRC522_SPICLOCK 1000000u  // 1 MHz au lieu de 4 : plus tolérant aux longs fils Dupont
#include <MFRC522.h>
#include <zephyr/kernel.h>

#define DHT_PIN   2
#define PIR_PIN   7
#define SERVO_PIN 9
#define DOOR_PIN  4  // HW-201 : OUT à 0 V quand il voit la porte (fermée), 3,3 V sinon
#define OLED_CONTRAST 60  // écran : luminosité sur 255, moins de courant et toujours lisible en intérieur
#define MOTOR_PIN 8   // relais 1 (IN1) : tête de la citrouille vers la gauche ; relais actif à l'état bas
#define MOTOR2_PIN A2 // relais 2 (IN2) : tête vers la droite. Pont en H : moteur sur les COM, + piles sur NO, − sur NC
#define SPEAKER_PIN 5  // module MOS : le haut-parleur est alimenté en 5 V, D5 le fait vibrer
#define LOCK_PIN  3  // sortie « verrou » : 3,3 V quand la porte est verrouillée (futur loquet via MOSFET)
#define RFID_SS   10 // RC522 : broche « SDA » = sélection SPI (rien à voir avec le SDA de l'I2C)
#define RFID_RST  6  // RC522 : RST ; SCK = D13, MOSI = D11, MISO = D12, alimentation 3,3 V uniquement

// Armement imposé par le backend (badge ou dashboard) ; armé = porte verrouillée (sortie LOCK_PIN).
volatile int armed = 0;

// --- Son : motifs joués sans bloquer la boucle (tone() change de note au fil des tours)
// 1 = badge accepté (deux bips aigus), 2 = badge refusé (deux bips plus graves), 3 = visage reconnu (carillon),
// 4 = sirène (montante et descendante, jusqu'à la fin de soundUntil), 5 = test (gamme courte)
struct Note { int freq; int ms; };  // freq 0 = silence
static const Note SND_OK[]      = {{2700, 90}, {0, 60}, {3200, 140}};
static const Note SND_REFUSED[] = {{1000, 180}, {0, 70}, {1000, 380}};
static const Note SND_HELLO[]   = {{2093, 130}, {2637, 200}};
static const Note SND_TEST[]    = {{1760, 120}, {2093, 120}, {2637, 120}, {3136, 220}};
const Note *sndNotes = nullptr;
int sndCount = 0, sndIndex = 0, soundPattern = 0;
unsigned long sndNoteEnd = 0, soundUntil = 0;

static void soundStop() {
  noTone(SPEAKER_PIN);
  digitalWrite(SPEAKER_PIN, LOW);  // MOSFET bloqué : aucun courant dans le haut-parleur au repos
  soundPattern = 0;
  sndNotes = nullptr;
}

static void playNote(int freq, int ms) {
  if (freq) tone(SPEAKER_PIN, freq); else noTone(SPEAKER_PIN);
  sndNoteEnd = millis() + ms;
}

int play_sound(int pattern, int seconds) {
  soundStop();
  soundPattern = pattern;
  switch (pattern) {
    case 1: sndNotes = SND_OK; sndCount = 3; break;
    case 2: sndNotes = SND_REFUSED; sndCount = 3; break;
    case 3: sndNotes = SND_HELLO; sndCount = 2; break;
    case 4: soundUntil = millis() + (unsigned long)constrain(seconds, 1, 120) * 1000; return 4;
    case 5: sndNotes = SND_TEST; sndCount = 4; break;
    default: soundPattern = 0; return 0;
  }
  sndIndex = 0;
  playNote(sndNotes[0].freq, sndNotes[0].ms);
  return pattern;
}
int stop_sound()  { soundStop(); return 0; }
int get_sound()   { return soundPattern; }

static void soundUpdate() {
  if (soundPattern == 4) {
    if ((long)(soundUntil - millis()) <= 0) { soundStop(); return; }
    // Sirène : 1500 -> 3200 Hz puis retour (zone où l'oreille est la plus sensible), cycle de 1 s
    static unsigned long lastStep = 0;
    if (millis() - lastStep >= 20) {
      lastStep = millis();
      unsigned long ph = millis() % 1000;
      int f = ph < 500 ? 1500 + ph * 1700 / 500 : 3200 - (ph - 500) * 1700 / 500;
      tone(SPEAKER_PIN, f);
    }
    return;
  }
  if (sndNotes && (long)(millis() - sndNoteEnd) >= 0) {
    if (++sndIndex >= sndCount) soundStop();
    else playNote(sndNotes[sndIndex].freq, sndNotes[sndIndex].ms);
  }
}


// --- DHT11 : lecteur maison (timing via micros()), plus fiable que la librairie Adafruit sur Zephyr
float lastTemp = NAN;
float lastHum  = NAN;
int   lastErr  = -1;   // 0 = OK, >0 = étape où la lecture a échoué
int   dhtModel = 0;    // 11 ou 22 une fois détecté, 0 sinon
unsigned long lastRead = 0;

// --- PIR : le HC-SR501 alterne souvent HIGH/LOW pendant un mouvement continu.
// L'état « mouvement » est donc maintenu pirHoldMs après le dernier signal HIGH.
int pirState = 0;                        // état lissé (celui exposé à l'API)
unsigned long pirLastMs = 0, pirCount = 0;
unsigned long pirAlertStart = 0;         // début de l'alerte en cours
volatile unsigned long pirHoldMs = 5000; // maintien après le dernier signal
bool pirSeen = false;

// --- Servo : déplacement progressif vers la cible, pour ne pas secouer la caméra
Servo servo;
volatile int servoTarget = 90;      // angle demandé (0-180)
volatile int servoSpeed  = 90;      // vitesse en degrés/seconde
int servoAngle = 90;                // angle actuel
unsigned long servoLastStep = 0;

// --- Reconnaissance faciale (service vision, via /display/face) : message temporaire prioritaire
int faceKind = 0;                   // 0 = aucun, 1 = visage reconnu, 2 = visage inconnu
char faceName[17] = "";             // prénom en majuscules (UTF-8)
unsigned long faceUntil = 0;

// --- Écran OLED : détecté à chaud (adresse I2C 0x3C ou 0x3D), le sketch marche sans
U8G2_SSD1306_128X64_NONAME_F_HW_I2C oled(U8G2_R0, U8X8_PIN_NONE);
bool oledOk = false;
unsigned long oledLastDraw = 0, oledLastProbe = 0;

static bool i2cPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

static void oledProbe() {
  uint8_t addr = i2cPresent(0x3C) ? 0x3C : (i2cPresent(0x3D) ? 0x3D : 0);
  if (!addr) { oledOk = false; return; }
  if (!oledOk) {
    oled.setI2CAddress(addr << 1);  // U8g2 attend l'adresse sur 8 bits
    oled.begin();
    oled.setContrast(OLED_CONTRAST);
    oledOk = true;
  }
}

// Le RC522 tire un pic de courant quand un badge entre dans son champ : le 3,3 V chute et l'écran
// redémarre éteint, sans cesser de répondre en I2C (rien ne le signale). On le réinitialise donc juste
// après chaque lecture de badge, puis toutes les 30 s par sécurité ; l'image est redessinée dans les 100 ms.
unsigned long oledReinitAt = 0, oledLastReinit = 0;

// --- Badge à l'écran : 1 = lu (en attente du backend), 2 = accepté, 3 = refusé, 4 = lu pour enregistrement
int badgeKind = 0, badgeArmed = 0;
char badgeUid[24] = "", badgeName[17] = "";
unsigned long badgeUntil = 0;
static void setBadge(int kind, const char *uid, const char *name, int seconds) {
  badgeKind = kind;
  strncpy(badgeUid, uid, sizeof(badgeUid) - 1); badgeUid[sizeof(badgeUid) - 1] = 0;
  strncpy(badgeName, name, sizeof(badgeName) - 1); badgeName[sizeof(badgeName) - 1] = 0;
  badgeUntil = millis() + (unsigned long)seconds * 1000;
}
static void oledReinit() {
  oled.initDisplay();
  oled.setContrast(OLED_CONTRAST);
  oled.setPowerSave(0);
  oledLastReinit = millis();
}

static void formatAgo(char *out, size_t n, unsigned long ms) {
  unsigned long sec = ms / 1000;
  if (sec < 60) snprintf(out, n, "%lus", sec);
  else if (sec < 3600) snprintf(out, n, "%lum%02lus", sec / 60, sec % 60);
  else snprintf(out, n, "%luh%02lum", sec / 3600, (sec / 60) % 60);
}

static void drawCentered(int y, const char *txt) {
  oled.drawStr((128 - oled.getStrWidth(txt)) / 2, y, txt);
}

static void drawCenteredUTF8(int y, const char *txt) {
  oled.drawUTF8((128 - oled.getUTF8Width(txt)) / 2, y, txt);
}

// Reconnaissance faciale : « BONJOUR <prénom> », ou « INTRU DÉTECTÉ » qui clignote
static void oledDrawFace() {
  bool intrus = faceKind == 2;
  if (intrus && (millis() / 300) % 2) {
    for (int k = 0; k < 4; k++) oled.drawFrame(k, k, 128 - 2 * k, 64 - 2 * k);  // cadre épais clignotant
  } else {
    oled.drawFrame(0, 0, 128, 64);
  }
  oled.setFont(u8g2_font_6x10_tf);
  drawCenteredUTF8(13, intrus ? "! VISAGE INCONNU !" : "VISAGE RECONNU");
  oled.setFont(u8g2_font_helvB12_tf);
  if (intrus) {
    drawCenteredUTF8(36, "INTRU");
    drawCenteredUTF8(56, "DÉTECTÉ");
  } else {
    drawCenteredUTF8(36, "BONJOUR");
    if (oled.getUTF8Width(faceName) > 124) oled.setFont(u8g2_font_6x10_tf);  // prénom long
    drawCenteredUTF8(56, faceName);
  }
  oled.setDrawColor(1);
}

// Écran d'alerte : clignote en plein écran (inversion toutes les 300 ms)
static void oledDrawAlert() {
  char line[28], ago[12];
  bool inverted = (millis() / 300) % 2;
  if (inverted) {
    for (int k = 0; k < 4; k++) oled.drawFrame(k, k, 128 - 2 * k, 64 - 2 * k);  // cadre épais clignotant
  } else {
    oled.drawFrame(0, 0, 128, 64);
    oled.drawFrame(2, 2, 124, 60);
  }
  oled.setFont(u8g2_font_6x10_tr);
  drawCentered(14, "! ALERTE INTRUSION !");
  oled.setFont(u8g2_font_helvB14_tr);
  drawCentered(38, "MOUVEMENT");
  oled.setFont(u8g2_font_6x10_tr);
  formatAgo(ago, sizeof(ago), millis() - pirAlertStart);
  snprintf(line, sizeof(line), "Alerte #%lu - %s", pirCount, ago);
  drawCentered(56, line);
  oled.setDrawColor(1);
}

// Écran de veille : système armé, rien à signaler
static void oledDrawIdle() {
  char line[28], ago[12];
  // Bandeau d'en-tête inversé
  oled.drawBox(0, 0, 128, 13);
  oled.setDrawColor(0);
  oled.setFont(u8g2_font_6x10_tr);
  oled.drawStr(3, 10, "SURVEILLANCE");
  const char *mode = armed ? "ARME" : "VEILLE";
  oled.drawStr(116 - oled.getStrWidth(mode), 10, mode);
  if ((millis() / 1000) % 2) oled.drawDisc(122, 6, 2);  // témoin de vie
  oled.setDrawColor(1);

  oled.setFont(u8g2_font_helvB14_tr);
  if (get_lid()) {  // trop long pour la grande police : 128 px de large
    oled.setFont(u8g2_font_helvB10_tr);
    drawCentered(34, "PORTE OUVERTE");
  } else {
    drawCentered(36, "R.A.S.");
  }

  oled.setFont(u8g2_font_6x10_tr);
  if (pirSeen) {
    formatAgo(ago, sizeof(ago), millis() - pirLastMs);
    snprintf(line, sizeof(line), "Dernier mvt : %s", ago);
  } else {
    snprintf(line, sizeof(line), "Aucun mouvement");
  }
  drawCentered(49, line);

  oled.drawHLine(0, 52, 128);
  snprintf(line, sizeof(line), "Alertes:%lu", pirCount);
  oled.drawStr(0, 63, line);
  // Température et humidité (DHT) ; printf sans flottants sur ce core : formatage manuel
  if (isnan(lastTemp)) snprintf(line, sizeof(line), "--.-C --%%");
  else {
    int t10 = (int)lroundf(lastTemp * 10);
    snprintf(line, sizeof(line), "%s%d.%dC %d%%", t10 < 0 ? "-" : "", abs(t10) / 10, abs(t10) % 10,
             (int)lroundf(lastHum));
  }
  oled.drawStr(128 - oled.getStrWidth(line), 63, line);
}

static void oledDrawBadge() {
  bool refused = badgeKind == 3;
  if (refused && (millis() / 300) % 2) {
    for (int k = 0; k < 4; k++) oled.drawFrame(k, k, 128 - 2 * k, 64 - 2 * k);  // cadre épais clignotant
  } else {
    oled.drawFrame(0, 0, 128, 64);
  }
  oled.setFont(u8g2_font_6x10_tf);
  drawCenteredUTF8(13, "BADGE RFID");
  oled.setFont(u8g2_font_helvB12_tf);
  switch (badgeKind) {
    case 1: drawCenteredUTF8(34, "LECTURE..."); break;
    case 2: drawCenteredUTF8(34, badgeName[0] ? badgeName : "BADGE OK"); break;
    case 3: drawCenteredUTF8(34, "REFUSÉ"); break;
    case 4: drawCenteredUTF8(34, badgeName[0] ? "DÉJÀ CONNU" : "NOUVEAU"); break;
  }
  oled.setFont(u8g2_font_6x10_tf);
  if (badgeKind == 2) drawCenteredUTF8(48, badgeArmed ? "SYSTÈME ARMÉ" : "SYSTÈME DÉSARMÉ");
  else if (badgeKind == 4) drawCenteredUTF8(48, badgeName[0] ? badgeName : "à enregistrer");
  drawCenteredUTF8(60, badgeUid);
  oled.setDrawColor(1);
}

static void oledDraw() {
  oled.clearBuffer();
  if (badgeKind && (long)(badgeUntil - millis()) > 0) oledDrawBadge();
  else if (faceKind && (long)(faceUntil - millis()) > 0) oledDrawFace();
  else if (pirState) oledDrawAlert();
  else oledDrawIdle();
  oled.sendBuffer();
}

// Attend que la broche quitte `level`, renvoie la durée en µs ou -1 si timeout
static long waitWhile(int level, unsigned long timeoutUs) {
  unsigned long start = micros();
  while (digitalRead(DHT_PIN) == level) {
    if (micros() - start > timeoutUs) return -1;
  }
  return micros() - start;
}

static int readDHT11(float &t, float &h) {
  uint8_t data[5] = {0};
  pinMode(DHT_PIN, OUTPUT);
  digitalWrite(DHT_PIN, LOW);
  delay(20);
  pinMode(DHT_PIN, INPUT_PULLUP);

  // Ordonnanceur verrouillé pendant la trame (5 ms max) : aucun autre thread (Bridge) ne peut
  // s'intercaler, mais les interruptions restent actives (masquer les IRQ coupe le Bridge).
  int err = 0;
  k_sched_lock();
  if (waitWhile(HIGH, 1000) < 0) err = 1;  // le capteur doit tirer la ligne à LOW
  else if (waitWhile(LOW, 200) < 0) err = 2;
  else if (waitWhile(HIGH, 200) < 0) err = 3;
  else {
    for (int i = 0; i < 40; i++) {
      if (waitWhile(LOW, 200) < 0) { err = 4; break; }
      long high = waitWhile(HIGH, 200);
      if (high < 0) { err = 5; break; }
      data[i / 8] <<= 1;
      if (high > 45) data[i / 8] |= 1;
    }
  }
  k_sched_unlock();
  if (err) return err;
  if (((data[0] + data[1] + data[2] + data[3]) & 0xFF) != data[4]) return 6;
  // DHT22 : valeurs sur 16 bits en dixièmes, donc octet de poids fort de l'humidité <= 3.
  // DHT11 : partie entière puis décimale, humidité >= 20 %.
  if (data[0] <= 3) {
    dhtModel = 22;
    h = ((data[0] << 8) | data[1]) * 0.1f;
    t = (((data[2] & 0x7F) << 8) | data[3]) * 0.1f;
  } else {
    dhtModel = 11;
    h = data[0] + data[1] * 0.1f;
    t = (data[2] & 0x7F) + data[3] * 0.1f;
  }
  if (data[2] & 0x80) t = -t;
  return 0;
}

// --- Méthodes exposées au Linux via le Bridge
float get_temperature() { return lastTemp; }
float get_humidity()    { return lastHum; }
int   get_dht_error()   { return lastErr; }
int   get_dht_model()   { return dhtModel; }
int   get_oled()        { return oledOk ? 1 : 0; }
// Scan I2C : renvoie la première adresse trouvée (0 si aucune), pour diagnostiquer l'écran
int   i2c_scan() {
  for (uint8_t a = 0x08; a < 0x78; a++) if (i2cPresent(a)) return a;
  return 0;
}
int   get_pir()         { return pirState; }
// --- Porte du pot : -1 = capteur réel, 0 / 1 = valeur d'exemple imposée (fermée / ouverte) pour tester
volatile int doorSim = -1;
int doorOpen = 0;
int   get_lid()         { return doorSim >= 0 ? doorSim : doorOpen; }
int   get_lid_source()  { return doorSim >= 0 ? 1 : 0; }  // 0 = capteur, 1 = simulation
int   set_lid_sim(int v) { doorSim = (v == 0 || v == 1) ? v : -1; return get_lid(); }

// --- Badge RFID : le MCU ne fait que lire l'UID ; la décision (badge autorisé, armement) vient du backend.
MFRC522 rfid(RFID_SS, RFID_RST);
volatile unsigned long rfidSeq = 0;  // incrémenté à chaque lecture : le Linux repère les nouveaux passages
String rfidUid = "";
unsigned long rfidLastPoll = 0, rfidLastRead = 0, rfidLastCheck = 0, rfidResets = 0;
// Consommation : l'antenne du RC522 (jusqu'à 100 mA) n'est allumée que pendant la recherche d'un badge,
// environ 15 ms toutes les 200 ms, au lieu d'en permanence : le 3,3 V de la carte ne s'effondre plus.
// Si une chute de tension réinitialise quand même le lecteur, ses registres reviennent aux valeurs d'usine :
// TxASKReg passe de 0x40 (réglé par PCD_Init) à 0x00. On le vérifie toutes les secondes.
static void rfidInit() {
  rfid.PCD_Init();
  rfid.PCD_AntennaOff();
}
static void rfidCheck() {
  if (rfid.PCD_ReadRegister(MFRC522::TxASKReg) != 0x40) {
    rfidInit();
    rfidResets++;
  }
}
int   get_rfid_resets() { return (int)rfidResets; }
// Diagnostic : registre de version du RC522 (0x91 ou 0x92 = OK, 0x00 ou 0xFF = aucun dialogue SPI)
int   get_rfid_version() { return rfid.PCD_ReadRegister(MFRC522::VersionReg); }
int   get_rfid_seq()    { return (int)rfidSeq; }
// ms depuis la dernière détection d'un badge (-1 si jamais) : un badge posé en permanence sur le lecteur bloque les nouveaux passages
int   get_rfid_seen()   { return rfidLastRead ? (int)(millis() - rfidLastRead) : -1; }
String get_rfid_uid()   { return rfidUid; }

// --- Armement (variable déclarée en tête : l'écran l'utilise) : imposé par le backend, armé = porte verrouillée.
int   get_armed()       { return armed; }
int   set_armed(int v)  { armed = v ? 1 : 0; digitalWrite(LOCK_PIN, armed ? HIGH : LOW); return armed; }
int   get_pir_count()   { return (int)pirCount; }
// ms depuis la dernière détection, -1 si jamais
int   get_pir_last()    { return pirSeen ? (int)(millis() - pirLastMs) : -1; }
int   get_pir_hold()    { return (int)pirHoldMs; }
// Durée de maintien de l'état « mouvement » après le dernier signal (0 à 60 s)
int   set_pir_hold(int ms) { pirHoldMs = constrain(ms, 0, 60000); return (int)pirHoldMs; }
int   get_servo()        { return servoAngle; }
int   get_servo_target() { return servoTarget; }
// Fixe la cible du servo ; speed en degrés/s (1-600), 0 = garde la vitesse actuelle
int   set_servo(int angle, int speed) {
  servoTarget = constrain(angle, 0, 180);
  if (speed > 0) servoSpeed = constrain(speed, 1, 600);
  return servoTarget;
}

// Affiche le résultat de la reconnaissance faciale ; kind : 1 = reconnu, 2 = inconnu ; seconds : 1 à 30
int show_face(int kind, String name, int seconds) {
  faceKind = (kind == 1 || kind == 2) ? kind : 0;
  strncpy(faceName, name.c_str(), sizeof(faceName) - 1);
  faceName[sizeof(faceName) - 1] = 0;
  faceUntil = millis() + (unsigned long)constrain(seconds, 1, 30) * 1000;
  if (faceKind == 1 && soundPattern != 4) play_sound(3, 0);
  else if (faceKind == 2) play_sound(4, 10);  // intrus : sirène 10 s
  return faceKind;
}

// Décision du backend pour le badge lu ; kind : 2 = accepté, 3 = refusé, 4 = lu pour enregistrement
int show_badge(int kind, String uid, String name, int isArmed, int seconds) {
  badgeArmed = isArmed;
  setBadge(constrain(kind, 1, 4), uid.c_str(), name.c_str(), constrain(seconds, 1, 30));
  if (soundPattern != 4) {  // la sirène en cours reste prioritaire
    if (badgeKind == 2) play_sound(1, 0);
    else if (badgeKind == 3) play_sound(2, 0);
    else if (badgeKind == 4) play_sound(5, 0);
  }
  return badgeKind;
}

// --- Moteur de la citrouille : pont en H à 2 relais (piles de la citrouille). Un seul relais à la fois :
// relais 1 = gauche, relais 2 = droite, aucun = arrêt (les deux fils du moteur au −, moteur freiné).
#define MOTOR_MAX_MS 30000
unsigned long motorUntil = 0;
int motorDir = 0;  // -1 = gauche, 1 = droite, 0 = arrêt
static void motorSet(int dir) {
  // on coupe d'abord, puis on active : jamais les deux relais en même temps
  digitalWrite(MOTOR_PIN, HIGH);
  digitalWrite(MOTOR2_PIN, HIGH);
  motorDir = dir;
  if (dir < 0) digitalWrite(MOTOR_PIN, LOW);
  else if (dir > 0) digitalWrite(MOTOR2_PIN, LOW);
}
// dir : -1 gauche, 1 droite, 0 arrêt ; ms : durée (1 à 30000), arrêt automatique ensuite
int move_motor(int dir, int ms) {
  if (dir == 0 || ms <= 0) { motorSet(0); return 0; }
  int d = dir < 0 ? -1 : 1;
  if (motorDir != 0 && motorDir != d) { motorSet(0); delay(60); }  // changement de sens : courte pause
  motorUntil = millis() + (unsigned long)constrain(ms, 1, MOTOR_MAX_MS);
  motorSet(d);
  return motorDir;
}
int run_motor(int seconds) { return move_motor(seconds > 0 ? -1 : 0, seconds * 1000); }  // compatibilité
int get_motor() { return motorDir; }

void setup() {
  digitalWrite(MOTOR_PIN, HIGH);  // relais ouverts avant de passer les broches en sortie : pas de « clac » au démarrage
  digitalWrite(MOTOR2_PIN, HIGH);
  pinMode(MOTOR_PIN, OUTPUT);
  pinMode(MOTOR2_PIN, OUTPUT);
  pinMode(PIR_PIN, INPUT_PULLDOWN);  // évite les parasites si le fil est débranché
  pinMode(DOOR_PIN, INPUT_PULLUP);   // capteur absent = pas d'obstacle = porte ouverte
  pinMode(LOCK_PIN, OUTPUT);
  pinMode(SPEAKER_PIN, OUTPUT);
  digitalWrite(SPEAKER_PIN, LOW);
  digitalWrite(LOCK_PIN, LOW);
  SPI.begin();
  rfidInit();
  servo.attach(SERVO_PIN);
  servo.write(servoAngle);
  Wire.begin();
  Wire.setClock(400000);
  oledProbe();
  Bridge.begin();
  Bridge.provide("get_temperature", get_temperature);
  Bridge.provide("get_humidity", get_humidity);
  Bridge.provide("get_dht_error", get_dht_error);
  Bridge.provide("get_dht_model", get_dht_model);
  Bridge.provide("get_oled", get_oled);
  Bridge.provide_safe("i2c_scan", i2c_scan);
  Bridge.provide("get_pir", get_pir);
  Bridge.provide("get_lid", get_lid);
  Bridge.provide("get_lid_source", get_lid_source);
  Bridge.provide("set_lid_sim", set_lid_sim);
  Bridge.provide("get_rfid_seq", get_rfid_seq);
  Bridge.provide_safe("get_rfid_uid", get_rfid_uid);
  Bridge.provide("get_armed", get_armed);
  Bridge.provide_safe("set_armed", set_armed);
  Bridge.provide("get_pir_count", get_pir_count);
  Bridge.provide("get_pir_last", get_pir_last);
  Bridge.provide("get_pir_hold", get_pir_hold);
  Bridge.provide("set_pir_hold", set_pir_hold);
  Bridge.provide("get_servo", get_servo);
  Bridge.provide("get_servo_target", get_servo_target);
  Bridge.provide("set_servo", set_servo);
  Bridge.provide_safe("show_face", show_face);
  Bridge.provide_safe("show_badge", show_badge);
  Bridge.provide_safe("play_sound", play_sound);
  Bridge.provide_safe("stop_sound", stop_sound);
  Bridge.provide("get_sound", get_sound);
  Bridge.provide_safe("run_motor", run_motor);
  Bridge.provide_safe("move_motor", move_motor);
  Bridge.provide("get_motor", get_motor);
  Bridge.provide("get_rfid_resets", get_rfid_resets);
  Bridge.provide("get_rfid_seen", get_rfid_seen);
  Bridge.provide_safe("get_rfid_version", get_rfid_version);
}

void loop() {
  soundUpdate();
  if (motorDir && (long)(millis() - motorUntil) >= 0) motorSet(0);
  // Badge : lecture toutes les 150 ms ; un même badge n'est compté qu'une fois toutes les 2 s
  if (millis() - rfidLastCheck >= 1000) {
    rfidLastCheck = millis();
    rfidCheck();
  }
  if (millis() - rfidLastPoll >= 200) {
    rfidLastPoll = millis();
    rfid.PCD_AntennaOn();
    delay(10);  // le temps que le badge s'alimente dans le champ (5 ms minimum pour un MIFARE)
    if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
      String uid = "";
      for (byte i = 0; i < rfid.uid.size; i++) {
        if (rfid.uid.uidByte[i] < 0x10) uid += "0";
        uid += String(rfid.uid.uidByte[i], HEX);
      }
      uid.toUpperCase();
      if (uid != rfidUid || millis() - rfidLastRead > 2000) {
        rfidUid = uid;
        rfidSeq++;
        // UID affiché tout de suite (AB:0C:A4:CA), en attendant la décision du backend
        char shown[24] = "";
        for (unsigned i = 0; i < uid.length() && strlen(shown) < sizeof(shown) - 3; i += 2) {
          if (i) strcat(shown, ":");
          strncat(shown, uid.c_str() + i, 2);
        }
        setBadge(1, shown, "", 3);
      }
      rfidLastRead = millis();
      oledReinitAt = millis() + 300;  // après le pic de courant du lecteur
      rfid.PICC_HaltA();
      rfid.PCD_StopCrypto1();
    }
    rfid.PCD_AntennaOff();
  }

  // Porte : état stable 100 ms avant d'être pris en compte
  static int doorRaw = 0;
  static unsigned long doorRawSince = 0;
  int dr = digitalRead(DOOR_PIN) == HIGH;  // HIGH = aucun reflet = porte ouverte
  if (dr != doorRaw) { doorRaw = dr; doorRawSince = millis(); }
  if (millis() - doorRawSince >= 100) doorOpen = doorRaw;

  // PIR : anti-rebond de 50 ms sur le signal brut, puis maintien pirHoldMs après le dernier HIGH
  static int pirRaw = 0, pirStable = 0;
  static unsigned long pirRawSince = 0;
  int p = digitalRead(PIR_PIN);
  if (p != pirRaw) { pirRaw = p; pirRawSince = millis(); }
  if (millis() - pirRawSince >= 50) pirStable = pirRaw;
  if (pirStable) { pirLastMs = millis(); pirSeen = true; }
  int active = pirSeen && (pirStable || millis() - pirLastMs < pirHoldMs);
  if (active && !pirState) { pirCount++; pirAlertStart = millis(); }
  pirState = active;

  // Servo : avance vers la cible au rythme de servoSpeed (plusieurs degrés par tour si besoin)
  if (servoAngle == servoTarget) {
    servoLastStep = millis();
  } else {
    int steps = (millis() - servoLastStep) * servoSpeed / 1000;
    if (steps > 0) {
      servoLastStep = millis();
      int delta = servoTarget - servoAngle;
      servoAngle += constrain(delta, -steps, steps);
      servo.write(servoAngle);
    }
  }

  // Écran : rafraîchi toutes les 100 ms (clignotement de l'alerte) ; on recherche l'écran toutes les 3 s s'il est absent
  if (!oledOk && millis() - oledLastProbe >= 3000) {
    oledLastProbe = millis();
    oledProbe();
  }
  if (oledOk && ((oledReinitAt && (long)(millis() - oledReinitAt) >= 0) || millis() - oledLastReinit >= 10000)) {
    oledReinitAt = 0;
    oledReinit();
    rfidCheck();  // le démarrage de l'écran peut lui aussi faire chuter le 3,3 V
  }
  if (oledOk && millis() - oledLastDraw >= 100) {
    oledLastDraw = millis();
    oledDraw();
  }

  // DHT11 : une lecture toutes les 2 s maximum
  if (millis() - lastRead >= 2000) {
    lastRead = millis();
    float t, h;
    lastErr = readDHT11(t, h);
    if (lastErr == 0) { lastTemp = t; lastHum = h; }
  }
  delay(10);
}
