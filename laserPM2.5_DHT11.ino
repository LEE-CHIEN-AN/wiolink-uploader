#include <ESP8266WiFi.h>
#include <ESP8266WiFiMulti.h>
#include <WiFiClient.h>
#include <SimplePgSQL.h>
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

//setup for Laser PM2.5 Sensor ===========================
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

HM330XErrorCode print_result(const char* str, uint16_t value) {
    if (NULL == str) {
        return ERROR_PARAM;
    }
    SERIAL_OUTPUT.print(str);
    SERIAL_OUTPUT.println(value);
    return NO_ERROR;
}

/*parse buf with 29 uint8_t-data*/
HM330XErrorCode parse_result(uint8_t* data) {
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

HM330XErrorCode parse_result_value(uint8_t* data) {
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
//Setup for Laser PM2.5 ===========================

//定義感測器變數與初始化邏輯
// current temperature & humidity, updated in loop()
float t = -1.0;
int h = -1;
int lux = -1;
int motion = -1;
int mag_approach = -1;
float dust = -1.0;
int touch = -1;
int pm1_0_atm = -1;
int pm2_5_atm = -1;
int pm10_atm = -1;


//Setup for WIFI=====================================
const char* ssid = "CAECE611 2G";
const char* pass = "116eceac";
WiFiClient client;

//Setup for multiWiFi=====================================
ESP8266WiFiMulti wifiMulti; // 建立一個ESP8266WiFiMulti類別的實體變數叫'wifiMulti'

//Setup connection and Database=====================
//IPAddress PGIP(192,168,0,45);   //connect 611 wifi's IP  // your PostgreSQL server IP
//IPAddress PGIP(192,168,50,35);  //connect rlab wifi's IP
//IPAddress PGIP(10,188,40,129);  //connect my phone wifi's IP
//IPAddress PGIP(192,168,0,102);  //connect my room wifi's I 
IPAddress PGIP;
const char user[] = "postgres";       // your database user
const char password[] = "Anjapan12";   // your database password
const char dbname[] = "postgres";         // your database name

// Supabase credentials==============================
const char* supabaseUrl = "https://orlmyfjhqcmlrbrlonbt.supabase.co";
const char* supabaseKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ybG15ZmpocWNtbHJicmxvbmJ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMDIyNTAsImV4cCI6MjA2MDc3ODI1MH0.uDgPqDhmv-qLZnBYaTIuN4Y-z21foH39kefj_lHqCu0";
Supabase supabase;


char buffer[1024];
PGconnection conn(&client, 0, 1024, buffer);
char inbuf[128];
int pg_status = 0;
//Setup connection and Database=====================

//millis================================
//Set every 60 sec read DHT
unsigned long previousMillis = 0;  // variable to store the last time the task was run
const long interval = 60000*15 ; //1 min  = 60000       // time interval in milliseconds (eg 1000ms = 1 second)
//======================================

void setup() {
  pinMode(15, OUTPUT); //wio link power
  digitalWrite(15, HIGH);

  Serial.begin(9600);
  //For DHT sensor
  dht.begin();
  
  //For Laser PM2.5
  SERIAL_OUTPUT.println("Serial start");
  if (sensor.init()) {
      SERIAL_OUTPUT.println("HM330X init failed!!");
      //while (1);
  }

  //For WiFi
  //WiFi.config(local_IP, gateway, subnet); // 靜態 IP 設定 一定要在 WiFi.begin() 之前
  wifiMulti.addAP("CAECE611 2G", "116eceac");
  wifiMulti.addAP("RLab_2.4G", "ntucerlab");
  wifiMulti.addAP("jie", "0926197320");
  wifiMulti.addAP("i_want_to_go_home", "33438542");

  Serial.println("Connecting");
  while (wifiMulti.run() != WL_CONNECTED) {//mulitWiFi
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.print("Connected to ");
  Serial.println(WiFi.SSID());              // 告訴我們是哪一組ssid連線到
  Serial.print("IP address:");
  Serial.println(WiFi.localIP());           // 送出ESP8266連線到IP多少

  // ✅ 在 WiFi 連線成功之後才呼叫 WiFi.SSID()
  String currentSSID = WiFi.SSID();
  if (currentSSID == "CAECE611 2G") {
    PGIP = IPAddress(192, 168, 0, 45);
  } else if (currentSSID == "RLab_2.4G") {
    PGIP = IPAddress(192, 168, 50, 35);
  } else if (currentSSID == "jie") {
    PGIP = IPAddress(10, 138, 177, 129);
  } else if (currentSSID == "i_want_to_go_home") {
    PGIP = IPAddress(192, 168, 0, 102);
  } else {
    Serial.println("Unknown WiFi. Using default PGIP.");
    PGIP = IPAddress(192, 168, 0, 45);
  }
  Serial.print("Selected PGIP: ");
  Serial.println(PGIP);


  Serial.println("Timer set to 60 seconds (timerDelay variable), it will take 60 seconds before publishing the first reading.");

  // Init Supabase
  supabase.begin(supabaseUrl, supabaseKey);

  

}

void doPg(void)
{
  char *msg;
  int rc;
  if (!pg_status) {
    conn.setDbLogin(PGIP,
                    user,
                    password,
                    dbname,
                    "utf8");
    pg_status = 1;
    return;
  }

  /*if (pg_status == -1) { //database 自動重連
    delay(1000);  // 等待一下，避免爆炸重連
    Serial.println("Trying to reconnect to database...");
    pg_status = 0; // 將狀態重設，讓 doPg() 下一輪重新 setDbLogin()
  }*/

  if (pg_status == 1) {
    rc = conn.status();
    if (rc == CONNECTION_BAD || rc == CONNECTION_NEEDED) {
      char *c = conn.getMessage();
      if (c) Serial.println(c);
      pg_status = -1;
    }
    else if (rc == CONNECTION_OK) {
      pg_status = 2;
      Serial.println("Starting query");
    }
    return;
  }
  
  if (pg_status == 2 && strlen(inbuf) > 0) {
    if (conn.status() != CONNECTION_OK) {
      Serial.println("PG not connected. Skipping execute.");
      pg_status = -1;
      return;
    }

    if (conn.execute(inbuf)) goto error;
    Serial.println("Working...");
    pg_status = 3;
    memset(inbuf, 0, sizeof(inbuf));
  }
  
  if (pg_status == 3) {
    rc = conn.getData();
    int i;
    if (rc < 0) goto error;
    if (!rc) return;
    if (rc & PG_RSTAT_HAVE_COLUMNS) {
      for (i = 0; i < conn.nfields(); i++) {
        if (i) Serial.print(" | ");
        Serial.print(conn.getColumn(i));
      }
      Serial.println("\n==========");
    }
    else if (rc & PG_RSTAT_HAVE_ROW) {
      for (i = 0; i < conn.nfields(); i++) {
        if (i) Serial.print(" | ");
        msg = conn.getValue(i);
        if (!msg) msg = (char *)"NULL";
        Serial.print(msg);
      }
      Serial.println();
    }
    else if (rc & PG_RSTAT_HAVE_SUMMARY) {
      Serial.print("Rows affected: ");
      Serial.println(conn.ntuples());
    }
    else if (rc & PG_RSTAT_HAVE_MESSAGE) {
      msg = conn.getMessage();
      if (msg) Serial.println(msg);
    }

    if (rc & PG_RSTAT_READY) {
      pg_status = 2;
      Serial.println("Waiting query");
    }

  }
  return;
error:
  msg = conn.getMessage();
  if (msg) Serial.println(msg);
  else Serial.println("UNKNOWN ERROR");
  if (conn.status() == CONNECTION_BAD) {
    Serial.println("Connection is bad");
    pg_status = -1;
  }
}

void loop() {
  delay(50);

  doPg();
  if (pg_status == -1) { //database 自動重連
    delay(1000);  // 等待一下，避免爆炸重連
    Serial.println("Trying to reconnect to database...");
    pg_status = 0; // 將狀態重設，讓 doPg() 下一輪重新 setDbLogin()
  }

  unsigned long currentMillis = millis();  // mendapatkan waktu sekarang
  // Checks whether it is time to run the task
  if (currentMillis - previousMillis >= interval) {
    // Save the last time the task was run
    previousMillis = currentMillis;
    if (WiFi.status() == WL_CONNECTED) {
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

      //read Laser PM2.5 -----------------------------
      if (sensor.read_sensor_value(buf, 29)) {
          SERIAL_OUTPUT.println("HM330X read result failed!!");
      }
      parse_result_value(buf);
      parse_result(buf);
      SERIAL_OUTPUT.println("");
      pm1_0_atm = ((uint16_t)buf[10] << 8) | buf[11];
      pm2_5_atm = ((uint16_t)buf[12] << 8) | buf[13];
      pm10_atm  = ((uint16_t)buf[14] << 8) | buf[15];
      Serial.print("PM1.0_atm: "); Serial.println(pm1_0_atm);
      Serial.print("PM2.5_atm: "); Serial.println(pm2_5_atm);
      Serial.print("PM10_atm: "); Serial.println(pm10_atm);
      //read Laser PM2.5 -----------------------------

      //Send data to PostgreSQL
      // Menggunakan sprintf untuk memformat string dengan nilai numerik
      // dan menyimpannya dalam inbuf
      //sprintf(inbuf, "insert into sensor_arduino (name,temp,humidity,motion_detected,light_intensity) values('wiolink_Arduino',%.2f,%.2f,%d,%d)", t, h,motion,lux);      
      // ✅ PostgreSQL：如果已連線才執行
      if (pg_status == 2) {
        snprintf(inbuf, sizeof(inbuf),
          "insert into sensor_arduino (name,temp,humidity,pm1_0_atm,pm2_5_atm,pm10_atm) "
          "values('pm2.5',%.2f,%d,%d,%d,%d)",
          t, h, pm1_0_atm, pm2_5_atm, pm10_atm); // ← 修正後加入 touch
        Serial.print("Generated SQL: ");
        Serial.println(inbuf);
      }

      
      // Supabase insert
      String jsonData = String("{") +
      "\"name\": \"pm2.5\"," +
      "\"humidity\": " + String((int)h) + "," +
      "\"celsius_degree\": " + String(t, 2) + "," +
      "\"pm1_0_atm\": " + String(pm1_0_atm) + "," +
      "\"pm2_5_atm\": " + String(pm2_5_atm) + "," +
      "\"pm10_atm\": " + String(pm10_atm) +
      "}";

      int res = supabase.insert("wiolink", jsonData, false);
      if (res == 200 || res == 201) {
        Serial.println("Supabase: Data inserted successfully!");
      } else {
        Serial.print("Supabase: Failed to insert data. HTTP: ");
        Serial.println(res);
      }
    }
    else { // wifi 自動重連
      Serial.println("WiFi Disconnected");
      //WiFi.begin(ssid, pass);
      wifiMulti.run();
      Serial.println("WiFi disconnected, trying to reconnect...");
      
    }
    
  }
}
