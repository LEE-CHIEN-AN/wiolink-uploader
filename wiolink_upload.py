import requests  # 匯入 requests 套件，用來發送 HTTP 請求
from supabase import create_client  # 從 supabase 套件匯入 create_client，用來建立 Supabase 連線
from datetime import datetime, timezone, timedelta  # 匯入時間相關模組
import psycopg2

# 連接本地 PostgreSQL
conn = psycopg2.connect(
    dbname="wiolink",
    user="postgres",      # 你自己的帳號
    password="",  # 替換成你的密碼
    host="localhost",
    port="5432"
)
conn.autocommit = True
cursor = conn.cursor()

def upload_to_postgres(data):
    try:
        cursor.execute(
            """
            INSERT INTO sensor_data (
                timestamp, sensor_name, humidity, light_intensity,
                motion_detected, celsius_degree, mag_approach, door_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                data["timestamp"], data["sensor_name"],
                data["humidity"], data["light_intensity"],
                data["motion_detected"], data["celsius_degree"],
                data["mag_approach"], data["door_status"]
            )
        )
        print("✅ 本地上傳成功：", data)
    except Exception as e:
        print("❌ 本地上傳失敗：", e)

# Supabase 設定
SUPABASE_URL = "https://orlmyfjhqcmlrbrlonbt.supabase.co"  # Supabase 專案網址
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ybG15ZmpocWNtbHJicmxvbmJ0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NTIwMjI1MCwiZXhwIjoyMDYwNzc4MjUwfQ.ThQYh9TgVpu9PEjuK-2Q2jaG_ewFzj4Osaq70RuH3rY"  # Supabase API 金鑰
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)  # 建立 Supabase 連線

# 所有板子的設定
DEVICES = [
    {
        "name": "wiolink2",  # 裝置名稱
        "token": "ad721465a96333625477b3690643f076"  # 裝置的存取token
    },
    {
        "name": "wiolink door",
        "token": "96c7644289c50aff68424a490845267f"
    }
]

BASE_URL = "https://cn.wio.seeed.io/v1/node"  # Wio Link API 基本網址

# API 路徑結構，對應各感測器的 API 路徑
SENSORS = {
    "humidity": "/GroveTempHumD2/humidity",  # 濕度感測器
    "light_intensity": "/GroveDigitalLightI2C0/lux",  # 光照強度感測器
    "motion_detected": "/GrovePIRMotionD1/approach",  # 移動偵測感測器
    "celsius_degree": "/GroveTempHumD2/temperature",  # 溫度感測器
    "mag_approach": "/GroveMagneticSwitchD0/approach"  # 磁簧開關感測器
}

# 抓取感測器資料
def get_sensor_data(device):
    # 建立一個結果字典，預設值為 None
    result = {
        "timestamp": (datetime.now(timezone(timedelta(hours=8)))).isoformat(),  # 取得當前台灣時間（UTC+8）
        "sensor_name": device["name"],  # 裝置名稱
        "humidity": None,
        "light_intensity": None,
        "motion_detected": None,
        "celsius_degree": None,
        "mag_approach": None,  # 磁簧開關狀態（門是否靠近磁鐵）
        "door_status": None  # 新增的門狀態描述（"closed" or "open"）
    }

    # 逐一抓取每個感測器的資料
    for key, path in SENSORS.items():
        url = f"{BASE_URL}{path}?access_token={device['token']}"  # 組合 API 請求網址
        try:
            r = requests.get(url)  # 設定 timeout 避免卡死
            if r.ok:  # 如果回應成功
                value = list(r.json().values())[0]  # 取得回傳 JSON 的第一個值
                result[key] = value  # 存入結果字典

                # 根據 mag_approach 的數值決定門的狀態描述
                if key == "mag_approach":
                    result["door_status"] = "closed" if value == 1 else "open"

        except Exception as e:
            print(f"[錯誤] 抓取 {device['name']} 的 {key} 失敗：", e)  # 例外處理，印出錯誤訊息

    return result  # 回傳感測器資料

# 上傳至 Supabase
def upload_to_supabase(data):
    try:
        supabase.table("wiolink").insert(data).execute()  # 將資料插入 wiolink 資料表
        print("✅ supabase上傳成功：", data)  # 上傳成功訊息
    except Exception as e:
        print("❌ supabase上傳失敗：", e)  # 上傳失敗訊息

# 執行所有板子
for device in DEVICES:
    data = get_sensor_data(device)  # 取得感測器資料
    upload_to_supabase(data)  # 上傳資料到 Supabase
    upload_to_postgres(data) # 上傳資料到本地 PostgreSQL

