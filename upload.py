import requests
from supabase import create_client
from datetime import datetime, timezone, timedelta
import os

# === Supabase 設定（從 GitHub Secrets 環境變數取得） ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === 所有 Wio Link 板子的 token 與命名設定 ===
DEVICES = [
    {
        "name": "wiolink window",  # 第一塊板子
        "token": "ad721465a96333625477b3690643f076"
    },
    {
        "name": "wiolink door",  # 第二塊板子
        "token": "96c7644289c50aff68424a490845267f"
    },
    {
        "name": "wiolink wall",
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
        "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),  # 台灣時間
        "sensor_name": device["name"],
        "humidity": None,
        "light_intensity": None,
        "motion_detected": None,  # 動作偵測感測器（目前未使用）
        "dust": None,
        "celsius_degree": None,
        "mag_approach": None,  # 磁簧開關狀態（門是否靠近磁鐵）
        "door_status": None,  # 新增的門狀態描述（"closed" or "open"）
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

# === 將單筆感測資料上傳至 Supabase ===
def upload_to_supabase(data):
    try:
        supabase.table("wiolink").insert(data).execute()
        print("✅ 上傳成功：", data)
    except Exception as e:
        print("❌ 上傳失敗：", e)

# === 主程式：針對所有板子執行抓取與上傳 ===
for device in DEVICES:
    data = get_sensor_data(device)
    upload_to_supabase(data)
