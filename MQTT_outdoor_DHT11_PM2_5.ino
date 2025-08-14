#include <ESP8266WiFi.h>
#include <WiFiClient.h>
#include <SimplePgSQL.h>
#include <ESPSupabase.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
//Setup for DHT======================================
#include <DHT.h>
#define DHTPIN 12  //wio link D1 is 12

// Uncomment the type of sensor in use:
//#define DHTTYPE    DHT11     // DHT 11
#define DHTTYPE    DHT11     // DHT 22 (AM2302)
//#define DHTTYPE    DHT21     // DHT 21 (AM2301)
DHT dht(DHTPIN, DHTTYPE);

//Setup for Laser PM2.5======================================================
#include <Seeed_HM330X.h>

#ifdef  ARDUINO_SAMD_VARIANT_COMPLIANCE
    #define SERIAL_OUTPUT SerialUSB
#else
    #define SERIAL_OUTPUT Serial
#endif

HM330X sensor;
uint8_t buf[30];


const char* str[] = {"sensor num: ", "PM1.0 concentration(CF=1,Standard particulate matter,unit:ug/m3): ",
                     "PM2.5 concentration(CF=1,Standard particulate matter,unit:ug/m3): ",
                     "PM10 concentration(CF=1,Standard particulate matter,unit:ug/m3): ",
                     "PM1.0 concentration(Atmospheric environment,unit:ug/m3): ",
                     "PM2.5 concentration(Atmospheric environment,unit:ug/m3): ",
                     "PM10 concentration(Atmospheric environment,unit:ug/m3): ",
                    };

err_t  print_result(const char* str, uint16_t value) {
    if (NULL == str) {
        return ERROR_PARAM;
    }
    SERIAL_OUTPUT.print(str);
    SERIAL_OUTPUT.println(value);
    return NO_ERROR;
}

/*parse buf with 29 uint8_t-data*/
err_t  parse_result(uint8_t* data) {
    uint16_t value = 0;
    if (NULL == data) {
        return ERROR_PARAM;
    }
    for (int i = 1; i < 8; i++) {
        value = (uint16_t) data[i * 2] << 8 | data[i * 2 + 1];
        print_result(str[i - 1], value);

    }

    return NO_ERROR;
}

err_t  parse_result_value(uint8_t* data) {
    if (NULL == data) {
        return ERROR_PARAM;
    }
    for (int i = 0; i < 28; i++) {
        SERIAL_OUTPUT.print(data[i], HEX);
        SERIAL_OUTPUT.print("  ");
        if ((0 == (i) % 5) || (0 == i)) {
            SERIAL_OUTPUT.println("");
        }
    }
    uint8_t sum = 0;
    for (int i = 0; i < 28; i++) {
        sum += data[i];
    }
    if (sum != data[28]) {
        SERIAL_OUTPUT.println("wrong checkSum!!");
    }
    SERIAL_OUTPUT.println("");
    return NO_ERROR;
}
//==================================================================

//定義感測器變數與初始化邏輯
// current temperature & humidity, updated in loop()
float t = -1.0;
int h = -1;
int pm1_0_atm = -1;
int pm2_5_atm = -1;
int pm10_atm = -1;



// Setup for MQTT=============================
#define mqttPort 1883  // MQTT伺服器埠號

const char* ssid = "CAECE611 2G";
const char* password = "116eceac";
const char* mqttServer = "mqtt3.thingspeak.com";  // MQTT伺服器位址
const char* mqttUserName = "DBAyFBgvNygQGTMZATsLOSI";
const char* mqttPwd = "yfWjt4KKC3X00KNvxQLo6mPC";
const char* clientID = "DBAyFBgvNygQGTMZATsLOSI";
const char* topic = "channels/3031639/publish";  // 不用填「寫入API密鑰」

unsigned long prevMillis = 0;  // 暫存經過時間（毫秒）
const long interval = 60000*5;  // 上傳資料的間隔時間，30秒。
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



void setup() {
  pinMode(15, OUTPUT); //wio link power
  digitalWrite(15, HIGH);
  //MQTT
  setup_wifi();
  client.setServer(mqttServer, mqttPort);

  //laser PM2.5============================================
  SERIAL_OUTPUT.begin(115200);
  delay(100);
  SERIAL_OUTPUT.println("Serial start");
  if (sensor.init()) {
      SERIAL_OUTPUT.println("HM330X init failed!!");
      //while (1);
  }

  //For DHT sensor===============================================
  dht.begin();

  Serial.println("Timer set to 60 seconds (timerDelay variable), it will take 60 seconds before publishing the first reading.");
}

void loop() {
  //MQTT
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

   // 等待30秒
  if (millis() - prevMillis > interval) {
    prevMillis = millis();

    //read Laser PM2.5 -----------------------------
    if (sensor.read_sensor_value(buf, 29)) {
      SERIAL_OUTPUT.println("HM330X read result failed!!");
    }
    parse_result_value(buf);
    parse_result(buf);
    SERIAL_OUTPUT.println("");
    delay(1000);
    pm1_0_atm = ((uint16_t)buf[10] << 8) | buf[11];
    pm2_5_atm = ((uint16_t)buf[12] << 8) | buf[13];
    pm10_atm  = ((uint16_t)buf[14] << 8) | buf[15];
    Serial.print("PM1.0_atm: "); Serial.println(pm1_0_atm);
    Serial.print("PM2.5_atm: "); Serial.println(pm2_5_atm);
    Serial.print("PM10_atm: "); Serial.println(pm10_atm);
    //read Laser PM2.5 -----------------------------

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
    msgStr = msgStr + "field1=" + t + "&field2=" + h + "&field3=" + pm1_0_atm + "&field4=" + pm2_5_atm + "&field5=" + pm10_atm;
    Serial.print("Publish message: ");
    Serial.println(msgStr);
    client.publish(topic, msgStr.c_str());       // 發布MQTT主題與訊息
    msgStr = "";
  }
}
