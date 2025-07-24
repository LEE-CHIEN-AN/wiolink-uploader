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

//Setup for dust sensor ======================================
int dustpin = 14;
unsigned long duration;
unsigned long starttime;
unsigned long sampletime_ms = 30000;//sampe 30s ;
unsigned long lowpulseoccupancy = 0;
float ratio = 0;
float concentration = 0;

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
//IPAddress PGIP(192,168,50,35);  //connect rlab wifi's IP
IPAddress PGIP(10,188,40,129);  //connect my phone wifi's IP
//IPAddress PGIP(192,168,0,102);  //connect my room wifi's I 
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
const long interval = 60000 * 15 ; //1 min  = 60000       // time interval in milliseconds (eg 1000ms = 1 second)
//======================================

//setup for VOC and eCO2 Gas Sensor(SGP30)
#include <Arduino.h>
#include <EEPROM.h>
#include "sensirion_common.h"
#include "sgp30.h"
#define LOOP_TIME_INTERVAL_MS  1000
#define BASELINE_IS_STORED_FLAG  (0X55)
//#define ARRAY_TO_U32(a)  (a[0]<<24|a[1]<<16|a[2]<<8|a[3])    //MSB first  //Not suitable for 8-bit platform

void array_to_u32(u32* value, u8* array) {
    (*value) = (*value) | (u32)array[0] << 24;
    (*value) = (*value) | (u32)array[1] << 16;
    (*value) = (*value) | (u32)array[2] << 8;
    (*value) = (*value) | (u32)array[3];
}
void u32_to_array(u32 value, u8* array) {
    if (!array) {
        return;
    }
    array[0] = value >> 24;
    array[1] = value >> 16;
    array[2] = value >> 8;
    array[3] = value;
}
/*
    Reset baseline per hour,store it in EEPROM;
*/
void  store_baseline(void) {
    static u32 i = 0;
    u32 j = 0;
    u32 iaq_baseline = 0;
    u8 value_array[4] = {0};
    i++;
    Serial.println(i);
    if (i == 3600) {
        i = 0;
        if (sgp_get_iaq_baseline(&iaq_baseline) != STATUS_OK) {
            Serial.println("get baseline failed!");
        } else {
            Serial.println(iaq_baseline, HEX);
            Serial.println("get baseline");
            u32_to_array(iaq_baseline, value_array);
            for (j = 0; j < 4; j++) {
                EEPROM.write(j, value_array[j]);
                Serial.print(value_array[j]);
                Serial.println("...");
            }
            EEPROM.write(j, BASELINE_IS_STORED_FLAG);
        }
    }
    delay(LOOP_TIME_INTERVAL_MS);
}
/*  Read baseline from EEPROM and set it.If there is no value in EEPROM,retrun .
    Another situation: When the baseline record in EEPROM is older than seven days,Discard it and return!!

*/
void set_baseline(void) {
    u32 i = 0;
    u8 baseline[5] = {0};
    u32 baseline_value = 0;
    for (i = 0; i < 5; i++) {
        baseline[i] = EEPROM.read(i);
        Serial.print(baseline[i], HEX);
        Serial.print("..");
    }
    Serial.println("!!!");
    if (baseline[4] != BASELINE_IS_STORED_FLAG) {
        Serial.println("There is no baseline value in EEPROM");
        return;
    }
    /*
        if(baseline record in EEPROM is older than seven days)
        {
        return;
        }
    */
    array_to_u32(&baseline_value, baseline);
    sgp_set_iaq_baseline(baseline_value);
    Serial.println(baseline_value, HEX);
}

