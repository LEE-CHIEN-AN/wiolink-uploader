import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import os
from supabase import create_client
from datetime import datetime, timedelta, timezone
# 字型設定（針對 Windows 中文支援）
import matplotlib
import plotly.express as px
import plotly.graph_objects as go

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=60 * 1000 *5, key="auto-refresh")  # 每5分鐘自動刷新

# ---------- Supabase 設定 ----------
# Supabase 設定
# === Supabase 設定（從 GitHub Secrets 環境變數取得） ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ========== 資料抓取 ==========
@st.cache_data(ttl=60)  # 每1分鐘更新
def load_data_604():
    now = datetime.now(timezone(timedelta(hours=8)))
    start_time = now - timedelta(hours=24)

    response = supabase.table("wiolink") \
        .select("time, name, co2eq, celsius_degree, humidity, total_voc") \
        .eq("name", "604_air_quality") \
        .gte("time", start_time.isoformat()) \
        .order("time", desc=False) \
        .execute()
  
    df = pd.DataFrame(response.data)
    df["time"] = pd.to_datetime(df["time"])
    return df.dropna()
    
@st.cache_data(ttl=60)  # 每1分鐘更新
def load_data_604light():
    now = datetime.now(timezone(timedelta(hours=8)))
    start_time = now - timedelta(hours=24)

    response = supabase.table("wiolink") \
        .select("time, name, light_intensity") \
        .eq("name", "wiolink wall") \
        .gte("time", start_time.isoformat()) \
        .order("time", desc=False) \
        .execute()

    df = pd.DataFrame(response.data)
    df["time"] = pd.to_datetime(df["time"])
    return df.dropna()

@st.cache_data(ttl=60)  # 每1分鐘更新
def load_data_604PM():
    now = datetime.now(timezone(timedelta(hours=8)))
    start_time = now - timedelta(hours=24)

    response = supabase.table("wiolink") \
        .select("time, name, pm1_0_atm,pm2_5_atm, pm10_atm") \
        .eq("name", "604_pm2.5") \
        .gte("time", start_time.isoformat()) \
        .order("time", desc=False) \
        .execute()

    df = pd.DataFrame(response.data)
    df["time"] = pd.to_datetime(df["time"])
    return df.dropna()

df = load_data_604()
df_light  = load_data_604light()
df_pm = load_data_604PM()
# ========== 畫面與圖表 ==========
st.title("🌱 604 空氣品質即時概況")

# 取最後一筆資料
latest = df.iloc[-1]
latest_light = df_light.iloc[-1]
latest_pm = df_pm.iloc[-1]
st.markdown(f"📅 最新資料時間：{latest['time'].strftime('%Y-%m-%d %H:%M:%S')}")

