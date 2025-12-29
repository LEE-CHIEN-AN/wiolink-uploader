import requests
from supabase import create_client
from datetime import datetime, timezone, timedelta
import os

# === Supabase 設定（從 GitHub Secrets 環境變數取得） ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === 將單筆感測資料上傳至 Supabase ===
def upload_to_supabase(data):
    try:
        supabase.table("wiolink").insert(data).execute()
        print("✅ 上傳成功：", data)
    except Exception as e:
        print("❌ 上傳失敗：", e)
        
# === 所有 Wio Link 板子的 token 與命名設定 ===
DEVICES = [
    {
        "name": "604_door",  # 第二塊板子
        "token": "96c7644289c50aff68424a490845267f"
    },
    {
        "name": "604_wall",
        "token": "1b10e1172b455a426b53af996442c0ce"
    }
]

# === Wio API 共用前綴 URL ===
BASE_URL = "https://cn.wio.seeed.io/v1/node"

# === 各感測器 API 路徑定義 ===
SENSORS = {
    "light_intensity": "/GroveDigitalLightI2C0/lux",  # 光照強度感測器
    "motion_detected": "/GrovePIRMotionD1/approach",  # 移動偵測感測器
    "dust": "/GroveDustD0/dust",  # 灰塵感測器
    "celsius_degree": "/GroveTempHumD2/temperature",  # 溫度感測器
    "humidity": "/GroveTempHumD2/humidity",  # 濕度感測器
    "mag_approach": "/GroveMagneticSwitchD0/approach"  # 磁簧開關感測器
}

# === 從單一板子抓取所有感測器資料 ===
def get_sensor_data(device):
    result = {
        "name": device["name"],
        "humidity": None,
        "light_intensity": None,
        "motion_detected": None,  # 動作偵測感測器（目前未使用）
        "dust": None,
        "celsius_degree": None,
        "mag_approach": None,  # 磁簧開關狀態（門是否靠近磁鐵）
    }

    for key, path in SENSORS.items():
        url = f"{BASE_URL}{path}?access_token={device['token']}"
        try:
            r = requests.get(url)  # 加上 timeout 避免卡住
            if r.ok:
                # 回傳 JSON 的值都只有一個，直接取第一個 value
                value = list(r.json().values())[0]
                result[key] = value
                
                # 根據 mag_approach 的數值決定門的狀態描述
                if key == "mag_approach":
                    result["door_status"] = "closed" if value == 1 else "open"

        except Exception as e:
            print(f"[錯誤] 抓取 {device['name']} 的 {key} 失敗：", e)

    return result

def get_thingspeak_604center_data():
    CHANNEL_ID = "3022873"
    READ_API_KEY = "O1JMFSHUMRCTBQHL"
    FIELD_URL = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
    params = {"api_key": READ_API_KEY, "results": 1}

    try:
        r = requests.get(FIELD_URL, params=params, timeout=5)
        r.raise_for_status()
        feed = r.json()["feeds"][0]

        return {
            "name": "604_center",
            "humidity": int(feed["field2"]),
            "light_intensity":  None,
            "motion_detected": None,
            "celsius_degree": float(feed["field1"]),
            "mag_approach": None,
            "dust": None,
            "touch": None
        }

    except Exception as e:
        print("❌ 無法取得 ThingSpeak 資料：", e)
        return None

def get_thingspeak_604window_data():
    CHANNEL_ID = "3027253"
    READ_API_KEY = "G9XE5ZK8PCDHADKC"
    FIELD_URL = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
    params = {"api_key": READ_API_KEY, "results": 1}

    try:
        r = requests.get(FIELD_URL, params=params, timeout=5)
        r.raise_for_status()
        feed = r.json()["feeds"][0]

        return {
            "name": "604_window",
            "humidity": int(feed["field2"]),
            "light_intensity":  None,
            "motion_detected": None,
            "celsius_degree": float(feed["field1"]),
            "mag_approach":None,
            "dust": None,
            "touch": None,
            "pm1_0_atm": int(feed["field4"]),
            "pm2_5_atm": int(feed["field5"]),
            "pm10_atm": int(feed["field6"])
        }

    except Exception as e:
        print("❌ 無法取得 ThingSpeak 資料：", e)
        return None


# === 抓取 ThingSpeak 最新一筆資料 ===
def get_thingspeak_604outdoor_data():
    READ_API_KEY = "GZW95SILPGDZ8LZB"
    CHANNEL_ID = "3031639"
    FIELD_URL = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
    try:
        response = requests.get(FIELD_URL, params={"api_key": READ_API_KEY, "results": 1}, timeout=5)
        response.raise_for_status()

        feed = response.json()["feeds"][0]
        data = {
            "name": "604_outdoor",
            "humidity": int(float(feed["field2"])) if feed["field2"] is not None else None,
            "light_intensity": None,
            "celsius_degree": float(feed["field1"]) if feed["field1"] is not None else None,
            "mag_approach": None,
            "touch": None,
            "pm1_0_atm": int(feed["field3"]) if feed["field3"] is not None else None,
            "pm2_5_atm": int(feed["field4"]) if feed["field4"] is not None else None,
            "pm10_atm": int(feed["field5"]) if feed["field5"] is not None else None,
        }
        return data                   # ★ 一定要 return

    except Exception as e:
        print("❌ ThingSpeak 最新資料抓取失敗：", e)
        return None                   # ★ 失敗時回傳 None



# === 主程式 ===
if __name__ == "__main__":
    # 上傳所有 Wio Link 板子
    for device in DEVICES:
        data = get_sensor_data(device)
        upload_to_supabase(data)

    # 上傳 ThingSpeak 604 center 資料
    vlabcenter_data = get_thingspeak_604center_data()
    if vlabcenter_data:
        upload_to_supabase(vlabcenter_data)

    # 上傳 ThingSpeak 604 window 資料
    vlabwindow_data = get_thingspeak_604window_data()
    if vlabwindow_data:               # ★ 用正確的變數名判斷
        upload_to_supabase(vlabwindow_data)

    # 上傳 ThingSpeak 604 outdoor 資料
    #vlaboutdoor_data =     #vlaboutdoor_data = get_thin
    #    #if vlaboutdoor_
        #        #upload_to_supabase(vlaboutd
