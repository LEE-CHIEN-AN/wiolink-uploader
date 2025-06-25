import requests
from supabase import create_client
from datetime import datetime, timezone, timedelta
import os

# Supabase 設定（從 GitHub Secrets 讀取）
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Wio Link API 設定
ACCESS_TOKEN = os.getenv("WIO_TOKEN")
BASE_URL = "https://cn.wio.seeed.io/v1/node"  # 建議使用 us 伺服器更穩定

# API 端點
ENDPOINTS = {
    "humidity": f"{BASE_URL}/GroveTempHumD0/humidity?access_token={ACCESS_TOKEN}",
    "light_intensity": f"{BASE_URL}/GroveDigitalLightI2C0/lux?access_token={ACCESS_TOKEN}",
    "motion_detected": f"{BASE_URL}/GrovePIRMotionD1/approach?access_token={ACCESS_TOKEN}",
    "celsius_degree": f"{BASE_URL}/GroveTempHumD0/temperature?access_token={ACCESS_TOKEN}",
}

# 抓取感測器資料
def get_sensor_data():
    result = {
        "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),  # 台灣時間
        "sensor_name": "wiolink2",
        "humidity": None,
        "light_intensity": None,
        "motion_detected": None,
        "celsius_degree": None
    }

    try:
        r = requests.get(ENDPOINTS["humidity"])
        if r.ok:
            result["humidity"] = r.json().get("humidity")
    except:
        pass

    try:
        r = requests.get(ENDPOINTS["light_intensity"])
        if r.ok:
            result["light_intensity"] = r.json().get("lux")
    except:
        pass

    try:
        r = requests.get(ENDPOINTS["motion_detected"])
        if r.ok:
            result["motion_detected"] = r.json().get("approach")
    except:
        pass

    try:
        r = requests.get(ENDPOINTS["celsius_degree"])
        if r.ok:
            result["celsius_degree"] = r.json().get("celsius_degree")
    except:
        pass

    return result

# 上傳至 Supabase
def upload_to_supabase(data):
    supabase.table("wiolink").insert(data).execute()
    print("✅ 上傳成功：", data)

if __name__ == "__main__":
    data = get_sensor_data()
    upload_to_supabase(data)
