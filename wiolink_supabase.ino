// Import WiFi and ESPSupabase Library
#include <ESP8266WiFi.h>
#include <ESPSupabase.h>

// Add you Wi-Fi credentials
const char* ssid = "jie";
const char* password = "0926197320";


// Supabase credentials
const char* supabaseUrl = "https://orlmyfjhqcmlrbrlonbt.supabase.co";
const char* supabaseKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ybG15ZmpocWNtbHJicmxvbmJ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMDIyNTAsImV4cCI6MjA2MDc3ODI1MH0.uDgPqDhmv-qLZnBYaTIuN4Y-z21foH39kefj_lHqCu0";

Supabase supabase;

void setup() {
  Serial.begin(115200);

  pinMode(15, OUTPUT); //wio link power
  digitalWrite(15, HIGH);

  // Connect to Wi-Fi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to Wi-Fi...");
  }
  Serial.println("Wi-Fi connected!");

  // Init Supabase
  supabase.begin(supabaseUrl, supabaseKey);

  // Add the table name here
  String tableName = "healthdata";
  // change the correct columns names you create in your table
  String jsonData = "{\"heartrate\": \"70\", \"bodytemp\": \"37\"}";

  // sending data to supabase
  int response = supabase.insert(tableName, jsonData, false);
  if (response == 200 || response == 201) {
    Serial.println("Data inserted successfully!");
  } else {
    Serial.print("Failed to insert data. HTTP response: ");
    Serial.println(response);
  }
}

void loop() {
}