/*
  MLX90641 (12x16) -> Supabase thermal_frames (minimal)
  Inserts: { session_id: "...", ts: "...optional...", data: [192 floats] }

  Recommended upload interval: 2000 ms (2 sec)
*/

#include <Wire.h>

// ===== MLX90641 =====
#define USE_MLX90641
#include "MLX90641_API.h"
#include "MLX9064X_I2C_Driver.h"

// ===== WiFi / Supabase =====
#include <ESP8266WiFi.h>
#include <ESP8266WiFiMulti.h>
#include <WiFiClientSecure.h>
#include <ESPSupabase.h>
#include <ArduinoJson.h>
#include <time.h>

// ---------- USER CONFIG ----------
static const char* SESSION_ID = "604_windowside";   // 你要的 session id（不是 UUID）

// WiFi multi
ESP8266WiFiMulti wifiMulti;

// Supabase
static const char* SUPABASE_URL = "https://orlmyfjhqcmlrbrlonbt.supabase.co";
static const char* SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ybG15ZmpocWNtbHJicmxvbmJ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMDIyNTAsImV4cCI6MjA2MDc3ODI1MH0.uDgPqDhmv-qLZnBYaTIuN4Y-z21foH39kefj_lHqCu0"; // 建議用 RLS + anon key
Supabase supabase;

// Upload tuning
static const uint32_t UPLOAD_INTERVAL_MS = 5000;  // 建議 2000ms，可改 1000ms

// If your DB has ts default now(), you can set SEND_TS=false to omit ts
static const bool SEND_TS = false;  // true: 上傳 ts (需要 NTP 成功); false: 不上傳 ts，DB default now()

// Orientation (if you want to flip in post-processing, keep raw here)
static const byte ROWS = 12;
static const byte COLS = 16;

const byte MLX90641_address = 0x33;
#define TA_SHIFT 8

uint16_t eeMLX90641[832];
float MLX90641To[192];
uint16_t MLX90641Frame[242];
paramsMLX90641 MLX90641;

// Wio Link power pin (ESP8266 GPIO15)
static const int WIO_POWER_PIN = 15;

// Upload timer
uint32_t lastUploadMs = 0;

// ---------- helpers ----------
boolean isConnected() {
  Wire.beginTransmission((uint8_t)MLX90641_address);
  return (Wire.endTransmission() == 0);
}

String iso8601_now_utc() {
  time_t now = time(nullptr);
  struct tm tm_utc;
  gmtime_r(&now, &tm_utc);

  char buf[32];
  // e.g. 2026-01-05T13:20:30Z
  snprintf(buf, sizeof(buf),
           "%04d-%02d-%02dT%02d:%02d:%02dZ",
           tm_utc.tm_year + 1900, tm_utc.tm_mon + 1, tm_utc.tm_mday,
           tm_utc.tm_hour, tm_utc.tm_min, tm_utc.tm_sec);
  return String(buf);
}

bool ensure_ntp_ready(uint32_t timeout_ms = 15000) {
  if (!SEND_TS) return true;
  uint32_t start = millis();
  while (millis() - start < timeout_ms) {
    time_t now = time(nullptr);
    // 1700000000 ~ 2023-11-14; 只要大於這個就表示 NTP 大機率成功
    if (now > 1700000000) return true;
    delay(200);
  }
  return false;
}

void wifi_connect() {
  // Add APs (依你現場)
  wifiMulti.addAP("CAECE611 2G", "116eceac");
  wifiMulti.addAP("RLab_2.4G", "ntucerlab");
  wifiMulti.addAP("jie", "0926197320");
  wifiMulti.addAP("i_want_to_go_home", "33438542");

  Serial.print("Connecting WiFi");
  while (wifiMulti.run() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi connected. SSID=");
  Serial.print(WiFi.SSID());
  Serial.print(" IP=");
  Serial.println(WiFi.localIP());
}

// ---------- setup ----------
void setup() {
  pinMode(WIO_POWER_PIN, OUTPUT);
  digitalWrite(WIO_POWER_PIN, HIGH);

  Serial.begin(115200);
  delay(200);

  Wire.begin();
  Wire.setClock(400000); // 400kHz stable on ESP8266

  // WiFi + Supabase
  wifi_connect();
  supabase.begin(SUPABASE_URL, SUPABASE_KEY);

  // NTP (only if SEND_TS=true)
  if (SEND_TS) {
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    bool ok = ensure_ntp_ready();
    Serial.print("NTP ready = ");
    Serial.println(ok ? "YES" : "NO (will likely fail if ts is required)");
  }

  // MLX init
  if (!isConnected()) {
    Serial.println("MLX90641 not detected at I2C 0x33. Check wiring.");
    while (1) delay(1000);
  }

  int status = MLX90641_DumpEE(MLX90641_address, eeMLX90641);
  if (status != 0) {
    Serial.println("Failed to load MLX90641 parameters");
    while (1) delay(1000);
  }

  status = MLX90641_ExtractParameters(eeMLX90641, &MLX90641);
  if (status != 0) {
    Serial.println("MLX90641 parameter extraction failed");
    while (1) delay(1000);
  }

  // Sensor refresh rate: 4Hz is fine for upload 1-2s
  MLX90641_SetRefreshRate(MLX90641_address, 0x03); // 4Hz

  Serial.println("Setup done.");
}

// ---------- main loop ----------
void loop() {
  // Keep WiFi alive
  if (wifiMulti.run() != WL_CONNECTED) {
    Serial.println("WiFi not connected, retrying...");
    delay(500);
    return;
  }

  // Read 1 frame (do 2 reads as recommended in examples to stabilize)
  for (byte x = 0 ; x < 2 ; x++) {
    int status = MLX90641_GetFrameData(MLX90641_address, MLX90641Frame);
    if (status < 0) {
      Serial.println("MLX90641_GetFrameData error");
      delay(50);
      return;
    }

    float Ta = MLX90641_GetTa(MLX90641Frame, &MLX90641);
    float tr = Ta - TA_SHIFT;
    float emissivity = 0.95;

    MLX90641_CalculateTo(MLX90641Frame, &MLX90641, emissivity, tr, MLX90641To);
  }

  // Upload throttling
  uint32_t nowMs = millis();
  if (nowMs - lastUploadMs < UPLOAD_INTERVAL_MS) {
    delay(10);
    return;
  }
  lastUploadMs = nowMs;

  // Build JSON payload
  // Capacity sizing: 192 floats + object keys. 12~16KB is safe on ESP8266.
  DynamicJsonDocument doc(16384);
  doc["session_id"] = SESSION_ID;

  if (SEND_TS) {
    // only do this if NTP is ready
    doc["ts"] = iso8601_now_utc();
  }

  JsonArray arr = doc.createNestedArray("data");
  for (int i = 0; i < 192; i++) {
    arr.add(MLX90641To[i]);
  }

  String payload;
  serializeJson(doc, payload);

  // Insert to Supabase table "thermal_frames"
  int res = supabase.insert("thermal_frames", payload, false);

  if (res == 200 || res == 201) {
    Serial.println("Supabase insert OK");
  } else {
    Serial.print("Supabase insert FAIL HTTP=");
    Serial.println(res);
    // 失敗時可以稍微 backoff，避免瘋狂重送
    delay(200);
  }

  delay(10);
}
