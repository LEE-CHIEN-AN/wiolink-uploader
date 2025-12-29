import os
import requests
import psycopg2
from datetime import datetime, timedelta, timezone
from supabase import create_client

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
    TZ_TAIPEI = ZoneInfo("Asia/Taipei")
except Exception:
    TZ_TAIPEI = timezone(timedelta(hours=8))


# =========================
# 本地 PostgreSQL 連線設定
# =========================
conn = psycopg2.connect(
    dbname=os.getenv("PG_DBNAME", "wiolink"),
    user=os.getenv("PG_USER", "postgres"),
    password=os.getenv("PG_PASSWORD", ""), #自己輸入密碼
    host=os.getenv("PG_HOST", "localhost"),
    port=os.getenv("PG_PORT", "5432"),
)
conn.autocommit = True
cursor = conn.cursor()

# 你本地寬表名稱（依你原本程式：sensor_data）
LOCAL_WIDE_TABLE = os.getenv("PG_WIDE_TABLE", "sensor_data")

# =========================
# Supabase 設定（建議用環境變數）
# =========================
SUPABASE_URL = ""
SUPABASE_KEY = ""
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL / SUPABASE_KEY env vars")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# 名稱映射（你要求的）
# =========================
def map_device_name(name: str) -> str:
    n = (name or "").strip()
    if n == "wiolink door":
        return "604_door"
    if n == "wiolink wall":
        return "604_wall"
    if n == "wiolink window":
        return "604_window"
    return n

# =========================
# 型別推斷（Supabase 新 schema 用）
# =========================
EXPLICIT_TYPES = {
    "door_status": "text",
    "motion_detected": "bool",
    "mag_approach": "bool",
    "touch": "bool",
}

def infer_value_type(metric_key: str) -> str:
    return EXPLICIT_TYPES.get(metric_key, "numeric")

def coerce_value(metric_key: str, value):
    t = infer_value_type(metric_key)
    if value is None:
        return None

    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(int(value))
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("1", "true", "t", "yes", "y", "on"):
                return True
            if v in ("0", "false", "f", "no", "n", "off"):
                return False
        return bool(value)

    if t == "text":
        return str(value)

    # numeric
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return value
    return value

# =========================
# Wio Link 裝置設定（已改名）
# =========================
BASE_URL = "https://cn.wio.seeed.io/v1/node"

DEVICES = [
    {
        "device_name": "604_door",
        "token": os.getenv("WIO_TOKEN_604_DOOR", "96c7644289c50aff68424a490845267f"),
        "source": "wio",
        "location": "604",
    },
    {
        "device_name": "604_wall",
        "token": os.getenv("WIO_TOKEN_604_WALL", "1b10e1172b455a426b53af996442c0ce"),
        "source": "wio",
        "location": "604",
    },
]

SENSORS = {
    "humidity": "/GroveTempHumD2/humidity",
    "light_intensity": "/GroveDigitalLightI2C0/lux",
    "motion_detected": "/GrovePIRMotionD1/approach",
    "dust": "/GroveDustD0/dust",
    "celsius_degree": "/GroveTempHumD2/temperature",
    "mag_approach": "/GroveMagneticSwitchD0/approach",
}

def get_wio_values(device: dict) -> dict:
    values: dict = {}
    for key, path in SENSORS.items():
        url = f"{BASE_URL}{path}?access_token={device['token']}"
        try:
            r = requests.get(url, timeout=5)
            if not r.ok:
                continue
            v = list(r.json().values())[0]
            values[key] = v
        except Exception as e:
            print(f"[錯誤] 抓取 {device['device_name']} 的 {key} 失敗：{e}")

    # mag_approach -> bool + door_status
    if values.get("mag_approach") is not None:
        mag_bool = coerce_value("mag_approach", values["mag_approach"])
        values["mag_approach"] = mag_bool
        values["door_status"] = "closed" if mag_bool else "open"

    # motion_detected -> bool
    if values.get("motion_detected") is not None:
        values["motion_detected"] = coerce_value("motion_detected", values["motion_detected"])

    return values

