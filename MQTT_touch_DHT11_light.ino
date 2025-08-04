#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <Digital_Light_TSL2561.h>
#include <Wire.h>
#include <ESPSupabase.h>
#include <ArduinoJson.h>

//Setup for DHT======================================
#include <DHT.h>
#define DHTPIN 12  //wio link D1 is 12

// Uncomment the type of sensor in use:
//#define DHTTYPE    DHT11     // DHT 11
#define DHTTYPE    DHT11     // DHT 22 (AM2302)
//#define DHTTYPE    DHT21     // DHT 21 (AM2301)
DHT dht(DHTPIN, DHTTYPE);
//Setup for DHT======================================

//Setup for  Supabase
// Supabase credentials==============================
const char* supabaseUrl = "https://orlmyfjhqcmlrbrlonbt.supabase.co";
const char* supabaseKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ybG15ZmpocWNtbHJicmxvbmJ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMDIyNTAsImV4cCI6MjA2MDc3ODI1MH0.uDgPqDhmv-qLZnBYaTIuN4Y-z21foH39kefj_lHqCu0";
Supabase supabase;

//Setup for touch sensor ======================================
const int TouchPin= 14 ;

// Setup for MQTT=============================
#define mqttPort 1883  // MQTT伺服器埠號

const char* ssid = "TP-Link_CDF8_2.4G";
const char* password = "Room901901";
const char* mqttServer = "mqtt3.thingspeak.com";  // MQTT伺服器位址
const char* mqttUserName = "KSo1KicrAgoOLR8wJBsFLhM";
const char* mqttPwd = "d3l5bnqw64+uExQAU5xDk9gy";
const char* clientID = "KSo1KicrAgoOLR8wJBsFLhM";
const char* topic = "channels/3026055/publish";  // 不用填「寫入API密鑰」

unsigned long prevMillis = 0;  // 暫存經過時間（毫秒）
const long interval = 60000;  // 上傳資料的間隔時間，60秒。
String msgStr = "";      // 暫存MQTT訊息字串


WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  delay(10);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect(clientID, mqttUserName, mqttPwd)) {
      Serial.println("MQTT connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);  // 等5秒之後再重試
    }
  }
}
// Setup for MQTT=============================

//變數初始化
float t = -1.0;
int h = -1;
int lux = -1;
int touch = -1;
void sendSensorData() {
  t = dht.readTemperature();
  h = dht.readHumidity();
  lux = TSL2561.readVisibleLux();
  touch = digitalRead(TouchPin);

  msgStr = "field1=" + String(t) + "&field2=" + String(h) +
           "&field3=" + String(lux) + "&field4=" + String(touch);

  Serial.print("📤 發布訊息：");
  Serial.println(msgStr);
  client.publish(topic, msgStr.c_str());
  msgStr = "";
}

void setup() {
  pinMode(15, OUTPUT); //wio link power
  digitalWrite(15, HIGH);

  Serial.begin(115200);
  setup_wifi();
  client.setServer(mqttServer, mqttPort);

  //For DHT sensor
  dht.begin();

  //For light
  Wire.begin();
  TSL2561.init();

  //For touch
  pinMode(TouchPin, INPUT);

  // Init Supabase
  supabase.begin(supabaseUrl, supabaseKey);

}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // 等待60秒
  if (millis() - prevMillis > interval) {
    prevMillis = millis();

    // 讀取DHT11的溫濕度資料
    //read DHT-11---------------------------------------
    t = dht.readTemperature();
    h = dht.readHumidity();
    Serial.print("Humidity = ");
    Serial.print(h);
    Serial.print("% ");
    Serial.print("Temperature = ");
    Serial.print(t);
    Serial.println(" C ");
    //read DHT-11---------------------------------------

    //read light-------------------------
    lux = TSL2561.readVisibleLux();
    Serial.print("The Light value is: ");
    Serial.println(TSL2561.readVisibleLux());
    //read light----------------------------

    //read touch----------------------------
    touch = digitalRead(TouchPin);
    Serial.print("The touch sensor value is: ");
    Serial.println(digitalRead(TouchPin));
    //read touch-----------------------------

    // 組合MQTT訊息；field1填入溫度、field2填入濕度
    msgStr = msgStr + "field1=" + t + "&field2=" + h + "&field3=" + lux + "&field4=" + touch;

    Serial.print("Publish message: ");
    Serial.println(msgStr);
    client.publish(topic, msgStr.c_str());       // 發布MQTT主題與訊息
    msgStr = "";
  }

  // 偵測觸碰變化（touch == 1 時）
  int currentTouchState = digitalRead(TouchPin);
  if (currentTouchState == 1 ) {
    Serial.println("👆 即時觸碰觸發上傳！");
    sendSensorData();  // 立即上傳

    // 上傳到 Supabase
    String jsonData = String("{") +
      "\"name\": \"407_aircondition\"," +
      "\"humidity\": " + String(h) + "," +
      "\"light_intensity\": " + String(lux) + "," +
      "\"celsius_degree\": " + String(t, 2) + "," +
      "\"touch\": " + String(touch) +
      "}";

    int res = supabase.insert("wiolink", jsonData, false);
    if (res == 200 || res == 201) {
      Serial.println("Supabase: Data inserted successfully!");
    } else {
      Serial.print("Supabase: Failed to insert data. HTTP: ");
      Serial.println(res);
    }
  }
}

