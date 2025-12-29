import os
import requests
from datetime import datetime, timezone
from supabase import create_client

# =========================
# Supabase 設定（GitHub Secrets）
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL / SUPABASE_KEY env vars")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# Wio API
# =========================
BASE_URL = "https://cn.wio.seeed.io/v1/node"

# 你的 Wio 裝置（已改名）
DEVICES = [
    {"device_name": "604_door", "token": "96c7644289c50aff68424a490845267f", "source": "wio", "location": "604"},
    {"device_name": "604_wall", "token": "1b10e1172b455a426b53af996442c0ce", "source": "wio", "location": "604"},
]

# Wio 感測器 API 路徑
SENSORS = {
    "light_intensity": "/GroveDigitalLightI2C0/lux",
    "motion_detected": "/GrovePIRMotionD1/approach",
    "dust": "/GroveDustD0/dust",
    "celsius_degree": "/GroveTempHumD2/temperature",
    "humidity": "/GroveTempHumD2/humidity",
    "mag_approach": "/GroveMagneticSwitchD0/approach",
}

# =========================
# 型別推斷規則（你指定的）
# =========================
EXPLICIT_TYPES = {
    "door_status": "text",
    "motion_detected": "bool",
    "mag_approach": "bool",
    "touch": "bool",
}

def infer_value_type(metric_key: str) -> str:
    """
    回傳 metrics.value_type 的值：'numeric' / 'bool' / 'text'
    """
    return EXPLICIT_TYPES.get(metric_key, "numeric")

def coerce_value(metric_key: str, value):
    """
    依 metric_key 做值轉型（確保寫入 reading_values 時型別一致）
    - 指定為 bool 的：把 0/1、"0"/"1"、True/False 等轉成 bool
    - 指定為 text 的：轉成 str
    - 其餘 numeric：盡量轉 float（失敗就回原值，讓後續當 text 寫入以免整筆掛掉）
    """
    t = infer_value_type(metric_key)

    if value is None:
        return None

    if t == "bool":
        # 常見狀況：0/1、"0"/"1"
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
        # 無法辨識就保守轉 bool（非空字串會變 True；不理想但避免整批失敗）
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
            return value  # 讓後續 fallback 成 text
    return value

# =========================
# DB helpers（新版 schema：device_name / metric_key）
# =========================
def upsert_device(device_name: str, source: str = "other", location: str | None = None, token: str | None = None) -> None:
    payload = {
        "device_name": device_name,
        "source": source,
        "location": location,
        "token": token,
        "is_active": True,
    }
    supabase.table("devices").upsert(payload, on_conflict="device_name").execute()

def ensure_metrics(metric_keys: list[str]) -> None:
    """
    確保 metrics 表中存在所有 metric_key，並依規則寫入正確 value_type。
    """
    if not metric_keys:
        return

    rows = []
    for k in metric_keys:
        rows.append({
            "metric_key": k,
            "value_type": infer_value_type(k),
        })

    supabase.table("metrics").upsert(rows, on_conflict="metric_key").execute()

def insert_reading(device_name: str, observed_at: datetime, raw: dict | None = None) -> int:
    res = supabase.table("readings").insert({
        "device_name": device_name,
        "observed_at": observed_at.isoformat(),
        "raw": raw
    }).execute()
    return int(res.data[0]["reading_id"])

def build_value_row(reading_id: int, metric_key: str, value):
    """
    依 infer_value_type 決定寫到 value_numeric/value_bool/value_text。
    並符合 exactly_one_value constraint。
    """
    v = coerce_value(metric_key, value)
    if v is None:
        return None

    row = {"reading_id": reading_id, "metric_key": metric_key}
    t = infer_value_type(metric_key)

    if t == "bool":
        row["value_bool"] = bool(v)
        return row

    if t == "text":
        row["value_text"] = str(v)
        return row

    # numeric：若轉型失敗而留下非數字（例如 "N/A"），就 fallback 成 text 避免寫入失敗
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        row["value_numeric"] = float(v)
        return row

    # fallback
    row["value_text"] = str(v)
    return row

def insert_reading_values(reading_id: int, values: dict) -> None:
    rows = []
    for k, v in values.items():
        if v is None:
            continue
        row = build_value_row(reading_id, k, v)
        if row:
            rows.append(row)

    if rows:
        supabase.table("reading_values").insert(rows).execute()

