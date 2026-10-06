// Sentinel-X : détecteur de mouvement HC-SR501 (PIR), envoyé en JSON sur le port série USB.
// Une ligne par message, lue par la passerelle (firmware/gateway/serial_gateway.py) qui ajoute
// device, seq et ts puis publie sur sentinel/box01/<topic>.
//
// Dans l'autre sens, la passerelle envoie les commandes du backend, une par ligne :
// {"cmd":"arm"}, {"cmd":"disarm"}, {"cmd":"buzzer_on"}, {"cmd":"buzzer_off"}, {"cmd":"reboot"}.
//
// Câblage HC-SR501 : VCC -> 5V, GND -> GND, OUT -> D2.
// Buzzer actif (module avec oscillateur intégré) : + -> D8, - -> GND.
// Potentiomètres du PIR : sensibilité au milieu, temporisation au minimum ; cavalier en position
// « H » (redéclenchement) pour que la sortie reste haute tant que ça bouge.

#if defined(__AVR__)
#include <avr/wdt.h>
#endif

const uint8_t PIR_PIN = 2;
const uint8_t BUZZER_PIN = 8;
const uint8_t LED_PIN = LED_BUILTIN;              // allumée pendant un mouvement
const unsigned long BAUD = 115200;
const unsigned long WARMUP_MS = 60000UL;          // le HC-SR501 se stabilise environ 1 min après la mise sous tension
const unsigned long HEARTBEAT_MS = 15000UL;       // contrat MQTT : heartbeat toutes les 15 s
const unsigned long DEBOUNCE_MS = 200;
const unsigned long BUZZER_MAX_MS = 60000UL;      // sécurité : le buzzer s'arrête seul si buzzer_off n'arrive jamais

int reportedState = -1;                           // dernier état envoyé (-1 : rien envoyé)
int candidateState = LOW;
unsigned long candidateSince = 0;
unsigned long lastHeartbeat = 0;

bool armed = false;
bool buzzerOn = false;
unsigned long buzzerSince = 0;

char cmdLine[48];                                 // ligne de commande en cours de réception
uint8_t cmdLen = 0;

void sendHeartbeat(unsigned long now) {
  Serial.print(F("{\"topic\":\"heartbeat\",\"type\":\"heartbeat\",\"data\":{\"uptime\":"));
  Serial.print(now / 1000UL);
  Serial.print(F(",\"firmware\":\"sx-pir-serial 0.2\",\"warmup\":"));
  Serial.print(now < WARMUP_MS ? F("true") : F("false"));
  Serial.print(F(",\"armed\":"));
  Serial.print(armed ? F("true") : F("false"));
  Serial.println(F("}}"));
}

void sendPir(int state) {
  Serial.print(F("{\"topic\":\"event\",\"type\":\"pir\",\"data\":{\"state\":"));
  Serial.print(state == HIGH ? 1 : 0);
  Serial.println(F("}}"));
}

void setBuzzer(bool on, unsigned long now) {
  buzzerOn = on;
  buzzerSince = now;
  digitalWrite(BUZZER_PIN, on ? HIGH : LOW);
}

void reboot() {
#if defined(__AVR__)
  wdt_enable(WDTO_15MS);                          // le chien de garde redémarre la carte dans 15 ms
  while (true) {}
#elif defined(__arm__)
  NVIC_SystemReset();
#endif
}

// La passerelle a déjà vérifié la commande (équipement, anti-rejeu) : ici on se contente de la reconnaître.
void handleCommand(const char *line, unsigned long now) {
  if (strstr(line, "\"cmd\":\"buzzer_on\"")) setBuzzer(true, now);
  else if (strstr(line, "\"cmd\":\"buzzer_off\"")) setBuzzer(false, now);
  else if (strstr(line, "\"cmd\":\"arm\"")) armed = true;
  else if (strstr(line, "\"cmd\":\"disarm\"")) { armed = false; setBuzzer(false, now); }
  else if (strstr(line, "\"cmd\":\"reboot\"")) reboot();
}

// Lecture non bloquante : on accumule les caractères reçus jusqu'au retour à la ligne.
void readCommands(unsigned long now) {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n') {
      cmdLine[cmdLen] = '\0';
      handleCommand(cmdLine, now);
      cmdLen = 0;
    } else if (c != '\r' && cmdLen < sizeof(cmdLine) - 1) {
      cmdLine[cmdLen++] = c;                      // une ligne trop longue est tronquée, donc ignorée
    }
  }
}

void setup() {
#if defined(__AVR__)
  wdt_disable();                                  // après un reboot par le chien de garde
#endif
  Serial.begin(BAUD);
  pinMode(PIR_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  sendHeartbeat(millis());
}

void loop() {
  unsigned long now = millis();

  readCommands(now);
  if (buzzerOn && now - buzzerSince >= BUZZER_MAX_MS) {
    setBuzzer(false, now);
  }

  if (now - lastHeartbeat >= HEARTBEAT_MS) {
    lastHeartbeat = now;
    sendHeartbeat(now);
  }

  // Pas de delay() : la boucle reste réactive. Un changement doit durer DEBOUNCE_MS pour compter.
  int state = digitalRead(PIR_PIN);
  if (state != candidateState) {
    candidateState = state;
    candidateSince = now;
  }
  if (now < WARMUP_MS || now - candidateSince < DEBOUNCE_MS) {
    return;
  }
  if (candidateState != reportedState) {
    reportedState = candidateState;
    digitalWrite(LED_PIN, reportedState);
    sendPir(reportedState);
  }
}