void setup() {
  pinMode(15, OUTPUT); //wio link power
  digitalWrite(15, HIGH);

  Serial.begin(115200);
  //For DHT sensor
  dht.begin();


  //For dust
  pinMode(dustpin,INPUT);
  starttime = millis();//get the current time;

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

  Serial.println("Timer set to 60 seconds (timerDelay variable), it will take 60 seconds before publishing the first reading.");

  // Init Supabase
  supabase.begin(supabaseUrl, supabaseKey);

  s16 err;
  u16 scaled_ethanol_signal, scaled_h2_signal;
  //Serial.begin(115200);
  Serial.println("serial start!!");

  /*For wio link!*/
  #if defined(ESP8266)
  pinMode(15, OUTPUT);
  digitalWrite(15, 1);
  Serial.println("Set wio link power!");
  delay(500);
  #endif

  /*  Init module,Reset all baseline,The initialization takes up to around 15 seconds, during which
      all APIs measuring IAQ(Indoor air quality ) output will not change.Default value is 400(ppm) for co2,0(ppb) for tvoc*/
  while (sgp_probe() != STATUS_OK) {
      Serial.println("SGP failed");
      while (1);
  }
  /*Read H2 and Ethanol signal in the way of blocking*/
  err = sgp_measure_signals_blocking_read(&scaled_ethanol_signal,
                                          &scaled_h2_signal);
  if (err == STATUS_OK) {
      Serial.println("get ram signal!");
  } else {
      Serial.println("error reading signals");
  }
  // err = sgp_iaq_init();
  set_baseline();
  //

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

      //read dust---------------------------
      duration = pulseIn(dustpin, LOW);
      lowpulseoccupancy = lowpulseoccupancy+duration;

      if ((millis()-starttime) > sampletime_ms)//if the sampel time == 30s
      {
          ratio = lowpulseoccupancy/(sampletime_ms*10.0);  // Integer percentage 0=>100
          concentration = 1.1*pow(ratio,3)-3.8*pow(ratio,2)+520*ratio+0.62; // using spec sheet curve
          dust = concentration;
          Serial.print(lowpulseoccupancy);
          Serial.print(",");
          Serial.print(ratio);
          Serial.print(",");
          Serial.println(concentration);
          lowpulseoccupancy = 0;
          starttime = millis();
      }

      //Send data to PostgreSQL
      //sprintf(inbuf, "insert into sensor_arduino (name,temp,humidity,motion_detected,light_intensity) values('wiolink_Arduino',%.2f,%.2f,%d,%d)", t, h,motion,lux);      
      // ✅ PostgreSQL：如果已連線才執行
      if (pg_status == 2) {
        snprintf(inbuf, sizeof(inbuf),
          "insert into sensor_arduino (name,temp,humidity,motion_detected,light_intensity,dust) "
          "values('wiolink_dust',%.2f,%d,%d,%d,%.2f)",
          t, h, motion, lux, dust); // ← 修正後加入 touch
        Serial.print("Generated SQL: ");
        Serial.println(inbuf);
      }
      //read dust---------------------------
      
      //read VOC and CO2 sensor
      // VOC and CO2 sensor
      s16 err = 0;
      u16 tvoc_ppb, co2_eq_ppm;
      err = sgp_measure_iaq_blocking_read(&tvoc_ppb, &co2_eq_ppm);
      if (err == STATUS_OK) {
          Serial.print("tVOC  Concentration:");
          Serial.print(tvoc_ppb);
          Serial.println("ppb");

          Serial.print("CO2eq Concentration:");
          Serial.print(co2_eq_ppm);
          Serial.println("ppm");
      } else {
          Serial.println("error reading IAQ values\n");
      }
      store_baseline();

      // Supabase insert
      String jsonData = String("{") +
      "\"name\": \"wiolink_dust\"," +
      "\"humidity\": " + String((int)h) + "," +
      "\"light_intensity\": " + String(lux) + "," +
      "\"motion_detected\": " + String(motion) + "," +
      "\"celsius_degree\": " + String(t, 2) + "," +
      "\"mag_approach\": "+ String(mag_approach) +"," +
      "\"dust\": " + String(dust, 2) + ","+
      "\"touch\": " + String(touch) + "," +
      "\"tVOC\": "+ String(tvoc_ppb) + "," + 
      "\"CO2eq\": "+ String(co2_eq_ppm) +
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
