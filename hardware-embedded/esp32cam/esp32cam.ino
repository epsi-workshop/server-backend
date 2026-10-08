// ESP32-CAM (AI-Thinker, OV2640) : flux MJPEG en Wi-Fi
//   http://<ip>/capture      -> une photo JPEG
//   http://<ip>:81/stream    -> flux MJPEG en direct
//   http://<ip>/status       -> infos JSON
// Authentification HTTP Basic sur les trois routes (CAM_USER / CAM_PASSWORD de secrets.h, cahier 7.6) :
// sans elle, tout appareil du Wi-Fi peut regarder la salle.
// Deux modes (voir secrets.h) :
//   - point d'accès (WIFI_AP_MODE) : la caméra crée son propre Wi-Fi, IP fixe 192.168.4.1
//   - client : la caméra rejoint un Wi-Fi existant, joignable via esp32cam.local
#include <WiFi.h>
#include <ESPmDNS.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "mbedtls/base64.h"
#include "secrets.h"  // WIFI_SSID / WIFI_PASSWORD / WIFI_AP_MODE / CAM_USER / CAM_PASSWORD

static_assert(sizeof(WIFI_PASSWORD) - 1 >= 8,
              "WIFI_PASSWORD doit faire au moins 8 caracteres (exigence WPA2)");
#if !defined(CAM_USER) || !defined(CAM_PASSWORD)
#error "Definir CAM_USER et CAM_PASSWORD dans secrets.h (authentification du flux, voir secrets.example.h)"
#endif
static_assert(sizeof(CAM_PASSWORD) - 1 >= 12, "CAM_PASSWORD doit faire au moins 12 caracteres");
constexpr bool sameText(const char *a, const char *b) { return *a == *b && (*a == '\0' || sameText(a + 1, b + 1)); }
static_assert(!sameText(CAM_PASSWORD, "a-remplacer-12car"), "Remplacer CAM_PASSWORD dans secrets.h (valeur d'exemple)");

// Brochage AI-Thinker
#define PWDN_GPIO_NUM  32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM   0
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27
#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    21
#define Y4_GPIO_NUM    19
#define Y3_GPIO_NUM    18
#define Y2_GPIO_NUM     5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22
#define FLASH_LED_PIN   4

#define BOUNDARY "frame"
static const char *STREAM_TYPE = "multipart/x-mixed-replace;boundary=" BOUNDARY;
static const char *STREAM_PART = "\r\n--" BOUNDARY "\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t mainServer = NULL;
httpd_handle_t streamServer = NULL;

// « Basic <base64(CAM_USER:CAM_PASSWORD)> », calculé une fois au démarrage
static char expectedAuth[160];

static void initAuth() {
  const char *creds = CAM_USER ":" CAM_PASSWORD;
  size_t olen = 0;
  strcpy(expectedAuth, "Basic ");
  mbedtls_base64_encode((unsigned char *)expectedAuth + 6, sizeof(expectedAuth) - 7, &olen,
                        (const unsigned char *)creds, strlen(creds));
  expectedAuth[6 + olen] = '\0';
}

// Comparaison en temps constant : la durée de la réponse ne renseigne pas sur le mot de passe
static bool authorized(httpd_req_t *req) {
  char got[sizeof(expectedAuth)] = {0};
  if (httpd_req_get_hdr_value_str(req, "Authorization", got, sizeof(got)) != ESP_OK) return false;
  size_t n = strlen(expectedAuth);
  if (strlen(got) != n) return false;
  unsigned char diff = 0;
  for (size_t i = 0; i < n; i++) diff |= (unsigned char)(got[i] ^ expectedAuth[i]);
  return diff == 0;
}

static esp_err_t deny(httpd_req_t *req) {
  httpd_resp_set_status(req, "401 Unauthorized");
  httpd_resp_set_hdr(req, "WWW-Authenticate", "Basic realm=\"esp32cam\"");
  return httpd_resp_send(req, NULL, 0);
}

