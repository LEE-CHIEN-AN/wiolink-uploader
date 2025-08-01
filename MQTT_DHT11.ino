#include <ESP8266WiFi.h>
#include <PubSubClient.h>

//Setup for DHT======================================
#include <DHT.h>
#define DHTPIN 13  //wio link D1 is 12

// Uncomment the type of sensor in use:
//#define DHTTYPE    DHT11     // DHT 11
#define DHTTYPE    DHT11     // DHT 22 (AM2302)
//#define DHTTYPE    DHT21     // DHT 21 (AM2301)
DHT dht(DHTPIN, DHTTYPE);

#define mqttPort 1883  // MQTT伺服器埠號

const char* ssid = "jie";
const char* password = "0926197320";
const char* mqttServer = "mqtt3.thingspeak.com";  // MQTT伺服器位址
const char* mqttUserName = "JxEuFCQcEysYMT0bODMPIw8";
const char* mqttPwd = "p8uhCyYaqnHcTENbDaOMsgdg";
const char* clientID = "JxEuFCQcEysYMT0bODMPIw8";
const char* topic = "channels/3022873/publish";  // 不用填「寫入API密鑰」

unsigned long prevMillis = 0;  // 暫存經過時間（毫秒）
const long interval = 20000;  // 上傳資料的間隔時間，20秒。
String msgStr = "";      // 暫存MQTT訊息字串


float t;  // 暫存溫度
int h;   // 暫存濕度

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

void setup() {
  pinMode(15, OUTPUT); //wio link power
  digitalWrite(15, HIGH);

  Serial.begin(115200);
  setup_wifi();
  client.setServer(mqttServer, mqttPort);

  //For DHT sensor
  dht.begin();
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // 等待20秒
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

    // 組合MQTT訊息；field1填入溫度、field2填入濕度
    msgStr = msgStr + "field1=" + t + "&field2=" + h;

    Serial.print("Publish message: ");
    Serial.println(msgStr);
    client.publish(topic, msgStr.c_str());       // 發布MQTT主題與訊息
    msgStr = "";
  }
}