# 以 HTML + CSS 呈現卡片
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
            <div class="value">{latest["co2eq"]} ppm</div>
        </div>
        <div class="card orange">
            <div class="label">tVOC</div>
            <div class="value">{latest["total_voc"]} ppb</div>
        </div>
        <div class="card yellow">
            <div class="label">Temp</div>
            <div class="value">{latest["celsius_degree"]:.1f}°C</div>
        </div>
        <div class="card blue">
            <div class="label">Humidity</div>
            <div class="value">{latest["humidity"]:.0f}%</div>
        </div>
        <div class="card brown">
            <div class="label">Light Intensity</div>
            <div class="value">{latest_light["light_intensity"]:.0f} lux</div>
        </div>
        <div class="card red">
            <div class="label">PM1.0</div>
            <div class="value">{latest_pm["pm1_0_atm"]} μg/m³</div>
        </div>
        <div class="card pink">
            <div class="label">PM2.5</div>
            <div class="value">{latest_pm["pm2_5_atm"]} μg/m³</div>
        </div>
        <div class="card purple">
            <div class="label">PM10</div>
            <div class="value">{latest_pm["pm10_atm"]} μg/m³</div>
        </div>

    </div>
    """,
    unsafe_allow_html=True
)

#=================================================
TZ = timezone(timedelta(hours=8))

# ========= 門檻 =========
THRESHOLDS = {
    "co2eq_ppm_8h": 1000,      # CO2 8h
    "tvoc_ppm_1h": 0.56,       # TVOC 1h (注意單位換算)
    "pm25_ug_24h": 35,         # PM2.5 24h
    "pm10_ug_24h": 75,         # PM10 24h
}

# 近乎超標的提醒比例
WARN_RATIO = 0.8

def latest_window_avg(df, col, hours, unit_conv=None):
    """
    取 df 中 col 欄位在「最新時間往回 hours 小時」的平均。
    df 需包含 time 欄位（datetime64[ns, tz] 或可轉換），且升冪排序。
    unit_conv: 可選單位換算的函式，例如 lambda s: s / 1000
    """
    if df.empty:
        return None

    # 確保時間為 tz-aware、升冪排序
    s = df.copy()
    s["time"] = pd.to_datetime(s["time"]).dt.tz_convert(TZ) if pd.to_datetime(s["time"]).dt.tz is not None else pd.to_datetime(s["time"]).dt.tz_localize(TZ)
    s = s.sort_values("time")

    end = s["time"].iloc[-1]
    start = end - pd.Timedelta(hours=hours)
    mask = (s["time"] >= start) & (s["time"] <= end)

    window = s.loc[mask, col].dropna()
    if window.empty:
        return None

    if unit_conv:
        window = unit_conv(window)

    return float(window.mean())


def badge(value, limit, label, unit):
    """回傳 Streamlit 的警示方塊：安全/接近/超標"""
    if value is None:
        st.info(f"{label}：近 {unit} 無足夠資料。")
        return

    if value > limit:
        st.error(f"⚠️ {label} 超標：{value:.2f}（標準 {limit}）")
    elif value > WARN_RATIO * limit:
        st.warning(f"⚠️ {label} 接近上限：{value:.2f}（標準 {limit}）")
    else:
        st.success(f"✅ {label} 正常：{value:.2f}（標準 {limit}）")


# ========= 與你現有 df 接軌 =========
# 假設：
# df         : 604_air_quality（含 time, co2eq, total_voc 等）
# df_pm2_5   : 604_pm2.5（含 time, pm2_5_atm）
# df_pm10    : 604_pm2.5（同表也有 pm10_atm；若你分表，請改變名稱）

# 1) CO2（8h 平均）
avg_co2_8h = latest_window_avg(df, "co2eq", hours=8)
badge(avg_co2_8h, THRESHOLDS["co2eq_ppm_8h"], "CO₂（8小時平均，ppm）", "8 小時")

# 2) TVOC（1h 平均，ppb→ppm）
avg_tvoc_1h = latest_window_avg(df, "total_voc", hours=1, unit_conv=lambda s: s/1000.0)
badge(avg_tvoc_1h, THRESHOLDS["tvoc_ppm_1h"], "TVOC（1小時平均，ppm）", "1 小時")

# 3) PM2.5（24h 平均）
avg_pm25_24h = latest_window_avg(df_pm2_5, "pm2_5_atm", hours=24)
badge(avg_pm25_24h, THRESHOLDS["pm25_ug_24h"], "PM2.5（24小時平均，μg/m³）", "24 小時")

# 4) PM10（24h 平均）
avg_pm10_24h = latest_window_avg(df_pm2_5, "pm10_atm", hours=24)
badge(avg_pm10_24h, THRESHOLDS["pm10_ug_24h"], "PM10（24小時平均，μg/m³）", "24 小時")

# （可選）在頁面上也顯示最新時間點，讓使用者知道平均是到什麼時刻
if not df.empty:
    latest_time = pd.to_datetime(df["time"].iloc[-1])
    latest_time = latest_time.tz_convert(TZ) if latest_time.tzinfo else latest_time.tz_localize(TZ)
    st.caption(f"平均計算截至：{latest_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

#==============================================================================
st.title("🌱 604 空氣品質感測看板")
fig, axs = plt.subplots(4, 2, figsize=(18, 24))

# CO2
axs[0, 0].plot(df["time"], df["co2eq"], marker='o', color='green')
axs[0, 0].set_title("CO₂")
axs[0, 0].set_ylabel("ppm")
axs[0, 0].tick_params(axis='x', rotation=45)

# TVOC
axs[0, 1].plot(df["time"], df["total_voc"], marker='o', color='orange')
axs[0, 1].set_title("TVOC")
axs[0, 1].set_ylabel("ppb")
axs[0, 1].tick_params(axis='x', rotation=45)

# Temperature
axs[1, 0].plot(df["time"], df["celsius_degree"], marker='o', color='gold')
axs[1, 0].set_title("Temperature")
axs[1, 0].set_ylabel("°C")
axs[1, 0].tick_params(axis='x', rotation=45)

# Humidity
axs[1, 1].plot(df["time"], df["humidity"], marker='o', color='blue')
axs[1, 1].set_title("Humidity")
axs[1, 1].set_ylabel("%")
axs[1, 1].tick_params(axis='x', rotation=45)

# light
axs[2,0].plot(df_light["time"], df_light["light_intensity"], marker='o', color='brown')
axs[2,0].set_title("Light intensity")
axs[2,0].set_ylabel("lux")
axs[2,0].tick_params(axis='x', rotation=45)

# PM2.5
axs[2, 1].plot(df_pm["time"], df_pm["pm2_5_atm"], marker='o', color='pink')
axs[2, 1].set_title("PM2.5")
axs[2, 1].set_ylabel("μg/m³")
axs[2, 1].tick_params(axis='x', rotation=45)

# PM1.0
axs[3, 0].plot(df_pm["time"], df_pm["pm1_0_atm"], marker='o', color='red')
axs[3, 0].set_title("PM2.5")
axs[3, 0].set_ylabel("μg/m³")
axs[3, 0].tick_params(axis='x', rotation=45)

# PM10
axs[3, 1].plot(df_pm["time"], df_pm["pm10_atm"], marker='o', color='purple')
axs[3, 1].set_title("PM2.5")
axs[3, 1].set_ylabel("μg/m³")
axs[3, 1].tick_params(axis='x', rotation=45)

plt.tight_layout()
st.pyplot(fig)

# 604 溫度熱力圖========================================
import matplotlib.colors as mcolors
# 感測器固定座標
sensor_coord_map = {
    "wiolink window": [180, 0],
    "wiolink wall": [688, 215],
    "wiolink door": [500, 678],
    "604_air_quality": [0, 305],
    "604_pm2.5" : [300,400]
}

# 從 Supabase 抓取最新一筆各感測器溫度資料
sensor_names = list(sensor_coord_map.keys())
latest_data = []

for name in sensor_coord_map:
    res = supabase.table("wiolink") \
        .select("time, name, celsius_degree,humidity") \
        .eq("name", name) \
        .order("time", desc=True) \
        .limit(100) \
        .execute()

    # 避免找不到資料
    if not res.data:
        st.error(f"❌ 感測器 `{name}` 無資料，請確認 Supabase 是否有上傳紀錄")
        st.stop()

    # 找到第一筆有效數據
    found = False
    for row in res.data:
        temp = row["celsius_degree"]
        if temp is not None and not np.isnan(temp):
            latest_data.append({
                "sensor_name": name,
                "time": row["time"],
                "temperature": temp,
                "humidity": row["humidity"],
                "x": sensor_coord_map[name][0],
                "y": sensor_coord_map[name][1]
            })
            found = True
            break

    # 若沒找到有效值就報錯停止
    if not found:
        st.error(f"❌ 感測器 `{name}` 找不到有效溫度值（全部為 NaN）")
        st.stop()

# 組成 DataFrame
df = pd.DataFrame(latest_data)
df["time"] = pd.to_datetime(df["time"])
latest_time = df["time"].min()

# 建立座標與值陣列
points = df[["x", "y"]].to_numpy()
temperatures = df["temperature"].to_numpy()

# IDW 插值
grid_x, grid_y = np.meshgrid(np.linspace(0, 688, 200), np.linspace(0, 687, 200))

def idw(x, y, points, values, power=2):
    z = np.zeros_like(x)
    for i in range(x.shape[0]):
        for j in range(x.shape[1]):
            dists = np.sqrt((points[:,0] - x[i,j])**2 + (points[:,1] - y[i,j])**2)
            dists = np.where(dists==0, 1e-10, dists)
            weights = 1 / dists**power
            z[i,j] = np.sum(weights * values) / np.sum(weights)
    return z

grid_z = idw(grid_x, grid_y, points, temperatures)

# 色彩設定與繪圖
cmap = plt.get_cmap('RdYlBu').reversed()
norm = mcolors.Normalize(vmin=20, vmax=30)  # 固定 colorbar 區間為 20~30°C

plt.figure(figsize=(8, 6))
img = plt.imshow(grid_z, extent=(0, 688, 0, 687), origin='lower',cmap=cmap, norm=norm, aspect='auto')
plt.scatter(df["x"], df["y"], c='white', edgecolors='black', label='Sensors')

sensor_short_name = {
    "wiolink window": "Window",
    "wiolink door": "Door",
    "wiolink wall": "Wall",
    "604_air_quality": "iMac",
    "604_pm2.5" : "PM2.5"
}
df["short_name"] = df["sensor_name"].apply(lambda x: sensor_short_name.get(x, x))

for i, row in df.iterrows():
    label = f"{row['short_name']}\n{row['temperature']:.1f}°C"
    plt.text(row["x"] -15, row["y"] + 10, label,
             color='black', fontsize=9, weight='bold')

cbar = plt.colorbar(img, label='Temperature (°C)')
cbar.set_ticks(np.arange(20, 31, 1))  # 每 1°C 一格
plt.title("Classroom Temperature Heatmap (IDW, with Sensor Labels)", pad=20)
plt.xlabel("X (cm)")
plt.ylabel("Y (cm)")
plt.legend(loc='lower right')
plt.tight_layout()


# 顯示在 Streamlit
st.title("🌡️ 604 溫度熱力圖")
# 找出資料時間（最晚時間）
st.markdown(f"📅 資料時間：{latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
st.pyplot(plt)

#---------------------------------------------------------------------------------

plt.figure(figsize=(8, 6))
humidity_values = df["humidity"].to_numpy()
grid_z_humidity = idw(grid_x, grid_y, points, humidity_values)

cmap = plt.get_cmap('jet').reversed()
norm=mcolors.Normalize(vmin=0, vmax=100)

img = plt.imshow(grid_z_humidity, extent=(0, 688, 0, 687), origin='lower', cmap=cmap, norm=norm, aspect='auto')
plt.scatter(df["x"], df["y"], c='white', edgecolors='black', label='Sensors')

for i, row in df.iterrows():
    label = f"{row['short_name']}\n{row['humidity']}%"
    plt.text(row["x"] - 15, row["y"] + 10, label,
             color='black', fontsize=9, weight='bold')

# 色彩設定與繪圖
cbar = plt.colorbar(img, label='Humidity (%)')
cbar.set_ticks(np.arange(0, 105, 5))
plt.title("Classroom Humidity Heatmap (IDW, with Sensor Labels)", pad=20)
plt.xlabel("X (cm)")
plt.ylabel("Y (cm)")
plt.legend(loc='lower right')
plt.tight_layout()
# 顯示在 Streamlit
st.title("🌡️ 604 溼度熱力圖")
# 找出資料時間（最晚時間）
st.markdown(f"📅 資料時間：{latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
st.pyplot(plt)

# 604 溫溼度熱力圖 END========================================
#================================================================
# ---------- 資料抓取函式 ----------
@st.cache_data(ttl=60)  # 每1分鐘更新一次
def load_co2_data():
    now = datetime.now(timezone(timedelta(hours=8)))
    start_time = now - timedelta(days=7)

    response = supabase.table("wiolink") \
        .select("time, name, co2eq,total_voc") \
        .eq("name", "604_air_quality") \
        .order("time", desc=False) \
        .execute()

    df = pd.DataFrame(response.data)
    df["time"] = pd.to_datetime(df["time"])
    df = df.dropna(subset=["co2eq"])
    return df

# ---------- 畫面與圖表 ----------
st.title("🌿 604 長期趨勢圖")

df = load_co2_data()

fig = px.line(
    data_frame=df,
    x="time",
    y="co2eq",
    title="604 教室 CO₂ 濃度變化趨勢",
    labels={"co2eq": "CO₂ (ppm)", "time": "時間"},
    height=500
)

st.plotly_chart(fig, use_container_width=True)
#--------------------------------------------
fig = px.line(
    data_frame=df,
    x="time",
    y="total_voc",
    title="604 教室 VOC 濃度變化趨勢",
    labels={"total_voc": "VOC (ppb)", "time": "時間"},
    height=500
)

st.plotly_chart(fig, use_container_width=True)

# 溫度長期趨勢圖=====
# 🔁 下拉選單選擇時間範圍
time_range = st.selectbox(
    "請選擇資料時間範圍：",
    options=["近 7 天", "近 30 天", "全部資料"]
)

# 🕒 根據選項設定時間區間
def get_start_time(range_label):
    now = datetime.now(timezone(timedelta(hours=8)))
    if range_label == "近 7 天":
        return now - timedelta(days=7)
    elif range_label == "近 30 天":
        return now - timedelta(days=30)
    else:
        return None  # 代表不限制時間

# 📦 讀取資料
@st.cache_data(ttl=60)
def load_dht11_data(start_time=None):
    query = supabase.table("wiolink") \
        .select("time, name, humidity, celsius_degree, light_intensity") \
        .eq("name", "wiolink door") \
        .order("time", desc=False)

    if start_time:
        query = query.gte("time", start_time.isoformat())

    response = query.execute()
    df = pd.DataFrame(response.data)
    df["time"] = pd.to_datetime(df["time"])
    df = df.dropna(subset=["celsius_degree"])
    return df

# 🧠 呼叫函式取得資料
start_time = get_start_time(time_range)
df = load_dht11_data(start_time=start_time)

# 📊 繪製互動式圖表
fig = px.line(
    data_frame=df,
    x="time",
    y="celsius_degree",
    title=f"604 教室溫度變化趨勢（{time_range}）",
    labels={"celsius_degree": "celsius degree", "time": "時間"},
    height=500
)

st.plotly_chart(fig, use_container_width=True)



#=========================================================
# ========== 資料抓取 ==========
@st.cache_data(ttl=60)  # 每1分鐘更新
def load_data_407():
    now = datetime.now(timezone(timedelta(hours=8)))
    start_time = now - timedelta(hours=24)

    response = supabase.table("wiolink") \
        .select("time, name, light_intensity, celsius_degree, humidity") \
        .eq("name", "407_aircondition") \
        .gte("time", start_time.isoformat()) \
        .order("time", desc=False) \
        .execute()

    df = pd.DataFrame(response.data)
    df["time"] = pd.to_datetime(df["time"])
    return df.dropna()

df_407 = load_data_407()

# ========== 畫面與圖表 ==========

st.title("🌱 407 空氣品質即時概況")
# 取最後一筆資料
latest = df_407.iloc[-1]
st.markdown(f"📅 最新資料時間：{latest['time'].strftime('%Y-%m-%d %H:%M:%S')}")

# 以 HTML + CSS 呈現卡片
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
        <div class="card brown">
            <div class="label">Light intensity</div>
            <div class="value">{latest["light_intensity"]} lux</div>
        </div>
        <div class="card yellow">
            <div class="label">Temp</div>
            <div class="value">{latest["celsius_degree"]:.1f}°C</div>
        </div>
        <div class="card blue">
            <div class="label">Humidity</div>
            <div class="value">{latest["humidity"]:.0f}%</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

st.title("🌱 407 環境感測看板")

fig, axs = plt.subplots(1, 3, figsize=(18, 6))

# light
axs[0].plot(df_407["time"], df_407["light_intensity"], marker='o', color='brown')
axs[0].set_title("Light intensity")
axs[0].set_ylabel("lux")
axs[0].tick_params(axis='x', rotation=45)

# Temperature
axs[1].plot(df_407["time"], df_407["celsius_degree"], marker='o', color='gold')
axs[1].set_title("Temperature")
axs[1].set_ylabel("°C")
axs[1].tick_params(axis='x', rotation=45)

# Humidity
axs[2].plot(df_407["time"], df_407["humidity"], marker='o', color='blue')
axs[2].set_title("Humidity")
axs[2].set_ylabel("%")
axs[2].tick_params(axis='x', rotation=45)



plt.tight_layout()
st.pyplot(fig)


#=========================================================
# ========== 資料抓取 ==========
@st.cache_data(ttl=60)  # 每1分鐘更新
def load_data_outdoor():
    now = datetime.now(timezone(timedelta(hours=8)))
    start_time = now - timedelta(hours=24)

    response = supabase.table("wiolink") \
        .select("time, name, celsius_degree, humidity, pm1_0_atm, pm2_5_atm,  pm10_atm") \
        .eq("name", "pm2.5") \
        .gte("time", start_time.isoformat()) \
        .order("time", desc=False) \
        .execute()

    df = pd.DataFrame(response.data)
    df["time"] = pd.to_datetime(df["time"])
    return df.dropna()

df_outdoor = load_data_outdoor()

st.title("🌱 6樓 戶外空氣品質即時概況")

# 取最後一筆資料
latest = df_outdoor.iloc[-1]
st.markdown(f"📅 最新資料時間：{latest['time'].strftime('%Y-%m-%d %H:%M:%S')}")

# 即時數據卡片呈現
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
    .red {{ background-color: #e53935; }}
    .pink {{ background-color: #d81b60; }}
    .purple {{ background-color: #8e24aa; }}
    .yellow {{ background-color: #FFC107; color: black; }}
    .blue {{ background-color: #2196F3; }}
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
        <div class="card red">
            <div class="label">PM1.0</div>
            <div class="value">{latest["pm1_0_atm"]} μg/m³</div>
        </div>
        <div class="card pink">
            <div class="label">PM2.5</div>
            <div class="value">{latest["pm2_5_atm"]} μg/m³</div>
        </div>
        <div class="card purple">
            <div class="label">PM10</div>
            <div class="value">{latest["pm10_atm"]} μg/m³</div>
        </div>
        <div class="card yellow">
            <div class="label">Temp</div>
            <div class="value">{latest["celsius_degree"]:.1f}°C</div>
        </div>
        <div class="card blue">
            <div class="label">Humidity</div>
            <div class="value">{latest["humidity"]:.0f}%</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

st.title("🌱 6樓 戶外感測看板")

fig, axs = plt.subplots(2, 3, figsize=(18, 10))

# PM1.0
axs[0, 0].plot(df_outdoor["time"], df_outdoor["pm1_0_atm"], marker='o', color='red')
axs[0, 0].set_title("PM1.0")
axs[0, 0].set_ylabel("μg/m³")
axs[0, 0].tick_params(axis='x', rotation=45)

# PM2.5
axs[0, 1].plot(df_outdoor["time"], df_outdoor["pm2_5_atm"], marker='o', color='pink')
axs[0, 1].set_title("PM2.5")
axs[0, 1].set_ylabel("μg/m³")
axs[0, 1].tick_params(axis='x', rotation=45)

# PM10
axs[0, 2].plot(df_outdoor["time"], df_outdoor["pm10_atm"], marker='o', color='purple')
axs[0, 2].set_title("PM10")
axs[0, 2].set_ylabel("μg/m³")
axs[0, 2].tick_params(axis='x', rotation=45)

# Temperature
axs[1, 0].plot(df_outdoor["time"], df_outdoor["celsius_degree"], marker='o', color='gold')
axs[1, 0].set_title("Temperature")
axs[1, 0].set_ylabel("°C")
axs[1, 0].tick_params(axis='x', rotation=45)

# Humidity
axs[1, 1].plot(df_outdoor["time"], df_outdoor["humidity"], marker='o', color='blue')
axs[1, 1].set_title("Humidity")
axs[1, 1].set_ylabel("%")
axs[1, 1].tick_params(axis='x', rotation=45)

# Empty (可放置其他指標或隱藏)
axs[1, 2].axis('off')

plt.tight_layout()
st.pyplot(fig)

#===========================================
