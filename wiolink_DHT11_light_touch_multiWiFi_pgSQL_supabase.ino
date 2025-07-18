/*
  by Yaser Ali Husen

  This code for sending data temperature and humidity to postresql database
  code based on pgconsole in SimplePgSQL example code.

*/
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

//Setup for PIR======================================
//#define PIR_MOTION_SENSOR 13 //wio link D2 = 13

//Setup for touch sensor ======================================
const int TouchPin= 13 ;


//定義感測器變數與初始化邏輯
// current temperature & humidity, updated in loop()
float t = -1.0;
int h = -1;
int lux = -1;
int motion = -1;
int mag_approach = -1;
float dust = -1.0;
int touch = -1;
//Setup for DHT======================================

//Setup for WIFI=====================================
const char* ssid = "CAECE611 2G";
const char* pass = "116eceac";
WiFiClient client;

//Setup for multiWiFi=====================================
ESP8266WiFiMulti wifiMulti; // 建立一個ESP8266WiFiMulti類別的實體變數叫'wifiMulti'

//Setup connection and Database=====================
//IPAddress PGIP(192,168,0,45);   //connect 611 wifi's IP  // your PostgreSQL server IP
IPAddress PGIP(192,168,50,35);  //connect rlab wifi's IP
//IPAddress PGIP(10,188,40,129);  //connect my phone wifi's IP
const char user[] = "postgres";       // your database user
const char password[] = "Anjapan12";   // your database password
const char dbname[] = "postgres";         // your database name

// Supabase credentials==============================
const char* supabaseUrl = "https://orlmyfjhqcmlrbrlonbt.supabase.co";
const char* supabaseKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ybG15ZmpocWNtbHJicmxvbmJ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMDIyNTAsImV4cCI6MjA2MDc3ODI1MH0.uDgPqDhmv-qLZnBYaTIuN4Y-z21foH39kefj_lHqCu0";
Supabase supabase;

/*
// 靜態 IP 設定（這是給 ESP8266 用的）
IPAddress local_IP(10, 188, 40, 192);      // 你想讓 Wio Link 使用的固定 IP
IPAddress gateway(10, 188, 40, 1);        // 熱點的 IP （通常是手機或路由器的）
IPAddress subnet(255, 255, 255, 0);       // 子網路遮罩，通常是這個值
*/
char buffer[1024];
PGconnection conn(&client, 0, 1024, buffer);
char inbuf[128];
int pg_status = 0;
//Setup connection and Database=====================

//millis================================
//Set every 60 sec read DHT
unsigned long previousMillis = 0;  // variable to store the last time the task was run
const long interval = 60000 ; //1 min  = 60000       // time interval in milliseconds (eg 1000ms = 1 second)
//======================================

void setup() {
  pinMode(15, OUTPUT); //wio link power
  digitalWrite(15, HIGH);

  Serial.begin(9600);
  //For DHT sensor
  dht.begin();

  //For PIR
  //pinMode(PIR_MOTION_SENSOR, INPUT);

  //For light
  Wire.begin();
  TSL2561.init();

  //For touch
  pinMode(TouchPin, INPUT);
  
  //For WiFi
  //WiFi.config(local_IP, gateway, subnet); // 靜態 IP 設定 一定要在 WiFi.begin() 之前
  wifiMulti.addAP("CAECE611 2G", "116eceac");
  wifiMulti.addAP("RLab_2.4G", "ntucerlab");
  wifiMulti.addAP("jie", "0926197320");

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

      /*
      //read PIR----------------------------
      motion = digitalRead(PIR_MOTION_SENSOR);
      if(digitalRead(PIR_MOTION_SENSOR))
        Serial.println("Hi,people is coming");
      else
        Serial.println("Watching");
      //read PIR -----------------------
      */

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

      //Send data to PostgreSQL
      // Menggunakan sprintf untuk memformat string dengan nilai numerik
      // dan menyimpannya dalam inbuf
      //sprintf(inbuf, "insert into sensor_arduino (name,temp,humidity,motion_detected,light_intensity) values('wiolink_Arduino',%.2f,%.2f,%d,%d)", t, h,motion,lux);      
      // ✅ PostgreSQL：如果已連線才執行
      if (pg_status == 2) {
        snprintf(inbuf, sizeof(inbuf),
          "insert into sensor_arduino (name,temp,humidity,motion_detected,light_intensity,touch) "
          "values('wiolink_touch',%.2f,%d,%d,%d,%d)",
          t, h, motion, lux,touch); // ← 修正後加入 touch
        Serial.print("Generated SQL: ");
        Serial.println(inbuf);
      }
      
      
      // Supabase insert
      String jsonData = String("{") +
      "\"name\": \"wiolink_touch\"," +
      "\"humidity\": " + String((int)h) + "," +
      "\"light_intensity\": " + String(lux) + "," +
      "\"motion_detected\": " + String(motion) + "," +
      "\"celsius_degree\": " + String(t, 2) + "," +
      "\"mag_approach\": "+ String(mag_approach) +"," +
      "\"dust\": " + String(dust, 2) + ","+
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
    else { // wifi 自動重連
      Serial.println("WiFi Disconnected");
      //WiFi.begin(ssid, pass);
      wifiMulti.run();
      Serial.println("WiFi disconnected, trying to reconnect...");
      
    }
    
  }
}
