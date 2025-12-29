import os
import requests
from datetime import datetime, timezone
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://cn.wio.seeed.io/v1/node"

# 你原本的 Wio 裝置
DEVICES = [
    {"name": "wiolink door", "token": "96c7644289c50aff68424a490845267f", "source": "wio", "location": "604"},
    {"name": "wiolink wall", "token": "1b10e1172b455a426b53af996442c0ce", "source": "wio", "location": "604"},
]

SENSORS = {
    "light_intensity": "/GroveDigitalLightI2C0/lux",
    "motion_detected": "/GrovePIRMotionD1/approach",
    "dust": "/GroveDustD0/dust",
    "celsius_degree": "/GroveTempHumD2/temperature",
    "humidity": "/GroveTempHumD2/humidity",
    "mag_approach": "/GroveMagneticSwitchD0/approach",
}

# ---- DB helpers ----

def upsert_device(device_name: str, source: str = "other", location: str | None = None, token: str | None = None) -> int:
    """
    Upsert devices by device_name, return device_id.
    """
    payload = {
        "device_name": device_name,
        "source": source,
        "location": location,
        "token": token,
        "is_active": True,
    }
    # Supabase upsert needs unique constraint; device_name is unique.
    res = supabase.table("devices").upsert(payload, on_conflict="device_name").execute()
    # upsert 回來通常含 data，但不同版本行為可能略不同；保守起見再查一次
    row = supabase.table("devices").select("device_id").eq("device_name", device_name).limit(1).execute().data[0]
    return int(row["device_id"])

def ensure_metrics(metric_keys: list[str]) -> dict[str, int]:
    """
    Ensure metrics exist. Return mapping metric_key -> metric_id.
    """
    if not metric_keys:
        return {}

    # 先查已存在的
    existing = supabase.table("metrics").select("metric_id,metric_key").in_("metric_key", metric_keys).execute().data
    mapping = {m["metric_key"]: int(m["metric_id"]) for m in existing}

    # 補不存在的
    to_insert = []
    for k in metric_keys:
        if k not in mapping:
            # 這裡預設 numeric；若你要更嚴謹，可在此加型別推斷
            to_insert.append({"metric_key": k, "value_type": "numeric"})
    if to_insert:
        supabase.table("metrics").upsert(to_insert, on_conflict="metric_key").execute()
        # 再查一次補齊
        existing2 = supabase.table("metrics").select("metric_id,metric_key").in_("metric_key", metric_keys).execute().data
        mapping = {m["metric_key"]: int(m["metric_id"]) for m in existing2}

    return mapping

def insert_reading(device_id: int, observed_at: datetime, raw: dict | None = None) -> int:
    res = supabase.table("readings").insert({
        "device_id": device_id,
        "observed_at": observed_at.isoformat(),
        "raw": raw
    }).execute()
    return int(res.data[0]["reading_id"])

def insert_reading_values(reading_id: int, metric_id_map: dict[str, int], values: dict):
    rows = []
    for k, v in values.items():
        if v is None:
            continue
        metric_id = metric_id_map[k]

        row = {"reading_id": reading_id, "metric_id": metric_id}

        # 型別分流：你可視需求擴充
        if isinstance(v, bool):
            row["value_bool"] = v
        elif isinstance(v, (int, float)):
            row["value_numeric"] = float(v)
        else:
            row["value_text"] = str(v)

        rows.append(row)

    if rows:
        supabase.table("reading_values").insert(rows).execute()

# ---- Data sources ----

def get_wio_device_values(device):
    values = {}

    for key, path in SENSORS.items():
        url = f"{BASE_URL}{path}?access_token={device['token']}"
        try:
            r = requests.get(url, timeout=5)
            if not r.ok:
                continue
            value = list(r.json().values())[0]
            values[key] = value

            if key == "mag_approach":
                values["door_status"] = "closed" if value == 1 else "open"

        except Exception as e:
            print(f"[錯誤] 抓取 {device['name']} 的 {key} 失敗：{e}")

    return values

def get_thingspeak_604center_values():
    CHANNEL_ID = "3022873"
    READ_API_KEY = "O1JMFSHUMRCTBQHL"
    url = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
    try:
        r = requests.get(url, params={"api_key": READ_API_KEY, "results": 1}, timeout=5)
        r.raise_for_status()
        feed = r.json()["feeds"][0]
        return {
            "celsius_degree": float(feed["field1"]) if feed["field1"] else None,
            "humidity": float(feed["field2"]) if feed["field2"] else None,
        }
    except Exception as e:
        print("❌ 無法取得 ThingSpeak 604_center：", e)
        return None

def get_thingspeak_604window_values():
    CHANNEL_ID = "3027253"
    READ_API_KEY = "G9XE5ZK8PCDHADKC"
    url = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
    try:
        r = requests.get(url, params={"api_key": READ_API_KEY, "results": 1}, timeout=5)
        r.raise_for_status()
        feed = r.json()["feeds"][0]
        return {
            "celsius_degree": float(feed["field1"]) if feed["field1"] else None,
            "humidity": float(feed["field2"]) if feed["field2"] else None,
            "pm1_0_atm": float(feed["field4"]) if feed["field4"] else None,
            "pm2_5_atm": float(feed["field5"]) if feed["field5"] else None,
            "pm10_atm": float(feed["field6"]) if feed["field6"] else None,
        }
    except Exception as e:
        print("❌ 無法取得 ThingSpeak wiolink window：", e)
        return None

def get_thingspeak_604outdoor_values():
    CHANNEL_ID = "3031639"
    READ_API_KEY = "GZW95SILPGDZ8LZB"
    url = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
    try:
        r = requests.get(url, params={"api_key": READ_API_KEY, "results": 1}, timeout=5)
        r.raise_for_status()
        feed = r.json()["feeds"][0]
        return {
            "celsius_degree": float(feed["field1"]) if feed["field1"] else None,
            "humidity": float(feed["field2"]) if feed["field2"] else None,
            "pm1_0_atm": float(feed["field3"]) if feed["field3"] else None,
            "pm2_5_atm": float(feed["field4"]) if feed["field4"] else None,
            "pm10_atm": float(feed["field5"]) if feed["field5"] else None,
        }
    except Exception as e:
        print("❌ 無法取得 ThingSpeak 604_outdoor：", e)
        return None

# ---- Main ----

def ingest_one(device_name: str, source: str, location: str | None, token: str | None, values: dict):
    # 只保留有值的 keys（避免把 None 當成一個 metric 值寫入）
    values = {k: v for k, v in values.items() if v is not None}
    if not values:
        return

    device_id = upsert_device(device_name, source=source, location=location, token=token)

    metric_id_map = ensure_metrics(list(values.keys()))

    observed_at = datetime.now(timezone.utc)
    reading_id = insert_reading(device_id, observed_at, raw={"values": values, "source": source})

    insert_reading_values(reading_id, metric_id_map, values)
    print(f"✅ Ingested {device_name} at {observed_at.isoformat()} with {len(values)} metrics")

if __name__ == "__main__":
    # Wio devices
    for d in DEVICES:
        vals = get_wio_device_values(d)
        ingest_one(d["name"], d["source"], d.get("location"), d.get("token"), vals)

    # ThingSpeak devices
    v = get_thingspeak_604center_values()
    if v:
        ingest_one("604_center", "thingspeak", "604", None, v)

    v = get_thingspeak_604window_values()
    if v:
        ingest_one("wiolink window", "thingspeak", "604", None, v)

    v = get_thingspeak_604outdoor_values()
    if v:
        ingest_one("604_outdoor", "thingspeak", "604", None, v)
