import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
import plotly.graph_objects as go

from supabase import create_client
from datetime import datetime, timedelta, timezone
from streamlit_autorefresh import st_autorefresh

# thermal comfort
from pythermalcomfort.models import pmv_ppd_ashrae
from pythermalcomfort.utilities import v_relative, clo_dynamic_ashrae

# heatmap overlay
from PIL import Image

# =========================================================
# Auto refresh
# =========================================================
st_autorefresh(interval=60 * 1000 * 5, key="auto-refresh")  # 每5分鐘自動刷新

# =========================================================
# Supabase client
# =========================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================================================
# Constants: device naming & sensor layout
# =========================================================
TZ_TAIPEI = "Asia/Taipei"

DEVICE_AIR_QUALITY = "604_air_quality"
DEVICE_WINDOW_PM = "604_window"
DEVICE_DOOR_LIGHT = "604_door"

# 你原本熱力圖座標（更新成新命名）
sensor_coord_map = {
    "604_window": [180, 0],
    "604_wall": [688, 215],
    "604_door": [500, 678],
    "604_air_quality": [0, 305],
    "604_center": [300, 400],
}

sensor_short_name = {
    "604_window": "Window",
    "604_door": "Door",
    "604_wall": "Wall",
    "604_air_quality": "iMac",
    "604_center": "Center",
}

# =========================================================
# Helpers: Supabase pagination
# =========================================================
def fetch_paginated(query_fn, page_size=1000, max_pages=50):
    frames = []
    offset = 0
    for _ in range(max_pages):
        q = query_fn().range(offset, offset + page_size - 1)
        resp = q.execute()
        rows = resp.data or []
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        if len(rows) < page_size:
            break
        offset += page_size
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# =========================================================
# Helpers: Load readings+values and pivot to "wide"
# =========================================================
import re
import pandas as pd
import numpy as np

import pandas as pd

def _coerce_observed_at_to_taipei(s: pd.Series) -> pd.Series:
    """
    Robust timestamptz parsing:
    - First try ISO8601 strict parsing (handles '2025-12-29T14:26:00+00:00')
    - Then fallback to fix '+08' / '+0800' forms
    - Coerce failures to NaT (but should be rare)
    """
    # keep original, but ensure it's a string series for cleaning
    raw = s.astype("string").str.strip()

    # 1) ISO8601 parse (best for Supabase/PostgREST output)
    dt = pd.to_datetime(raw, errors="coerce", utc=True, format="ISO8601")

    # 2) fallback: normalize odd offsets like +08 / +0800
    mask = dt.isna()
    if mask.any():
        fixed = raw.copy()
        fixed = fixed.str.replace(" ", "T", regex=False)
        fixed = fixed.str.replace(r"([+-]\d{2})(\d{2})$", r"\1:\2", regex=True)  # +0800 -> +08:00
        fixed = fixed.str.replace(r"([+-]\d{2})$", r"\1:00", regex=True)        # +08 -> +08:00
        dt2 = pd.to_datetime(fixed, errors="coerce", utc=True)
        dt = dt.fillna(dt2)

    # convert to Taipei time
    return dt.dt.tz_convert("Asia/Taipei")


def _pivot_values(df_long: pd.DataFrame, time_col: str = "observed_at") -> pd.DataFrame:
    if df_long.empty:
        return pd.DataFrame()

    df = df_long.copy()

    # unify value into one column
    df["value"] = None
    if "value_numeric" in df.columns:
        m = df["value_numeric"].notna()
        df.loc[m, "value"] = df.loc[m, "value_numeric"]
    if "value_bool" in df.columns:
        m = df["value_bool"].notna()
        df.loc[m, "value"] = df.loc[m, "value_bool"].astype("boolean")
    if "value_text" in df.columns:
        m = df["value_text"].notna()
        df.loc[m, "value"] = df.loc[m, "value_text"].astype(str)

    df = df.rename(columns={time_col: "time", "device_name": "name"})

    # robust datetime parsing
    df["time"] = _coerce_observed_at_to_taipei(df["time"])

    # drop only rows whose time is truly invalid
    df = df[df["time"].notna()].copy()

    wide = (
        df.pivot_table(
            index=["time", "name"],
            columns="metric_key",
            values="value",
            aggfunc="last",
        )
        .reset_index()
        .sort_values("time")
    )
    wide.columns.name = None
    return wide


