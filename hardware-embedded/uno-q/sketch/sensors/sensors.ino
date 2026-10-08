// Capteurs UNO Q (MCU STM32) -> Bridge -> API Python (Linux)
//   DHT11 ou DHT22 (temp./humidité) : données sur D2, + sur 3V3, - sur GND (modèle détecté auto)
//   PIR HC-SR501 (mouvement)       : OUT sur D7, VCC sur 5V, GND sur GND
//   Servo SG90 (rotation caméra)   : signal (orange) sur D9, rouge sur 5V, marron sur GND
//   Écran OLED SSD1306 128x64 I2C  : SDA sur SDA, SCL sur SCL, VCC sur 3V3, GND sur GND
#include <Arduino_RouterBridge.h>
#include <Servo.h>
#include <Wire.h>
#include <U8g2lib.h>
#include <zephyr/kernel.h>

#define DHT_PIN   2
#define PIR_PIN   7
#define SERVO_PIN 9

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
    oledOk = true;
  }
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
    oled.drawBox(0, 0, 128, 64);
    oled.setDrawColor(0);
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
    oled.drawBox(0, 0, 128, 64);
    oled.setDrawColor(0);
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
  oled.drawStr(92, 10, "ARME");
  if ((millis() / 1000) % 2) oled.drawDisc(122, 6, 2);  // témoin de vie
  oled.setDrawColor(1);

  oled.setFont(u8g2_font_helvB14_tr);
  drawCentered(36, "R.A.S.");

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

static void oledDraw() {
  oled.clearBuffer();
  if (faceKind && (long)(faceUntil - millis()) > 0) oledDrawFace();
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
  return faceKind;
}

void setup() {
  pinMode(PIR_PIN, INPUT_PULLDOWN);  // évite les parasites si le fil est débranché
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
  Bridge.provide("get_pir_count", get_pir_count);
  Bridge.provide("get_pir_last", get_pir_last);
  Bridge.provide("get_pir_hold", get_pir_hold);
  Bridge.provide("set_pir_hold", set_pir_hold);
  Bridge.provide("get_servo", get_servo);
  Bridge.provide("get_servo_target", get_servo_target);
  Bridge.provide("set_servo", set_servo);
  Bridge.provide_safe("show_face", show_face);
}

void loop() {
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