# =========================
# ThingSpeak helpers
# =========================
def parse_thingspeak_time(created_at: str) -> datetime:
    # "2025-12-24T18:11:40Z" => UTC aware
    dt = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
    return dt.replace(tzinfo=timezone.utc)

def get_latest_thingspeak_feed(channel_id: str, api_key: str, results: int = 1):
    url = f"https://api.thingspeak.com/channels/{channel_id}/feeds.json"
    r = requests.get(url, params={"api_key": api_key, "results": results}, timeout=5)
    r.raise_for_status()
    feeds = r.json().get("feeds", [])
    return feeds

# =========================
# 本地 PostgreSQL（寬表）寫入
# =========================
def to_int01(x) -> int | None:
    if x is None:
        return None
    try:
        # bool -> 0/1
        if isinstance(x, bool):
            return 1 if x else 0
        # "0"/"1" or float string
        return 1 if int(float(x)) == 1 else 0
    except Exception:
        return None

def upload_to_postgres_wide(device_name: str, observed_at_utc: datetime, values: dict):
    """
    寫入本地寬表 sensor_data
    欄位對齊你截圖：time, name, humidity, light_intensity, celsius_degree, mag_approach, touch, pm1_0_atm, pm2_5_atm, pm10_atm
    """
    # 你本地顯示 +08，所以這裡轉台北時間寫入（timestamptz 仍會保留時區語意）
    observed_at_taipei = observed_at_utc.astimezone(TZ_TAIPEI)

    # 本地欄位型別：humidity/light/temp 為 double precision；mag_approach/touch/pm 為 int
    humidity = values.get("humidity")
    light_intensity = values.get("light_intensity")
    celsius_degree = values.get("celsius_degree")

    mag_approach_int = to_int01(values.get("mag_approach"))
    touch_int = to_int01(values.get("touch"))

    pm1 = values.get("pm1_0_atm")
    pm25 = values.get("pm2_5_atm")
    pm10 = values.get("pm10_atm")

    try:
        cursor.execute(
            f"""
            insert into {LOCAL_WIDE_TABLE} (
                time, name,
                humidity, light_intensity, celsius_degree,
                mag_approach, touch,
                pm1_0_atm, pm2_5_atm, pm10_atm
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                observed_at_taipei,
                device_name,
                humidity,
                light_intensity,
                celsius_degree,
                mag_approach_int,
                touch_int,
                pm1,
                pm25,
                pm10,
            ),
        )
        print("✅ 本地 PostgreSQL 寬表寫入成功：", device_name, observed_at_taipei)
    except Exception as e:
        print("❌ 本地 PostgreSQL 寬表寫入失敗：", e)

# =========================
# Supabase（新版 schema）寫入
# =========================
def sb_upsert_device(device_name: str, source: str, location: str | None, token: str | None):
    supabase.table("devices").upsert(
        {
            "device_name": device_name,
            "source": source,
            "location": location,
            "token": token,
            "is_active": True,
        },
        on_conflict="device_name",
    ).execute()

def sb_ensure_metrics(metric_keys: list[str]):
    if not metric_keys:
        return
    rows = [{"metric_key": k, "value_type": infer_value_type(k)} for k in metric_keys]
    supabase.table("metrics").upsert(rows, on_conflict="metric_key").execute()

def sb_insert_reading(device_name: str, observed_at: datetime, raw: dict | None = None) -> int:
    res = supabase.table("readings").insert(
        {
            "device_name": device_name,
            "observed_at": observed_at.isoformat(),
            "raw": raw,
        }
    ).execute()
    return int(res.data[0]["reading_id"])

def sb_insert_values(reading_id: int, values: dict):
    rows = []
    for k, v in values.items():
        if v is None:
            continue
        v2 = coerce_value(k, v)
        if v2 is None:
            continue

        t = infer_value_type(k)
        row = {"reading_id": reading_id, "metric_key": k}

        if t == "bool":
            row["value_bool"] = bool(v2)
        elif t == "text":
            row["value_text"] = str(v2)
        else:
            if isinstance(v2, (int, float)) and not isinstance(v2, bool):
                row["value_numeric"] = float(v2)
            else:
                row["value_text"] = str(v2)

        rows.append(row)

    if rows:
        supabase.table("reading_values").insert(rows).execute()

def upload_to_supabase_v2(device_name: str, source: str, location: str | None, token: str | None,
                          observed_at_utc: datetime, values: dict, raw: dict | None = None):
    # 清理 + coercion
    clean = {}
    for k, v in values.items():
        if v is None:
            continue
        clean[k] = coerce_value(k, v)
    clean = {k: v for k, v in clean.items() if v is not None}

    if not clean:
        print(f"⚠️ Supabase: {device_name} 無有效數值，略過")
        return

    sb_upsert_device(device_name, source, location, token)
    sb_ensure_metrics(list(clean.keys()))
    reading_id = sb_insert_reading(device_name, observed_at_utc, raw=raw)
    sb_insert_values(reading_id, clean)
    print(f"✅ Supabase 正規化寫入成功：{device_name} @ {observed_at_utc.isoformat()} ({len(clean)} metrics)")

# =========================
# ThingSpeak：各裝置抓取（回 values + observed_at）
# =========================
def fetch_latest_604_aircondition():
    api_key = os.getenv("TS_604_AIRCONDITION_KEY", "797QS4ZPIJYT4U7W")
    channel_id = os.getenv("TS_604_AIRCONDITION_CHANNEL", "3026055")

    feed = get_latest_thingspeak_feed(channel_id, api_key, results=1)[0]
    observed_at = parse_thingspeak_time(feed["created_at"])

    values = {
        "humidity": feed.get("field2"),
        "light_intensity": feed.get("field3"),
        "celsius_degree": feed.get("field1"),
        "touch": feed.get("field4"),
    }

    return "604_aircondition", "thingspeak", "604", None, observed_at, values, {"channel_id": channel_id, "feed": feed}

def fetch_latest_604_window():
    api_key = os.getenv("TS_604_WINDOW_KEY", "G9XE5ZK8PCDHADKC")
    channel_id = os.getenv("TS_604_WINDOW_CHANNEL", "3027253")

    feed = get_latest_thingspeak_feed(channel_id, api_key, results=1)[0]
    observed_at = parse_thingspeak_time(feed["created_at"])

    values = {
        "humidity": feed.get("field2"),
        "celsius_degree": feed.get("field1"),
        "mag_approach": feed.get("field3"),
        "pm1_0_atm": feed.get("field4"),
        "pm2_5_atm": feed.get("field5"),
        "pm10_atm": feed.get("field6"),
    }

    # mag_approach -> bool + door_status
    if values.get("mag_approach") is not None:
        mag_bool = coerce_value("mag_approach", values["mag_approach"])
        values["mag_approach"] = mag_bool
        values["door_status"] = "closed" if mag_bool else "open"

    return "604_window", "thingspeak", "604", None, observed_at, values, {"channel_id": channel_id, "feed": feed}

def fetch_latest_604_center():
    api_key = os.getenv("TS_604_CENTER_KEY", "O1JMFSHUMRCTBQHL")
    channel_id = os.getenv("TS_604_CENTER_CHANNEL", "3022873")

    feed = get_latest_thingspeak_feed(channel_id, api_key, results=1)[0]
    observed_at = parse_thingspeak_time(feed["created_at"])

    values = {
        "humidity": feed.get("field2"),
        "celsius_degree": feed.get("field1"),
    }

    return "604_center", "thingspeak", "604", None, observed_at, values, {"channel_id": channel_id, "feed": feed}

def fetch_latest_604_outdoor():
    api_key = os.getenv("TS_604_OUTDOOR_KEY", "GZW95SILPGDZ8LZB")
    channel_id = os.getenv("TS_604_OUTDOOR_CHANNEL", "3031639")

    feed = get_latest_thingspeak_feed(channel_id, api_key, results=1)[0]
    observed_at = parse_thingspeak_time(feed["created_at"])

    values = {
        "humidity": feed.get("field2"),
        "celsius_degree": feed.get("field1"),
        "pm1_0_atm": feed.get("field3"),
        "pm2_5_atm": feed.get("field4"),
        "pm10_atm": feed.get("field5"),
    }

    return "604_outdoor", "thingspeak", "604", None, observed_at, values, {"channel_id": channel_id, "feed": feed}

def fetch_touch_events_last_5min():
    api_key = os.getenv("TS_604_AIRCONDITION_KEY", "797QS4ZPIJYT4U7W")
    channel_id = os.getenv("TS_604_AIRCONDITION_CHANNEL", "3026055")

    feeds = get_latest_thingspeak_feed(channel_id, api_key, results=100)
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(minutes=5)

    events = []
    for feed in feeds:
        try:
            observed_at = parse_thingspeak_time(feed["created_at"])
            if observed_at < cutoff:
                continue

            touch_val = feed.get("field4")
            if touch_val is None:
                continue
            if int(float(touch_val)) != 1:
                continue

            values = {
                "humidity": feed.get("field2"),
                "light_intensity": feed.get("field3"),
                "celsius_degree": feed.get("field1"),
                "touch": 1,  # 明確標記
            }
            events.append(("604_aircondition", "thingspeak", "604", None, observed_at, values, {"channel_id": channel_id, "feed": feed, "touch_event": True}))
        except Exception:
            continue

    return events

# =========================
# 主程式
# =========================
if __name__ == "__main__":
    # 1) Wio devices（604_door / 604_wall）
    for device in DEVICES:
        observed_at_utc = datetime.now(timezone.utc)
        values = get_wio_values(device)

        device_name = map_device_name(device["device_name"])
        raw = {"source": "wio", "device": device_name, "values": values}

        # Supabase（正規化）
        upload_to_supabase_v2(device_name, "wio", device.get("location"), device.get("token"), observed_at_utc, values, raw=raw)
        # 本地（寬表）
        upload_to_postgres_wide(device_name, observed_at_utc, values)

    # 2) ThingSpeak：604_window / 604_center 最新一筆）
    for fetcher in (fetch_latest_604_window, fetch_latest_604_center):
        try:
            device_name, source, location, token, observed_at_utc, values, raw = fetcher()

            upload_to_supabase_v2(device_name, source, location, token, observed_at_utc, values, raw=raw)
            upload_to_postgres_wide(device_name, observed_at_utc, values)
        except Exception as e:
            print(f"❌ ThingSpeak fetcher 失敗：{e}")

    
     # 3) 補抓過去 5 分鐘 touch==1
    '''
    try:
        events = fetch_touch_events_last_5min()
        for device_name, source, location, token, observed_at_utc, values, raw in events:
            upload_to_supabase_v2(device_name, source, location, token, observed_at_utc, values, raw=raw)
            upload_to_postgres_wide(device_name, observed_at_utc, values)
        print(f"✅ touch=1 補上傳完成：{len(events)} 筆")
    except Exception as e:
        print("❌ 補抓 touch=1 失敗：", e)
    '''

    # 你要就打開
    # device_name, source, location, token, observed_at_utc, values, raw = fetch_latest_604_outdoor()
    # upload_to_supabase_v2(device_name, source, location, token, observed_at_utc, values, raw=raw)
    # upload_to_postgres_wide(device_name, observed_at_utc, values)