@st.cache_data(ttl=60)
def load_device_metrics_wide(
    device_name: str,
    metric_keys: list[str],
    hours: int = 24,
) -> pd.DataFrame:
    """
    Query:
      readings (filter by device & time range)
      join reading_values (filter by metric keys)
    Return:
      wide df with columns: time, name, <metric_keys...>
    """
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(hours=hours)
    start_iso = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Supabase nested select: readings + reading_values
    # NOTE: postgrest syntax: reading_values!inner(metric_key, value_numeric, value_bool, value_text)
    def build_query():
        return (
            supabase.table("readings")
            .select(
                "observed_at, device_name, "
                "reading_values!inner(metric_key, value_numeric, value_bool, value_text)"
            )
            .eq("device_name", device_name)
            .gte("observed_at", start_iso)
            .lte("observed_at", end_iso)
            .in_("reading_values.metric_key", metric_keys)
            .order("observed_at", desc=False)
        )

    df_raw = fetch_paginated(build_query, page_size=1000, max_pages=50)
    if df_raw.empty:
        return pd.DataFrame(columns=["time", "name"] + metric_keys)

    # flatten nested reading_values array
    rows = []
    for _, r in df_raw.iterrows():
        obs = r.get("observed_at")
        dev = r.get("device_name")
        vals = r.get("reading_values") or []
        for v in vals:
            rows.append(
                {
                    "observed_at": obs,
                    "device_name": dev,
                    "metric_key": v.get("metric_key"),
                    "value_numeric": v.get("value_numeric"),
                    "value_bool": v.get("value_bool"),
                    "value_text": v.get("value_text"),
                }
            )

    df_long = pd.DataFrame(rows)
    if df_long.empty:
        return pd.DataFrame(columns=["time", "name"] + metric_keys)

    df_wide = _pivot_values(df_long, time_col="observed_at")

    # ensure numeric columns parse
    for k in metric_keys:
        if k in ["door_status"]:  # text
            continue
        if k in ["motion_detected", "mag_approach", "touch"]:  # bool
            # keep as bool if possible
            if k in df_wide.columns:
                df_wide[k] = df_wide[k].astype("boolean")
            continue
        # numeric
        if k in df_wide.columns:
            df_wide[k] = pd.to_numeric(df_wide[k], errors="coerce")

    return df_wide

@st.cache_data(ttl=60)
def load_latest_value(device_name: str, metric_key: str):
    """
    Fetch latest value for one metric.
    """
    resp = (
        supabase.table("readings")
        .select("observed_at, device_name, reading_values!inner(metric_key, value_numeric, value_bool, value_text)")
        .eq("device_name", device_name)
        .eq("reading_values.metric_key", metric_key)
        .order("observed_at", desc=True)
        .limit(1)
        .execute()
    )
    data = resp.data or []
    if not data:
        return None

    r0 = data[0]
    obs = pd.to_datetime(r0["observed_at"], utc=True).tz_convert(TZ_TAIPEI)
    vals = r0.get("reading_values") or []
    if not vals:
        return None

    v = vals[0]
    if v.get("value_numeric") is not None:
        value = v["value_numeric"]
    elif v.get("value_bool") is not None:
        value = bool(v["value_bool"])
    else:
        value = v.get("value_text")

    return {"time": obs, "name": device_name, metric_key: value}

# =========================================================
# Load data (24h)
# =========================================================
df_air = load_device_metrics_wide(
    device_name=DEVICE_AIR_QUALITY,
    metric_keys=["co2eq", "total_voc", "celsius_degree", "humidity"],
    hours=24,
)
df_light = load_device_metrics_wide(
    device_name=DEVICE_DOOR_LIGHT,
    metric_keys=["light_intensity"],
    hours=24,
)
df_pm = load_device_metrics_wide(
    device_name=DEVICE_WINDOW_PM,
    metric_keys=["pm1_0_atm", "pm2_5_atm", "pm10_atm", "mag_approach"],
    hours=24,
)

# =========================================================
# Page: Cards
# =========================================================
st.title("🌱 604 空氣品質即時概況")

if df_air.empty or df_light.empty or df_pm.empty:
    st.warning("目前資料不足（新 schema）。請確認 readings/reading_values 是否持續寫入，以及 RLS policy 是否允許讀取。")
    st.stop()

latest_air = df_air.dropna(subset=["celsius_degree", "humidity"], how="any").iloc[-1]
latest_light = df_light.dropna(subset=["light_intensity"], how="any").iloc[-1]
latest_pm = df_pm.dropna(subset=["pm2_5_atm"], how="any").iloc[-1]

# window status: mag_approach bool => True means closed
window_state_val = latest_pm.get("mag_approach")
window_status = "Closed" if (window_state_val is True) else "Open"

