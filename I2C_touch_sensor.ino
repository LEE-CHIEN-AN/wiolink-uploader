#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <ESPSupabase.h>
#include <ArduinoJson.h>

// ===== I2C Touch (MPR121 via Grove I2C Touch Sensor) =====
#include <i2c_touch_sensor.h>
#include <MPR121.h>
i2ctouchsensor touchsensor;

// ===== Supabase =====
const char* supabaseUrl = "https://orlmyfjhqcmlrbrlonbt.supabase.co";
const char* supabaseKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ybG15ZmpocWNtbHJicmxvbmJ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMDIyNTAsImV4cCI6MjA2MDc3ODI1MH0.uDgPqDhmv-qLZnBYaTIuN4Y-z21foH39kefj_lHqCu0";  // 建議不要硬寫在公開repo
Supabase supabase;

// ===== MQTT (ThingSpeak) =====
#define mqttPort 1883
const char* ssid = "CAECE611 2G";
const char* password = "116eceac";
const char* mqttServer = "mqtt3.thingspeak.com";
const char* mqttUserName = "KSo1KicrAgoOLR8wJBsFLhM";
const char* mqttPwd = "d3l5bnqw64+uExQAU5xDk9gy";
const char* clientID = "KSo1KicrAgoOLR8wJBsFLhM";
const char* topic = "channels/3026055/publish";

WiFiClient espClient;
PubSubClient client(espClient);

// ===== Touch mapping =====
const int CH_TEMP_PLUS  = 3;  // CH3 = 溫度+
const int CH_TEMP_MINUS = 0;  // CH0 = 溫度-

// ===== Periodic upload =====
unsigned long prevUploadMs = 0;
const unsigned long uploadIntervalMs = 60000;  // 60 秒

// ===== Touch polling =====
unsigned long lastTouchPollMs = 0;
const unsigned long touchPollIntervalMs = 50;  // 50~100ms
uint16_t lastTouched = 0;

// ===== Debounce (avoid multi-trigger) =====
unsigned long lastActionMs = 0;
const unsigned long debounceMs = 250;

// ===== Data to send =====
// 方案：用「計數」最清楚（每 60 秒內按了幾次）
volatile int touch_add_count = 0;
volatile int touch_minus_count = 0;

// 最近一次事件（即時上傳用：1 表示這次上傳是由按下觸發）
int touch_add_event = 0;
int touch_minus_event = 0;

String msgStr;

// ---------- WiFi / MQTT ----------
void setup_wifi() {
  delay(10);
  Serial.print("Connecting WiFi");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");
}

void reconnect_mqtt() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(clientID, mqttUserName, mqttPwd)) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" retry in 5 seconds");
      delay(5000);
    }
  }
}

// ---------- Upload helpers ----------
void publishMQTT(int addVal, int minusVal) {
  // ThingSpeak MQTT: field1..field8
  msgStr = "field1=" + String(addVal) + "&field2=" + String(minusVal);

  Serial.print("MQTT publish: ");
  Serial.println(msgStr);

  client.publish(topic, msgStr.c_str());
  msgStr = "";
}

void insertSupabase(int addVal, int minusVal) {
  // 你原本 insert("wiolink", jsonData, false) 我保留同樣呼叫方式
  // 注意：這裡欄位名要符合你 Supabase table schema
  String jsonData = String("{") +
    "\"name\": \"604_aircondition\"," +
    "\"touch_add\": " + String(addVal) + "," +
    "\"touch_minus\": " + String(minusVal) +
  "}";

  int res = supabase.insert("wiolink", jsonData, false);
  if (res == 200 || res == 201) {
    Serial.println("Supabase: Data inserted successfully!");
  } else {
    Serial.print("Supabase: Failed. HTTP: ");
    Serial.println(res);
  }
}

// 即時上傳：用 event（0/1）或你也可改成上傳當下累計
void sendImmediateIfNeeded() {
  if (touch_add_event == 0 && touch_minus_event == 0) return;

  // 即時事件上傳（0/1）
  publishMQTT(touch_add_event, touch_minus_event);
  insertSupabase(touch_add_event, touch_minus_event);

  // 清掉事件旗標
  touch_add_event = 0;
  touch_minus_event = 0;
}

// 定時上傳：用 count（這 60 秒按了幾次）
void sendPeriodicCounts() {
  publishMQTT(touch_add_count, touch_minus_count);
  insertSupabase(touch_add_count, touch_minus_count);

  // 清掉計數器
  touch_add_count = 0;
  touch_minus_count = 0;
}

// ---------- Touch polling (core) ----------
void pollTouch() {
  unsigned long now = millis();
  if (now - lastTouchPollMs < touchPollIntervalMs) return;
  lastTouchPollMs = now;

  touchsensor.getTouchState();
  uint16_t curTouched = touchsensor.touched;

  uint16_t justPressed  = (curTouched) & (~lastTouched);
  // uint16_t justReleased = (~curTouched) & (lastTouched); // 如需放開事件再開

  // 只在按下那一刻觸發（避免狂刷）
  if (justPressed & (1 << CH_TEMP_PLUS)) {
    if (now - lastActionMs > debounceMs) {
      Serial.println("[CH3] TEMP + pressed");
      touch_add_count++;
      touch_add_event = 1;      // 即時事件上傳
      lastActionMs = now;
    }
  }

  if (justPressed & (1 << CH_TEMP_MINUS)) {
    if (now - lastActionMs > debounceMs) {
      Serial.println("[CH0] TEMP - pressed");
      touch_minus_count++;
      touch_minus_event = 1;    // 即時事件上傳
      lastActionMs = now;
    }
  }

  lastTouched = curTouched;
}

void setup() {
  Serial.begin(115200);
  Wire.begin();

  // Wio Link：GPIO15 是 boot strap 腳；你若確定用來供電才這樣做
  pinMode(15, OUTPUT);
  digitalWrite(15, HIGH);

  Serial.println("Init touch sensor...");
  touchsensor.initialize();
  Serial.println("Touch sensor ready.");

  setup_wifi();
  client.setServer(mqttServer, mqttPort);

  //
  supabase.begin(supabaseUrl, supabaseKey);

  prevUploadMs = millis();
}

void loop() {
  // MQTT keep-alive
  if (!client.connected()) reconnect_mqtt();
  client.loop();

  // 1) 先輪詢 touch（非阻塞）
  pollTouch();

  // 2) 若有按鍵事件：即時上傳（0/1）
  sendImmediateIfNeeded();

  // 3) 每 60 秒上傳一次累計（按了幾次）
  //unsigned long now = millis();
  //if (now - prevUploadMs >= uploadIntervalMs) {
    //prevUploadMs = now;
    //Serial.println("Periodic upload (counts in last interval)...");
    //sendPeriodicCounts();
  //}
}
