import os
import requests
import psycopg2
from datetime import datetime, timedelta, timezone
from supabase import create_client

# === PostgreSQL 連線設定 ===
conn = psycopg2.connect(
    dbname="wiolink",
    user="postgres",
    password="Anjapan12",
    host="localhost",
    port="5432"
)
conn.autocommit = True
cursor = conn.cursor()

# === Supabase 設定 ===
SUPABASE_URL = "https://orlmyfjhqcmlrbrlonbt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ybG15ZmpocWNtbHJicmxvbmJ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMDIyNTAsImV4cCI6MjA2MDc3ODI1MH0.uDgPqDhmv-qLZnBYaTIuN4Y-z21foH39kefj_lHqCu0"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === Wio Link 裝置設定 ===
DEVICES = [
    {"name": "wiolink window", "token": "ad721465a96333625477b3690643f076"},
    {"name": "wiolink door", "token": "96c7644289c50aff68424a490845267f"},
    {"name": "wiolink wall", "token": "1b10e1172b455a426b53af996442c0ce"}
]
BASE_URL = "https://cn.wio.seeed.io/v1/node"
SENSORS = {
    "humidity": "/GroveTempHumD2/humidity",
    "light_intensity": "/GroveDigitalLightI2C0/lux",
    "motion_detected": "/GrovePIRMotionD1/approach",
    "dust": "/GroveDustD0/dust",
    "celsius_degree": "/GroveTempHumD2/temperature",
    "mag_approach": "/GroveMagneticSwitchD0/approach"
}

# === ThingSpeak API 設定 ===
READ_API_KEY = "797QS4ZPIJYT4U7W"
CHANNEL_ID = "3026055"
FIELD_URL = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"

# === 上傳到 PostgreSQL 的工具 ===
def upload_to_postgres(data):
    try:
        cursor.execute("""
            INSERT INTO sensor_data (
                name, humidity, light_intensity,
                motion_detected, celsius_degree, mag_approach, dust, touch
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get("name"),
            data.get("humidity"),
            data.get("light_intensity"),
            data.get("motion_detected"),
            data.get("celsius_degree"),
            data.get("mag_approach"),
            data.get("dust"),
            data.get("touch")
        ))
        print("✅ 本地上傳成功：", data)
    except Exception as e:
        print("❌ 本地上傳失敗：", e)

# === 上傳到 Supabase 的工具 ===
def upload_to_supabase(data):
    try:
        supabase.table("wiolink").insert(data).execute()
        print("✅ Supabase 上傳成功：", data)
    except Exception as e:
        print("❌ Supabase 上傳失敗：", e)

# === 從單一 Wio Link 板子抓資料 ===
def get_sensor_data(device):
    result = {
        "name": device["name"],
        "humidity": None,
        "light_intensity": None,
        "motion_detected": None,
        "dust": None,
        "celsius_degree": None,
        "mag_approach": None
    }
    for key, path in SENSORS.items():
        url = f"{BASE_URL}{path}?access_token={device['token']}"
        try:
            r = requests.get(url, timeout=5)
            if r.ok:
                value = list(r.json().values())[0]
                result[key] = value
        except Exception as e:
            print(f"[錯誤] 抓取 {device['name']} 的 {key} 失敗：", e)
    return result

# === 抓取 ThingSpeak 最新一筆資料 ===
def fetch_latest_thingspeak():
    try:
        response = requests.get(FIELD_URL, params={"api_key": READ_API_KEY, "results": 1}, timeout=5)
        response.raise_for_status()

        feed = response.json()["feeds"][0]
        data = {
            "name": "407_aircondition",
            "humidity": int(feed["field2"]),
            "light_intensity": int(feed["field3"]),
            "motion_detected": None,
            "celsius_degree": float(feed["field1"]),
            "mag_approach": None,
            "dust": None,
            "touch": int(feed["field4"])
        }

        upload_to_postgres(data)
        upload_to_supabase(data)

    except Exception as e:
        print("❌ ThingSpeak 最新資料抓取失敗：", e)

# === 補抓過去 5 分鐘內 touch == 1 的資料並寫入 PostgreSQL ===
def fetch_touch_events():
    try:
        response = requests.get(FIELD_URL, params={"api_key": READ_API_KEY, "results": 100}, timeout=5)
        response.raise_for_status()
        feeds = response.json()["feeds"]

        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=5)
        count = 0

        for feed in feeds:
            try:
                created_at = datetime.strptime(feed["created_at"], "%Y-%m-%dT%H:%M:%SZ")
                if created_at < cutoff:
                    continue
                if int(feed["field4"]) == 1:
                    data = {
                        "name": "407_aircondition",
                        "humidity": int(feed["field2"]),
                        "light_intensity": int(feed["field3"]),
                        "motion_detected": None,
                        "celsius_degree": float(feed["field1"]),
                        "mag_approach": None,
                        "dust": None,
                        "touch": 1
                    }
                    upload_to_postgres(data)
                    count += 1
            except:
                continue

        print(f"✅ 共補上傳 {count} 筆 touch=1 的資料")
    except Exception as e:
        print("❌ 抓取 ThingSpeak touch=1 資料失敗：", e)

# === 主程式執行區 ===
if __name__ == "__main__":
    # 1. 上傳所有 Wio Link 板子資料
    for device in DEVICES:
        data = get_sensor_data(device)
        upload_to_supabase(data)
        upload_to_postgres(data)

    # 2. 上傳最新一筆 407_aircondition
    fetch_latest_thingspeak()

    # 3. 補上傳 touch=1 資料（過去 5 分鐘內）
    fetch_touch_events()