static esp_err_t capture_handler(httpd_req_t *req) {
  if (!authorized(req)) return deny(req);
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

static esp_err_t stream_handler(httpd_req_t *req) {
  if (!authorized(req)) return deny(req);
  char part[128];
  esp_err_t res = httpd_resp_set_type(req, STREAM_TYPE);
  while (res == ESP_OK) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      res = ESP_FAIL;
      break;
    }
    size_t hlen = snprintf(part, sizeof(part), STREAM_PART, fb->len);
    res = httpd_resp_send_chunk(req, part, hlen);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
  }
  return res;
}

static esp_err_t status_handler(httpd_req_t *req) {
  if (!authorized(req)) return deny(req);
  char json[192];
#ifdef WIFI_AP_MODE
  snprintf(json, sizeof(json),
           "{\"mode\":\"ap\",\"ssid\":\"%s\",\"ip\":\"%s\",\"clients\":%d,\"uptime_s\":%lu,\"psram\":%s}",
           WIFI_SSID, WiFi.softAPIP().toString().c_str(), WiFi.softAPgetStationNum(),
           millis() / 1000, psramFound() ? "true" : "false");
#else
  snprintf(json, sizeof(json),
           "{\"mode\":\"sta\",\"ssid\":\"%s\",\"ip\":\"%s\",\"rssi\":%d,\"uptime_s\":%lu,\"psram\":%s}",
           WIFI_SSID, WiFi.localIP().toString().c_str(), WiFi.RSSI(),
           millis() / 1000, psramFound() ? "true" : "false");
#endif
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_sendstr(req, json);
}

void startServers() {
  initAuth();
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  httpd_uri_t capture = {"/capture", HTTP_GET, capture_handler, NULL};
  httpd_uri_t status = {"/status", HTTP_GET, status_handler, NULL};
  if (httpd_start(&mainServer, &config) == ESP_OK) {
    httpd_register_uri_handler(mainServer, &capture);
    httpd_register_uri_handler(mainServer, &status);
  }
  // Serveur séparé pour le flux, pour que /capture reste disponible pendant un stream
  config.server_port = 81;
  config.ctrl_port += 1;
  httpd_uri_t stream = {"/stream", HTTP_GET, stream_handler, NULL};
  if (httpd_start(&streamServer, &config) == ESP_OK) {
    httpd_register_uri_handler(streamServer, &stream);
  }
}

bool initCamera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.grab_mode = CAMERA_GRAB_LATEST;  // toujours l'image la plus récente (faible latence)
  if (psramFound()) {
    c.frame_size = FRAMESIZE_VGA;    // 640x480
    c.jpeg_quality = 12;
    c.fb_count = 2;
    c.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    c.frame_size = FRAMESIZE_QVGA;   // 320x240
    c.jpeg_quality = 15;
    c.fb_count = 1;
    c.fb_location = CAMERA_FB_IN_DRAM;
  }
  return esp_camera_init(&c) == ESP_OK;
}

void setup() {
  Serial.begin(115200);
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);

  if (!initCamera()) {
    Serial.println("ERREUR: camera non initialisee");
    delay(3000);
    ESP.restart();
  }

  WiFi.setSleep(false);  // évite les saccades du flux
  WiFi.setHostname("esp32cam");
#ifdef WIFI_AP_MODE
  // La caméra crée son propre réseau ; elle est toujours en 192.168.4.1
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP(WIFI_SSID, WIFI_PASSWORD)) {
    Serial.println("ERREUR: point d'acces non cree");
    delay(3000);
    ESP.restart();
  }
  Serial.printf("Point d'acces \"%s\" cree, IP: %s\n", WIFI_SSID, WiFi.softAPIP().toString().c_str());
#else
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connexion Wi-Fi");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > 30000) ESP.restart();
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nOK, IP: %s\n", WiFi.localIP().toString().c_str());
#endif

  MDNS.begin("esp32cam");
  MDNS.addService("http", "tcp", 80);
  startServers();
#ifdef WIFI_AP_MODE
  Serial.println("Flux: http://192.168.4.1:81/stream");
#else
  Serial.println("Flux: http://esp32cam.local:81/stream");
#endif
}

void loop() {
#ifndef WIFI_AP_MODE
  // Reconnexion automatique si le Wi-Fi tombe
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(5000);
  }
#endif
  delay(1000);
}