st.caption(f"📅 最新資料時間：{latest_air['time'].strftime('%Y-%m-%d %H:%M:%S %Z')}")

st.markdown(
    f"""
    <style>
    .card-container {{
        display: flex;
        flex-wrap: wrap;
        gap: 20px;
        justify-content: center;
    }}
    .card {{
        padding: 20px;
        border-radius: 15px;
        width: 160px;
        color: white;
        text-align: center;
        font-family: 'Noto Sans CJK TC', sans-serif;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }}
    .green {{ background-color: #4CAF50; }}
    .orange {{ background-color: #FF9800; }}
    .yellow {{ background-color: #FFC107; color: black; }}
    .blue {{ background-color: #2196F3; }}
    .brown {{ background-color: #A52A2A;}}
    .red {{background-color: #e53935; }}
    .pink {{ background-color: #d81b60; }}
    .purple {{ background-color: #8e24aa; }}
    .darkblue{{ background-color: #00008B; }}
    .value {{
        font-size: 32px;
        font-weight: bold;
    }}
    .label {{
        font-size: 18px;
        margin-top: 5px;
    }}
    </style>

    <div class="card-container">
        <div class="card green">
            <div class="label">CO₂</div>
            <div class="value">{int(latest_air["co2eq"])} ppm</div>
        </div>
        <div class="card orange">
            <div class="label">tVOC</div>
            <div class="value">{int(latest_air["total_voc"])} ppb</div>
        </div>
        <div class="card yellow">
            <div class="label">Temp</div>
            <div class="value">{float(latest_air["celsius_degree"]):.1f}°C</div>
        </div>
        <div class="card blue">
            <div class="label">Humidity</div>
            <div class="value">{float(latest_air["humidity"]):.0f}%</div>
        </div>
        <div class="card brown">
            <div class="label">Light</div>
            <div class="value">{float(latest_light["light_intensity"]):.0f} lux</div>
        </div>
        <div class="card red">
            <div class="label">PM1.0</div>
            <div class="value">{int(latest_pm["pm1_0_atm"])} μg/m³</div>
        </div>
        <div class="card pink">
            <div class="label">PM2.5</div>
            <div class="value">{int(latest_pm["pm2_5_atm"])} μg/m³</div>
        </div>
        <div class="card purple">
            <div class="label">PM10</div>
            <div class="value">{int(latest_pm["pm10_atm"])} μg/m³</div>
        </div>
        <div class="card darkblue">
            <div class="label">Window</div>
            <div class="value">{window_status}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================================================
# Standards badges
# =========================================================
st.subheader("🌱 臺灣室內空氣品質標準")

THRESHOLDS = {
    "co2eq_ppm_8h": 1000,
    "tvoc_ppm_1h": 0.56,
    "pm25_ug_24h": 35,
    "pm10_ug_24h": 75,
}
WARN_RATIO = 0.8

def latest_window_avg(df, col, hours, unit_conv=None):
    if df.empty or col not in df.columns:
        return None
    s = df.sort_values("time")
    end = s["time"].iloc[-1]
    start = end - pd.Timedelta(hours=hours)
    w = s.loc[(s["time"] >= start) & (s["time"] <= end), col].dropna()
    if w.empty:
        return None
    if unit_conv:
        w = unit_conv(w)
    return float(w.mean())

st.markdown("""
<style>
.env-badge {
  border-radius: 12px;
  padding: 14px 16px;
  margin: 8px 0;
  font-size: 18px;
  font-weight: 700;
  border: 1px solid rgba(0,0,0,0.06);
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.env-chip { font-weight: 800; padding: 2px 10px; border-radius: 999px;
            background: rgba(255,255,255,.35); display: inline-block; }
.env-ok    { background:#CAFFBF;  color:#0f3a15; }
.env-warn  { background:#FCFF98;  color:#3c2a00; }
.env-bad   { background:#ff6b6b; color:#3D0000; }
.env-sub   { font-weight:600; opacity:.9 }
</style>
""", unsafe_allow_html=True)

def badge(value, limit, label):
    if value is None:
        st.info(f"{label}：資料不足。")
        return
    if value > limit:
        cls, chip, lead = "env-bad", "⚠️ 超標", f"{value:.2f}"
    elif value > WARN_RATIO * limit:
        cls, chip, lead = "env-warn", "⚠️ 接近上限", f"{value:.2f}"
    else:
        cls, chip, lead = "env-ok", "✅ 正常", f"{value:.2f}"

    st.markdown(
        f"""
        <div class="env-badge {cls}">
          <span class="env-chip">{chip}</span>
          <span>{label}：{lead}</span>
          <span class="env-sub">　|　標準 {limit}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

avg_co2_8h = latest_window_avg(df_air, "co2eq", hours=8)
badge(avg_co2_8h, THRESHOLDS["co2eq_ppm_8h"], "CO₂（8小時平均，ppm）")

avg_tvoc_1h = latest_window_avg(df_air, "total_voc", hours=1, unit_conv=lambda s: s / 1000.0)
badge(avg_tvoc_1h, THRESHOLDS["tvoc_ppm_1h"], "TVOC（1小時平均，ppm）")

avg_pm25_24h = latest_window_avg(df_pm, "pm2_5_atm", hours=24)
badge(avg_pm25_24h, THRESHOLDS["pm25_ug_24h"], "PM2.5（24小時平均，μg/m³）")

avg_pm10_24h = latest_window_avg(df_pm, "pm10_atm", hours=24)
badge(avg_pm10_24h, THRESHOLDS["pm10_ug_24h"], "PM10（24小時平均，μg/m³）")

latest_time = df_air["time"].iloc[-1]
st.caption(f"📅 平均計算截至：{latest_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

# =========================================================
# IAQI
# =========================================================
st.subheader("🌈 604 室內空氣品質（indoor air quality, IAQ）")
st.caption(f"📅 最新資料時間：{latest_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

IAQI_BREAKPOINTS = {
    "co2eq": [
        (400, 599, 81, 100),
        (600, 999, 61, 80),
        (1000, 1499, 41, 60),
        (1500, 2499, 21, 40),
        (2500, 4000, 0, 20),
    ],
    "pm1_0_atm": [
        (0, 14, 81, 100),
        (15, 34, 61, 80),
        (35, 61, 41, 60),
        (62, 95, 21, 40),
        (96, 150, 0, 20),
    ],
    "pm2_5_atm": [
        (0, 20, 81, 100),
        (21, 50, 61, 80),
        (51, 90, 41, 60),
        (91, 140, 21, 40),
        (141, 200, 0, 20),
    ],
    "pm10_atm": [
        (0, 30, 81, 100),
        (31, 75, 61, 80),
        (76, 125, 41, 60),
        (126, 200, 21, 40),
        (201, 300, 0, 20),
    ],
}

def calculate_iaqi_tvoc_simple(tvoc_ppm):
    if tvoc_ppm <= 0.065:
        return 100
    elif tvoc_ppm <= 0.22:
        return 80
    elif tvoc_ppm <= 0.66:
        return 60
    elif tvoc_ppm <= 2.2:
        return 40
    elif tvoc_ppm <= 5.5:
        return 20
    else:
        return 10

def calculate_iaqi(value, breakpoints):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    for bp_lo, bp_hi, i_lo, i_hi in breakpoints:
        if bp_lo <= value <= bp_hi:
            return (i_hi - i_lo) / (bp_hi - bp_lo) * (value - bp_lo) + i_lo
    return None

co2_val = float(df_air["co2eq"].dropna().iloc[-1])
tvoc_val = float(df_air["total_voc"].dropna().iloc[-1]) / 1000.0  # ppb->ppm
pm1_val = float(df_pm["pm1_0_atm"].dropna().iloc[-1])
pm25_val = float(df_pm["pm2_5_atm"].dropna().iloc[-1])
pm10_val = float(df_pm["pm10_atm"].dropna().iloc[-1])

iaqi_co2 = calculate_iaqi(co2_val, IAQI_BREAKPOINTS["co2eq"])
iaqi_tvoc = calculate_iaqi_tvoc_simple(tvoc_val)
iaqi_pm1 = calculate_iaqi(pm1_val, IAQI_BREAKPOINTS["pm1_0_atm"])
iaqi_pm25 = calculate_iaqi(pm25_val, IAQI_BREAKPOINTS["pm2_5_atm"])
iaqi_pm10 = calculate_iaqi(pm10_val, IAQI_BREAKPOINTS["pm10_atm"])

iaqi_final = min(filter(None, [iaqi_co2, iaqi_tvoc, iaqi_pm1, iaqi_pm25, iaqi_pm10]))

st.markdown("""
<style>
.iaqi-badge {
  border-radius: 12px;
  padding: 14px 16px;
  margin: 8px 0;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
  border: 1px solid rgba(0,0,0,0.06);
}
.iaqi-good       { background:#9bf6ff;  color:#005057; }
.iaqi-moderate   { background:#CAFFBF;  color:#0f3a15; }
.iaqi-polluted   { background:#FCFF98;  color:#3c2a00;}
.iaqi-very       { background:#FF920E;  color:#3C2100; }
.iaqi-severe     { background:#ff6b6b;  color:#3D0000;  }
.iaqi-chip {
  font-weight: 800; padding: 2px 8px; border-radius: 999px; background: rgba(255,255,255,.35);
  margin-right: 8px; display: inline-block;
}
.iaqi-detail { font-weight: 500; opacity:.9 }
</style>
""", unsafe_allow_html=True)

def iaqi_bucket(score: float):
    if score is None:
        return ("Undefined", "iaqi-moderate")
    s = float(score)
    if 81 <= s <= 100:  return ("Good", "iaqi-good")
    if 61 <= s <= 80:   return ("Moderate", "iaqi-moderate")
    if 41 <= s <= 60:   return ("Polluted", "iaqi-polluted")
    if 21 <= s <= 40:   return ("Very Polluted", "iaqi-very")
    return ("Severely Polluted", "iaqi-severe")

def iaqi_badge_item(title: str, score: float, detail_text: str):
    label, css = iaqi_bucket(score)
    score_txt = "--" if score is None else f"{score:.1f}"
    st.markdown(
        f"""
        <div class="iaqi-badge {css}">
          <span class="iaqi-chip">{label}</span>
          <span>{title}：IAQI {score_txt}</span>
          <span class="iaqi-detail">　|　{detail_text}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

iaqi_badge_item("TVOC", iaqi_tvoc, f"TVOC：{tvoc_val:.3f} ppm")
iaqi_badge_item("CO₂", iaqi_co2, f"CO₂：{co2_val:.0f} ppm")
iaqi_badge_item("PM1.0", iaqi_pm1, f"PM1.0：{pm1_val:.0f} μg/m³")
iaqi_badge_item("PM2.5", iaqi_pm25, f"PM2.5：{pm25_val:.0f} μg/m³")
iaqi_badge_item("PM10", iaqi_pm10, f"PM10：{pm10_val:.0f} μg/m³")
iaqi_badge_item("綜合 IAQI（取最差）", iaqi_final, "取最差指標")

# =========================================================
# Thermal comfort (PMV/PPD) for latest air_quality values
# =========================================================
st.subheader("🌡️ 熱舒適度評估（PMV / PPD）")

ta = float(latest_air["celsius_degree"])
tr = ta
v = 0.1
rh = float(latest_air["humidity"])
met = 1.1
clo = 0.5

v_r = v_relative(v=v, met=met)
clo_d = clo_dynamic_ashrae(clo=clo, met=met)

results = pmv_ppd_ashrae(tdb=ta, tr=tr, vr=v_r, rh=rh, met=met, clo=clo_d, model="55-2023")
pmv = results.pmv
ppd = results.ppd

st.markdown("""
<style>
.pmv-badge {
  border-radius: 12px;
  padding: 14px 16px;
  margin: 8px 0;
  font-size: 18px;
  font-weight: 700;
  color: #111827;
  border: 1px solid rgba(0,0,0,0.06);
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.pmv-chip { font-weight: 800; padding: 2px 10px; border-radius: 999px;
            background: rgba(255,255,255,.35); display: inline-block; }

.pmv-cold3   { background:#1e90ff; color:#fff;}
.pmv-cold2   { background:#4da6ff; color:#fff;}
.pmv-cold1   { background:#7fd3ff; color:#0b2a3f;}
.pmv-neutral { background:#CAFFBF; color:#0b2a3f;}
.pmv-warm1   { background:#ffe08a; color:#3c2a00;}
.pmv-warm2   { background:#ffb36a; color:#3c1200;}
.pmv-hot3    { background:#ff6b6b; color:#3D0000; }

.pmv-line { font-weight:600; opacity:.9 }
</style>
""", unsafe_allow_html=True)

def pmv_bucket(pmv_val: float):
    if pmv_val <= -2.5: return "COLD", "pmv-cold3"
    if pmv_val <= -1.5: return "COOL", "pmv-cold2"
    if pmv_val <= -0.5: return "SLIGHTLY COOL", "pmv-cold1"
    if pmv_val <= 0.5:  return "NEUTRAL", "pmv-neutral"
    if pmv_val <= 1.5:  return "SLIGHTLY WARM", "pmv-warm1"
    if pmv_val <= 2.5:  return "WARM", "pmv-warm2"
    return "HOT", "pmv-hot3"

zone_label, zone_cls = pmv_bucket(float(pmv))

st.markdown(
    f"""
    <div class="pmv-badge {zone_cls}">
      <span class="pmv-chip">{zone_label}</span>
      <span>PMV：{pmv:.2f}</span>
      <span class="pmv-line">　|　建議範圍 −0.5 ~ +0.5</span>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown(
    f"""
    <div class="pmv-badge {zone_cls}">
      <span class="pmv-chip">PPD</span>
      <span>空間內有 {ppd:.1f}% 的人感到不舒適</span>
      <span class="pmv-line">　|　建議 ≤ 20%</span>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown(f"""
- 參數：
  - 操作溫度 **{ta:.1f} °C**（假設 $T_r = T_a$）
  - 相對濕度 **{rh:.0f}%**
  - 氣流速度 **{v} m/s**（動態修正 $v_r={v_r:.2f}$）
  - 代謝率 **{met} met**
  - 衣著隔熱 **{clo} clo**（動態修正後 {clo_d:.2f} clo）
""")

st.image("https://www.simscale.com/wp-content/uploads/2019/09/Artboard-1-1024x320.png", use_container_width=True)

# =========================================================
# Heatmaps: latest temperature/humidity from multiple devices
# =========================================================
st.title("🌡️ 604教室溫度/溼度/PMV/PPD 熱力圖")

FLOOR_PATH = "604vlab-2.png"
FLOOR_ALPHA = 0.5
XMAX, YMAX = 688, 687

_floor_img = Image.open(FLOOR_PATH).convert("RGBA").transpose(Image.FLIP_TOP_BOTTOM)
_floor_arr = np.array(_floor_img)

def idw(x, y, points, values, power=2):
    z = np.zeros_like(x, dtype=float)
    for i in range(x.shape[0]):
        for j in range(x.shape[1]):
            dists = np.sqrt((points[:, 0] - x[i, j])**2 + (points[:, 1] - y[i, j])**2)
            dists = np.where(dists == 0, 1e-10, dists)
            weights = 1 / dists**power
            z[i, j] = np.sum(weights * values) / np.sum(weights)
    return z

@st.cache_data(ttl=60)
def load_latest_env_points(devices: list[str]):
    # fetch last 100 readings per device, find first valid temp/humidity
    rows = []
    for dev in devices:
        df_dev = load_device_metrics_wide(dev, ["celsius_degree", "humidity"], hours=72)
        if df_dev.empty:
            continue
        # take latest non-null row
        df_dev = df_dev.dropna(subset=["celsius_degree", "humidity"], how="any")
        if df_dev.empty:
            continue
        last = df_dev.iloc[-1]
        rows.append({
            "sensor_name": dev,
            "time": last["time"],
            "temperature": float(last["celsius_degree"]),
            "humidity": float(last["humidity"]),
            "x": sensor_coord_map[dev][0],
            "y": sensor_coord_map[dev][1],
        })
    return pd.DataFrame(rows)

devices_for_map = list(sensor_coord_map.keys())
df_pts = load_latest_env_points(devices_for_map)

if df_pts.empty:
    st.warning("熱力圖：找不到足夠的溫溼資料。請確認各 device 是否有寫入 celsius_degree/humidity。")
    st.stop()

df_pts["short_name"] = df_pts["sensor_name"].apply(lambda x: sensor_short_name.get(x, x))

latest_time_map = df_pts["time"].min()

points = df_pts[["x", "y"]].to_numpy()
temperatures = df_pts["temperature"].to_numpy()
humidity_values = df_pts["humidity"].to_numpy()

grid_x, grid_y = np.meshgrid(np.linspace(0, XMAX, 200), np.linspace(0, YMAX, 200))
grid_z_temp = idw(grid_x, grid_y, points, temperatures)
grid_z_hum = idw(grid_x, grid_y, points, humidity_values)

# PMV/PPD per sensor point
met, clo, v = 1.1, 0.5, 0.1
def calc_pmv_ppd(row):
    res = pmv_ppd_ashrae(
        tdb=row["temperature"],
        tr=row["temperature"],
        rh=row["humidity"],
        vr=v_relative(v=v, met=met),
        met=met,
        clo=clo
    )
    return pd.Series({"pmv": res.pmv, "ppd": res.ppd})

df_pts[["pmv", "ppd"]] = df_pts.apply(calc_pmv_ppd, axis=1)

grid_z_pmv = idw(grid_x, grid_y, points, df_pts["pmv"].to_numpy())
grid_z_ppd = idw(grid_x, grid_y, points, df_pts["ppd"].to_numpy())

# ---- Temperature heatmap
fig, ax = plt.subplots(figsize=(10, 7))
cmap_t = plt.get_cmap('RdYlBu').reversed()
norm_t = mcolors.Normalize(vmin=20, vmax=30)
img = ax.imshow(grid_z_temp, extent=(0, XMAX, 0, YMAX), origin='lower', cmap=cmap_t, norm=norm_t, zorder=0)
ax.imshow(_floor_arr, extent=(0, XMAX, 0, YMAX), origin='lower', alpha=FLOOR_ALPHA, zorder=1)
ax.scatter(df_pts["x"], df_pts["y"], c='white', edgecolors='black', s=50, zorder=2)
for _, r in df_pts.iterrows():
    ax.text(r["x"]-15, r["y"]+10, f"{r['short_name']}\n{r['temperature']:.1f}°C",
            color='black', fontsize=9, weight='bold', zorder=3)
plt.colorbar(img, ax=ax, label='Temperature (°C)')
ax.set_title("Classroom 604 Temperature Heatmap", pad=20)
ax.set_xlabel("X (cm)"); ax.set_ylabel("Y (cm)")
ax.set_aspect('equal', adjustable='box')
plt.tight_layout()
st.markdown(f"📅 資料時間：{latest_time_map.strftime('%Y-%m-%d %H:%M:%S %Z')}")
st.pyplot(fig)

# ---- Humidity heatmap
fig, ax = plt.subplots(figsize=(10, 7))
cmap_h = plt.get_cmap('jet').reversed()
norm_h = mcolors.Normalize(vmin=0, vmax=100)
img = ax.imshow(grid_z_hum, extent=(0, XMAX, 0, YMAX), origin='lower', cmap=cmap_h, norm=norm_h, zorder=0)
ax.imshow(_floor_arr, extent=(0, XMAX, 0, YMAX), origin='lower', alpha=FLOOR_ALPHA, zorder=1)
ax.scatter(df_pts["x"], df_pts["y"], c='white', edgecolors='black', s=50, zorder=2)
for _, r in df_pts.iterrows():
    ax.text(r["x"]-15, r["y"]+10, f"{r['short_name']}\n{r['humidity']:.0f}%",
            color='black', fontsize=9, weight='bold', zorder=3)
plt.colorbar(img, ax=ax, label='Humidity (%)')
ax.set_title("Classroom 604 Humidity Heatmap", pad=20)
ax.set_xlabel("X (cm)"); ax.set_ylabel("Y (cm)")
ax.set_aspect('equal', adjustable='box')
plt.tight_layout()
st.pyplot(fig)

# ---- PMV heatmap
fig, ax = plt.subplots(figsize=(10, 7))
cmap_pmv = plt.get_cmap('Spectral').reversed()
norm_pmv = mcolors.Normalize(vmin=-3, vmax=3)
img = ax.imshow(grid_z_pmv, extent=(0, XMAX, 0, YMAX), origin='lower', cmap=cmap_pmv, norm=norm_pmv, zorder=0)
ax.imshow(_floor_arr, extent=(0, XMAX, 0, YMAX), origin='lower', alpha=FLOOR_ALPHA, zorder=1)
ax.scatter(df_pts["x"], df_pts["y"], c='white', edgecolors='black', s=50, zorder=2)
for _, r in df_pts.iterrows():
    ax.text(r["x"]-35, r["y"]+12, f"{r['short_name']}\nPMV={r['pmv']:.2f}",
            color="black", fontsize=9, weight="bold", zorder=3)
plt.colorbar(img, ax=ax, label='PMV')
ax.set_title("Classroom 604 PMV Heatmap", pad=20)
ax.set_xlabel("X (cm)"); ax.set_ylabel("Y (cm)")
ax.set_aspect('equal', adjustable='box')
plt.tight_layout()
st.pyplot(fig)

# ---- PPD heatmap
fig, ax = plt.subplots(figsize=(10, 7))
cmap_ppd = plt.get_cmap('Spectral').reversed()
norm_ppd = mcolors.Normalize(vmin=5, vmax=50)
img = ax.imshow(grid_z_ppd, extent=(0, XMAX, 0, YMAX), origin='lower', cmap=cmap_ppd, norm=norm_ppd, zorder=0)
ax.imshow(_floor_arr, extent=(0, XMAX, 0, YMAX), origin='lower', alpha=FLOOR_ALPHA, zorder=1)
ax.scatter(df_pts["x"], df_pts["y"], c='white', edgecolors='black', s=50, zorder=2)
for _, r in df_pts.iterrows():
    ax.text(r["x"]-35, r["y"]+12, f"PMV={r['pmv']:.2f}\nPPD={r['ppd']:.1f}%",
            color="black", fontsize=9, weight="bold", zorder=3)
cs = ax.contour(grid_x, grid_y, grid_z_ppd, levels=[20], colors="red", linewidths=1.8, zorder=3)
ax.clabel(cs, inline=True, fmt="PPD=20%%", fontsize=9)
plt.colorbar(img, ax=ax, label='PPD (%)')
ax.set_title("Classroom 604 PPD Heatmap", pad=20)
ax.set_xlabel("X (cm)"); ax.set_ylabel("Y (cm)")
ax.set_aspect('equal', adjustable='box')
plt.tight_layout()
st.pyplot(fig)

# =========================================================
# Long-term trends (10 days): CO2/VOC
# =========================================================
st.title("🌿 604 長期趨勢圖")
st.image("https://urbanrenewal.wealth.com.tw/uploads/editor/1625104721.jpg", use_container_width=True)

@st.cache_data(ttl=60)
def load_device_metrics_days(device_name: str, metric_keys: list[str], days: int = 10):
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(days=days)
    start_iso = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    def build_query():
        return (
            supabase.table("readings")
            .select("observed_at, device_name, reading_values!inner(metric_key, value_numeric, value_bool, value_text)")
            .eq("device_name", device_name)
            .gte("observed_at", start_iso)
            .lte("observed_at", end_iso)
            .in_("reading_values.metric_key", metric_keys)
            .order("observed_at", desc=False)
        )

    df_raw = fetch_paginated(build_query, page_size=1000, max_pages=80)
    if df_raw.empty:
        return pd.DataFrame(columns=["time", "name"] + metric_keys)

    rows = []
    for _, r in df_raw.iterrows():
        obs = r.get("observed_at")
        dev = r.get("device_name")
        vals = r.get("reading_values") or []
        for v in vals:
            rows.append(
                {
                    "observed_at": obs,
                    "device_name": dev,
                    "metric_key": v.get("metric_key"),
                    "value_numeric": v.get("value_numeric"),
                    "value_bool": v.get("value_bool"),
                    "value_text": v.get("value_text"),
                }
            )
    df_long = pd.DataFrame(rows)
    df_wide = _pivot_values(df_long, time_col="observed_at")

    for k in metric_keys:
        if k in df_wide.columns:
            df_wide[k] = pd.to_numeric(df_wide[k], errors="coerce")
    return df_wide

df_long_air = load_device_metrics_days(DEVICE_AIR_QUALITY, ["co2eq", "total_voc"], days=10)

if df_long_air.empty:
    st.info("最近 10 天沒有可用的 CO2/VOC 資料（604_air_quality）。")
else:
    fig = px.line(
        data_frame=df_long_air.dropna(subset=["co2eq"]),
        x="time",
        y="co2eq",
        title="604 教室 CO₂ 濃度變化趨勢",
        labels={"co2eq": "CO₂ (ppm)", "time": "時間"},
        height=500
    )
    fig.add_hline(y=1000, line_dash="dash", line_color="red",
                  annotation_text="警戒值：1000 ppm", annotation_position="top left")
    st.plotly_chart(fig, use_container_width=True)

    fig = px.line(
        data_frame=df_long_air.dropna(subset=["total_voc"]),
        x="time",
        y="total_voc",
        title="604 教室 VOC 濃度變化趨勢",
        labels={"total_voc": "VOC (ppb)", "time": "時間"},
        height=500
    )
    fig.add_hline(y=560, line_dash="dash", line_color="red",
                  annotation_text="警戒值：560 ppb", annotation_position="top left")
    st.plotly_chart(fig, use_container_width=True)

# =========================================================
# Long-term trends (10 days): PM (window)
# =========================================================
df_long_pm = load_device_metrics_days(DEVICE_WINDOW_PM, ["pm1_0_atm", "pm2_5_atm", "pm10_atm"], days=10)

if df_long_pm.empty:
    st.info("最近 10 天沒有可用的 PM 資料（604_window）。")
else:
    for col, title in [
        ("pm1_0_atm", "604 教室 PM1.0 濃度變化趨勢"),
        ("pm2_5_atm", "604 教室 PM2.5 濃度變化趨勢"),
        ("pm10_atm", "604 教室 PM10 濃度變化趨勢"),
    ]:
        dfx = df_long_pm.dropna(subset=[col])
        if dfx.empty:
            st.info(f"{title}：資料不足。")
            continue
        st.plotly_chart(
            px.line(dfx, x="time", y=col, title=title,
                    labels={col: f"{col} (μg/m³)", "time": "時間"}, height=500),
            use_container_width=True
        )