# =========================
# Data sources
# =========================
def get_wio_device_values(device: dict) -> dict:
    """
    從單一 Wio 裝置抓取所有感測器值，回傳 dict: {metric_key: value}
    """
    values: dict = {}

    for key, path in SENSORS.items():
        url = f"{BASE_URL}{path}?access_token={device['token']}"
        try:
            r = requests.get(url, timeout=5)
            if not r.ok:
                continue

            payload = r.json()
            value = list(payload.values())[0]

            # 先做一次 coercion（例如 mag_approach/motion_detected 轉 bool）
            values[key] = coerce_value(key, value)

            # 衍生指標：door_status（文字）
            if key == "mag_approach":
                values["door_status"] = "closed" if values[key] else "open"

        except Exception as e:
            print(f"[錯誤] 抓取 {device['device_name']} 的 {key} 失敗：{e}")

    return values

def get_thingspeak_latest(channel_id: str, read_api_key: str) -> dict | None:
    url = f"https://api.thingspeak.com/channels/{channel_id}/feeds.json"
    try:
        r = requests.get(url, params={"api_key": read_api_key, "results": 1}, timeout=5)
        r.raise_for_status()
        feeds = r.json().get("feeds", [])
        if not feeds:
            return None
        return feeds[0]
    except Exception as e:
        print(f"❌ ThingSpeak 讀取失敗 (channel={channel_id}): {e}")
        return None

def get_604_center_values() -> dict | None:
    feed = get_thingspeak_latest("3022873", "O1JMFSHUMRCTBQHL")
    if not feed:
        return None
    return {
        "celsius_degree": feed.get("field1"),
        "humidity": feed.get("field2"),
    }

def get_604_window_values() -> dict | None:
    feed = get_thingspeak_latest("3027253", "G9XE5ZK8PCDHADKC")
    if not feed:
        return None
    return {
        "celsius_degree": feed.get("field1"),
        "humidity": feed.get("field2"),
        "pm1_0_atm": feed.get("field4"),
        "pm2_5_atm": feed.get("field5"),
        "pm10_atm": feed.get("field6"),
    }

def get_604_outdoor_values() -> dict | None:
    feed = get_thingspeak_latest("3031639", "GZW95SILPGDZ8LZB")
    if not feed:
        return None
    return {
        "celsius_degree": feed.get("field1"),
        "humidity": feed.get("field2"),
        "pm1_0_atm": feed.get("field3"),
        "pm2_5_atm": feed.get("field4"),
        "pm10_atm": feed.get("field5"),
    }

# =========================
# Ingest pipeline
# =========================
def ingest_one(device_name: str, source: str, location: str | None, token: str | None, values: dict) -> None:
    # 清理 + 依規則轉型
    clean = {}
    for k, v in values.items():
        if v is None:
            continue
        clean[k] = coerce_value(k, v)

    # 去掉轉完仍為 None 的
    clean = {k: v for k, v in clean.items() if v is not None}

    if not clean:
        print(f"⚠️ {device_name}: no values, skip")
        return

    upsert_device(device_name, source=source, location=location, token=token)
    ensure_metrics(list(clean.keys()))

    observed_at = datetime.now(timezone.utc)
    reading_id = insert_reading(
        device_name=device_name,
        observed_at=observed_at,
        raw={"source": source, "values": clean}
    )

    insert_reading_values(reading_id, clean)
    print(f"✅ Ingested {device_name} at {observed_at.isoformat()} ({len(clean)} metrics)")

# =========================
# Main
# =========================
if __name__ == "__main__":
    # 1) Wio devices (604_door / 604_wall)
    for d in DEVICES:
        vals = get_wio_device_values(d)
        ingest_one(d["device_name"], d["source"], d.get("location"), d.get("token"), vals)

    # 2) ThingSpeak devices: 604_center / 604_window / 604_outdoor
    v = get_604_center_values()
    if v:
        ingest_one("604_center", "thingspeak", "604", None, v)

    v = get_604_window_values()
    if v:
        ingest_one("604_window", "thingspeak", "604", None, v)

    v = get_604_outdoor_values()
    if v:
        ingest_one("604_outdoor", "thingspeak", "604", None, v)
