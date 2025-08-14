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
        .select("time, name, pm1_0_atm,pm2_5_atm, pm10_atm, mag_approach") \
        .eq("name", "wiolink window") \
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

# 窗戶狀態轉文字與 emoji
window_state_val = latest_pm.get("mag_approach")
if window_state_val in [1, True]:
    window_status = "Closed"
else:
    window_status = "Open"
    
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
        <div class="card darkblue">
            <div class="label">Window </div>
            <div class="value">{window_status} </div>
        </div>

    </div>
    """,
    unsafe_allow_html=True
)

#=================================================

st.subheader("🌱 臺灣室內空氣品質標準")

# ========= 門檻 =========
THRESHOLDS = {
    "co2eq_ppm_8h": 1000,
    "tvoc_ppm_1h": 0.56,
    "pm25_ug_24h": 35,
    "pm10_ug_24h": 75,
}

WARN_RATIO = 0.8  # 警告比例

def latest_window_avg(df, col, hours, unit_conv=None):
    if df.empty:
        return None

    s = df.copy()
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
    if value is None:
        st.info(f"{label}：近 {unit} 無足夠資料。")
        return

    if value > limit:
        st.error(f"⚠️ {label} 超標：{value:.2f}（標準 {limit}）")
    elif value > WARN_RATIO * limit:
        st.warning(f"⚠️ {label} 接近上限：{value:.2f}（標準 {limit}）")
    else:
        st.success(f"✅ {label} 正常：{value:.2f}（標準 {limit}）")

# 假設：
# df     : 604_air_quality（含 co2eq、total_voc）
# df_pm  : 604_pm2.5（含 pm2_5_atm、pm10_atm）

avg_co2_8h = latest_window_avg(df, "co2eq", hours=8)
badge(avg_co2_8h, THRESHOLDS["co2eq_ppm_8h"], "CO₂（8小時平均，ppm）", "8 小時")

avg_tvoc_1h = latest_window_avg(df, "total_voc", hours=1, unit_conv=lambda s: s / 1000.0)
badge(avg_tvoc_1h, THRESHOLDS["tvoc_ppm_1h"], "TVOC（1小時平均，ppm）", "1 小時")

avg_pm25_24h = latest_window_avg(df_pm, "pm2_5_atm", hours=24)
badge(avg_pm25_24h, THRESHOLDS["pm25_ug_24h"], "PM2.5（24小時平均，μg/m³）", "24 小時")

avg_pm10_24h = latest_window_avg(df_pm, "pm10_atm", hours=24)
badge(avg_pm10_24h, THRESHOLDS["pm10_ug_24h"], "PM10（24小時平均，μg/m³）", "24 小時")

# 顯示平均時間
if not df.empty:
    latest_time = df["time"].iloc[-1]
    st.caption(f"📅 平均計算截至：{latest_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
#==================================================================================
# ==================== IAQI 指數計算區塊 ====================

# IAQI 分類表（來源：atmotube.com）
IAQI_BREAKPOINTS = {
    "co2eq": [
        (400, 599, 81, 100),
        (600, 999, 61, 80),
        (1000, 1499, 41, 60),
        (1500, 2499, 21, 40),
        (2500, 4000, 0, 20),
    ],
    "total_voc": [
        (0.0, 0.05, 81, 100),
        (0.06, 0.1, 61, 80),
        (0.11, 0.3, 41, 60),
        (0.31, 0.75, 21, 40),
        (0.76, 1.0, 0, 20),
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
    """
    根據圖中 TVOC 分類表，直接對應 IAQI 分數（不套用 IAQI 插值公式）
    """
    if tvoc_ppm <= 0.065:
        return 100  # Excellent
    elif tvoc_ppm <= 0.22:
        return 80   # Good
    elif tvoc_ppm <= 0.66:
        return 60   # Moderate
    elif tvoc_ppm <= 2.2:
        return 40   # Poor
    elif tvoc_ppm <= 5.5:
        return 20   # Unhealthy
    else:
        return 10   # Dangerously high

def calculate_iaqi(value, breakpoints):
    """依據 IAQI 分段與公式計算單一項目的 IAQI"""
    for bp_lo, bp_hi, i_lo, i_hi in breakpoints:
        if bp_lo <= value <= bp_hi:
            return (i_hi - i_lo) / (bp_hi - bp_lo) * (value - bp_lo) + i_lo
    return None


# 取得最新資料（ppb 轉 ppm）
co2_val = df["co2eq"].iloc[-1]
tvoc_val = df["total_voc"].iloc[-1] / 1000  # ppb → ppm
pm1_val = df_pm["pm1_0_atm"].iloc[-1]
pm25_val = df_pm["pm2_5_atm"].iloc[-1]
pm10_val = df_pm["pm10_atm"].iloc[-1]


# 各項 IAQI
iaqi_co2 = calculate_iaqi(co2_val, IAQI_BREAKPOINTS["co2eq"])
iaqi_tvoc = calculate_iaqi_tvoc_simple(tvoc_val)
iaqi_pm1 = calculate_iaqi(pm10_val, IAQI_BREAKPOINTS["pm1_0_atm"])
iaqi_pm25 = calculate_iaqi(pm25_val, IAQI_BREAKPOINTS["pm2_5_atm"])
iaqi_pm10 = calculate_iaqi(pm10_val, IAQI_BREAKPOINTS["pm10_atm"])


# 最終 IAQI：取最小值（代表最差）
iaqi_final = min(filter(None, [iaqi_co2, iaqi_tvoc, iaqi_pm1, iaqi_pm25, iaqi_pm10]))

# 分類文字
def iaqi_label(score):
    if score is None:
        return "❓ 未定義"
    if score >= 81:
        return "🔵 良好"
    elif score >= 61:
        return "🟢 普通"
    elif score >= 41:
        return "🟡 輕度污染"
    elif score >= 21:
        return "🟠 中度污染"
    else:
        return "🔴 嚴重污染"

# 顯示 IAQI 結果
st.subheader("🌈 室內空氣品質 IAQI 指數")
st.markdown(f"""
- tVOC IAQ : {iaqi_label(iaqi_tvoc)} , tVOC : {tvoc_val}
- CO2 IAQI : {iaqi_co2:.1f} , {iaqi_label(iaqi_co2)} , CO2 : {co2_val}
- PM1.0 IAQI : {iaqi_pm1:.1f} , {iaqi_label(iaqi_pm1)} , PM2.5 : {pm1_val}
- PM2.5 IAQI : {iaqi_pm25:.1f} , {iaqi_label(iaqi_pm25)} , PM2.5 : {pm25_val}
- PM10 IAQI : {iaqi_pm10:.1f} , {iaqi_label(iaqi_pm10)} , PM10 : {pm10_val}
- **綜合IAQI 分數：** {iaqi_final:.1f}
- **等級分類：** {iaqi_label(iaqi_final)}
""")
st.image("https://cdn.prod.website-files.com/5f23e100544c90c140f34325/67ae00f27393a15e23104e7d_6284b21bc2130b8160d3cac5_25.jpeg", use_container_width=True)
st.image("https://cdn.prod.website-files.com/5f23e100544c90c140f34325/68948e3f0fe25227203a2692_IAQI.png", use_container_width=True)

# 熱舒適度 =============================================================================
# 以下程式碼為新增區塊：根據用戶環境使用 pythermalcomfort 套件計算熱舒適度 PMV 與 PPD

from pythermalcomfort.models import pmv_ppd_ashrae
from pythermalcomfort.utilities import v_relative, clo_dynamic_ashrae

# 提取氣候參數
ta = latest["celsius_degree"]       # Operative temperature (室內操作溫度)
tr = ta                             # 假設輻射溫度與操作溫度相同（可再補充感測資料）
v = 0.1                           # 室內氣流速度，假設為 0.1 m/s
rh = latest["humidity"]            # 相對濕度 %
met = 1.1                          # 代謝率：電腦教室打字
clo = 0.5                          # 衣著隔熱（夏季短袖、大學生）

# calculate relative air speed
v_r = v_relative(v=v, met=met)
# calculate dynamic clothing
clo_d = clo_dynamic_ashrae(clo=clo, met=met)

# 計算 PMV 與 PPD
results = pmv_ppd_ashrae(tdb=ta, tr=tr, vr=v_r, rh=rh, met=met, clo=clo_d, model="55-2023")

pmv = results.pmv
ppd = results.ppd

# 舒適程度標籤
def comfort_label(pmv_val):
    if pmv_val <= -2.5 :
        return "Cold 冷死了"
    elif pmv_val <= -1.5:
        return "Cool 很冷"
    elif pmv_val <= -0.5:
        return "Slightly cool 稍微冷"
    elif pmv_val <= 0.5:
        return "Neutral 舒適"
    elif pmv_val <= 1.5:
        return "Slightly warm 稍微熱"
    elif pmv_val <= 2.5:
        return "Warm 很熱"
    else:
        return "Hot 熱死了"

hot_comfort_label = comfort_label(pmv)

# 顯示結果
st.subheader("🌡️ 熱舒適度評估 (PMV/PPD)")
st.markdown(f"""
- **PMV 指數**：{pmv:.2f}  （ 建議範圍：-0.5 ~ +0.5 ） 
- **熱感分類 Thermal sensation**：{hot_comfort_label}
- **PPD 不滿意比例**：{ppd:.1f}% (約有 {ppd:.1f}% 人感到熱不適) ( 建議範圍： ≤ 20% )
- 參數使用：
    - 操作溫度 Operative temperature：{ta} °C
    - 相對濕度 Relative humidity：{rh:.0f} %
    - 氣流速度 Air speed：{v} m/s
    - 代謝率 Metabolic rate：{met} met (Typing : 坐著用電腦打字、文書工作)
    - 衣著隔熱 Clothing level：{clo} clo (夏季短袖長褲)
""")
st.image("https://www.simscale.com/wp-content/uploads/2019/09/pmv_ppd-1.png", use_container_width=True)	
#=============================================================================

# 604 溫度熱力圖========================================
import matplotlib.colors as mcolors
# 感測器固定座標
sensor_coord_map = {
    "wiolink window": [180, 0],
    "wiolink wall": [688, 215],
    "wiolink door": [500, 678],
    "604_air_quality": [0, 305],
    "604_center" : [300,400]
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
#------------------------------------------------------------------------------


sensor_short_name = {
    "wiolink window": "Window",
    "wiolink door": "Door",
    "wiolink wall": "Wall",
    "604_air_quality": "iMac",
    "604_pm2.5" : "PM2.5"
}
df["short_name"] = df["sensor_name"].apply(lambda x: sensor_short_name.get(x, x))

grid_z = idw(grid_x, grid_y, points, temperatures)
#---------------------------------------------------------------------------------

humidity_values = df["humidity"].to_numpy()
grid_z_humidity = idw(grid_x, grid_y, points, humidity_values)

#-------------------------------------------------------------

# Re-import required libraries after kernel reset
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from pythermalcomfort.models import pmv_ppd_ashrae

# 補充固定參數：metabolic rate, clo, air_speed
met = 1.1   # 打字活動
clo = 0.5   # 夏季輕便服裝
v = 0.1     # # 典型空調室內風速 (m/s)
# ===== 2) 以每個感測器的溫/溼來算 PMV 與 PPD =====）
def calc_pmv_ppd(row):
    res = pmv_ppd_ashrae(tdb=row["temperature"],
                            tr=row["temperature"],
                            rh=row["humidity"],
                            vr=v_relative(v=v, met=met),
                            met=met,
                            clo=clo)
    return pd.Series({"pmv": res.pmv, "ppd": res.ppd })
    
df[["pmv", "ppd"]] = df.apply(calc_pmv_ppd, axis=1)

# ===== 3) 仍然用 PPD 做 IDW 插值（熱力圖顏色代表 PPD）=====
ppd_values = df["ppd"].to_numpy()
grid_z_ppd = idw(grid_x, grid_y, points, ppd_values)

# ===== 4) 畫 PPD 熱力圖 + 在每個感測器位置同時標註 PMV / PPD =====



#--------------------------------------------------------------
# ========= 共同：載入並固定翻轉平面圖（一次即可重用） =========
from PIL import Image
import matplotlib.image as mpimg
import numpy as np

FLOOR_PATH = "604vlab-2.png"  # 你的透明底平面圖 PNG
FLOOR_ALPHA = 0.5                         # 固定透明度
XMAX, YMAX = 688, 687

# 讀圖並固定上下翻轉（圖片原點通常在左上、熱力圖在左下）
_floor_img = Image.open(FLOOR_PATH).convert("RGBA")
_floor_img = _floor_img.transpose(Image.FLIP_TOP_BOTTOM)
_floor_arr = np.array(_floor_img)

# ========= 溫度熱力圖（底：熱力圖 → 疊：平面圖 → 點/標註） =========
fig, ax = plt.subplots(figsize=(10, 7))
# 底：溫度熱力圖
cmap_t = plt.get_cmap('RdYlBu').reversed()
norm_t = mcolors.Normalize(vmin=20, vmax=30)
img = ax.imshow(grid_z, extent=(0, XMAX, 0, YMAX), origin='lower',
                cmap=cmap_t, norm=norm_t, aspect='equal', zorder=0)
# 疊：平面圖（固定翻轉 + 固定透明度）
ax.imshow(_floor_arr, extent=(0, XMAX, 0, YMAX), origin='lower',
          alpha=FLOOR_ALPHA, zorder=1)

# 點與標註
ax.scatter(df["x"], df["y"], c='white', edgecolors='black', s=50, label='Sensors', zorder=2)
for _, row in df.iterrows():
    ax.text(row["x"]-15, row["y"]+10, f"{row['short_name']}\n{row['temperature']:.1f}°C",
            color='black', fontsize=9, weight='bold', zorder=3)

cbar = plt.colorbar(img, ax=ax, label='Temperature (°C)')
cbar.set_ticks(np.arange(20, 31, 1))
ax.set_title("Classroom 604 Temperature Heatmap over Floor Plan", pad=20)
ax.set_xlabel("X (cm)"); ax.set_ylabel("Y (cm)")
ax.set_aspect('equal', adjustable='box')
ax.legend(loc='lower right')
plt.tight_layout()
st.title("🌡️ 604教室溫度熱力圖（含平面圖）")
st.markdown(f"📅 資料時間：{latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
st.pyplot(fig)

# ========= 濕度熱力圖 =========
fig, ax = plt.subplots(figsize=(10, 7))
cmap_h = plt.get_cmap('jet').reversed()
norm_h = mcolors.Normalize(vmin=0, vmax=100)
img = ax.imshow(grid_z_humidity, extent=(0, XMAX, 0, YMAX), origin='lower',
                cmap=cmap_h, norm=norm_h, aspect='equal', zorder=0)
ax.imshow(_floor_arr, extent=(0, XMAX, 0, YMAX), origin='lower',
          alpha=FLOOR_ALPHA, zorder=1)

ax.scatter(df["x"], df["y"], c='white', edgecolors='black', s=50, label='Sensors', zorder=2)
for _, row in df.iterrows():
    ax.text(row["x"]-15, row["y"]+10, f"{row['short_name']}\n{row['humidity']:.0f}%",
            color='black', fontsize=9, weight='bold', zorder=3)

cbar = plt.colorbar(img, ax=ax, label='Humidity (%)')
cbar.set_ticks(np.arange(0, 105, 5))
ax.set_title("Classroom 604 Humidity Heatmap over Floor Plan", pad=20)
ax.set_xlabel("X (cm)"); ax.set_ylabel("Y (cm)")
ax.set_aspect('equal', adjustable='box')
ax.legend(loc='lower right')
plt.tight_layout()
st.title("💧 604 教室溼度熱力圖（含平面圖）")
st.markdown(f"📅 資料時間：{latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
st.pyplot(fig)

# ========= PMV/PPD 熱力圖 =========
from pythermalcomfort.models import pmv_ppd_ashrae
from pythermalcomfort.utilities import v_relative

met, clo, v = 1.1, 0.5, 0.1
df[["pmv", "ppd"]] = df.apply(
    lambda r: pd.Series(
        {
            "pmv": pmv_ppd_ashrae(
                tdb=r["temperature"], tr=r["temperature"], rh=r["humidity"],
                vr=v_relative(v=v, met=met), met=met, clo=clo
            ).pmv,
            "ppd": pmv_ppd_ashrae(
                tdb=r["temperature"], tr=r["temperature"], rh=r["humidity"],
                vr=v_relative(v=v, met=met), met=met, clo=clo
            ).ppd,
        }
    ),
    axis=1,
)
# ----------------- PMV 熱力圖 -------------------
pmv_values = df["pmv"].to_numpy()
grid_z_pmv = idw(grid_x, grid_y, points, pmv_values)

fig, ax = plt.subplots(figsize=(10, 7))
cmap_pmv = plt.get_cmap('Spectral').reversed()
norm_pmv = mcolors.Normalize(vmin=-3, vmax=3)
img = ax.imshow(grid_z_pmv, extent=(0, XMAX, 0, YMAX), origin='lower',
                cmap=cmap_pmv, norm=norm_pmv, aspect='equal', zorder=0)
# 疊：平面圖
ax.imshow(_floor_arr, extent=(0, XMAX, 0, YMAX), origin='lower',
          alpha=FLOOR_ALPHA, zorder=1)

# 感測器 + PMV/PPD 標註
ax.scatter(df["x"], df["y"], c='white', edgecolors='black', s=50, label='Sensors', zorder=2)
for _, row in df.iterrows():
    ax.text(row["x"]-35, row["y"]+12, f"{row['short_name']}\nPMV={row['pmv']:.2f}",
            color="black", fontsize=9, weight="bold", zorder=3)
    
cbar = plt.colorbar(img, ax=ax, label='PMV')
cbar.set_ticks(np.arange(-3, 4, 1))
ax.set_title("Classroom 604 PMV Heatmap over Floor Plan", pad=20)
ax.set_xlabel("X (cm)"); ax.set_ylabel("Y (cm)")
ax.set_aspect('equal', adjustable='box')
ax.legend(loc='lower right')
plt.tight_layout()

st.title("🌡️ 604 教室 PMV 熱力圖（含平面圖）")
st.markdown(f"""預測平均表決 (Predicted Mean Vote，PMV)，是由丹麥學者P.O. Fanger教授於1972年所發表人體熱平衡模型，該模型用來表示人體對於環境中冷、熱的感受。""")
st.image("https://www.simscale.com/wp-content/uploads/2019/09/Artboard-1-1024x320.png", use_container_width=True)	
st.pyplot(fig)



# ----------------- PPD 熱力圖 -------------------
ppd_values = df["ppd"].to_numpy()
grid_z_ppd = idw(grid_x, grid_y, points, ppd_values)

fig, ax = plt.subplots(figsize=(10, 7))
cmap_p = plt.get_cmap('Spectral').reversed()
norm_p = mcolors.Normalize(vmin=5, vmax=50)
img = ax.imshow(grid_z_ppd, extent=(0, XMAX, 0, YMAX), origin='lower',
                cmap=cmap_p, norm=norm_p, aspect='equal', zorder=0)

# 疊：平面圖
ax.imshow(_floor_arr, extent=(0, XMAX, 0, YMAX), origin='lower',
          alpha=FLOOR_ALPHA, zorder=1)

# 感測器 + PMV/PPD 標註
ax.scatter(df["x"], df["y"], c='white', edgecolors='black', s=50, label='Sensors', zorder=2)
for _, row in df.iterrows():
    ax.text(row["x"]-35, row["y"]+12, f"PMV={row['pmv']:.2f}\nPPD={row['ppd']:.1f}%",
            color="black", fontsize=9, weight="bold", zorder=3)

# 20% PPD 等值線（ASHRAE/ISO 推薦上限）
cs = ax.contour(grid_x, grid_y, grid_z_ppd, levels=[20], colors="red", linewidths=1.8, zorder=3)
ax.clabel(cs, inline=True, fmt="PPD=20%%", fontsize=9)

cbar = plt.colorbar(img, ax=ax, label='PPD (%)')
cbar.set_ticks(np.arange(5, 51, 5))
ax.set_title("Classroom 604 PPD Heatmap over Floor Plan", pad=20)
ax.set_xlabel("X (cm)"); ax.set_ylabel("Y (cm)")
ax.set_aspect('equal', adjustable='box')
ax.legend(loc='lower right')
plt.tight_layout()

st.title("🧊 604 教室 PPD 熱力圖（含平面圖）")
st.markdown(f"""預測不滿意百分率(Predicted Percentage of Dissa-tisfied, PPD)，表示在該PMV舒適指標中，空間內有多少百分比的人感到不舒適。""")
st.markdown(f"""為了確保符合已知標準（ASHRAE 55 和 ISO 7730）的熱舒適度，空間內所有佔用區域的 PPD 值應保持在 20% 以下。""")
st.image("https://www.simscale.com/wp-content/uploads/2019/09/pmv_ppd-1.png", use_container_width=True)	
st.pyplot(fig)


# 604 溫溼度熱力圖 END========================================

#=========================================================
# ========== 資料抓取 ==========
@st.cache_data(ttl=60)  # 每1分鐘更新
def load_data_outdoor():
    now = datetime.now(timezone(timedelta(hours=8)))
    start_time = now - timedelta(hours=24)

    response = supabase.table("wiolink") \
        .select("time, name, celsius_degree, humidity, pm1_0_atm, pm2_5_atm,  pm10_atm") \
        .eq("name", "604_outdoor") \
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


#==========VOC and CO2 長期趨勢圖======================================================
# ---------- 資料抓取函式 ----------
@st.cache_data(ttl=60)  # 每1分鐘更新一次
# ---------- CO2 & VOC：最近 10 天 ----------
@st.cache_data(ttl=60)
def load_co2_data(days=10):
    from datetime import datetime, timedelta, timezone
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(days=days)
    start_iso = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso   = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    resp = (
        supabase.table("wiolink")
        .select("time, name, co2eq, total_voc")
        .eq("name", "604_air_quality")
        .gte("time", start_iso)   # 最近 10 天（UTC）
        .lte("time", end_iso)
        .order("time", desc=False)
        .execute()
    )
    df = pd.DataFrame(resp.data)
    if df.empty:
        return df

    # 轉當地時區顯示（台北）
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert("Asia/Taipei")
    df["co2eq"] = pd.to_numeric(df["co2eq"], errors="coerce")
    df["total_voc"] = pd.to_numeric(df["total_voc"], errors="coerce")
    return df.dropna(subset=["co2eq"]).sort_values("time")


# ---------- 畫面與圖表 ----------
st.title("🌿 604 長期趨勢圖")

df = load_co2_data(days=10)         # ← 這裡就是 10 天

fig = px.line(
    data_frame=df,
    x="time",
    y="co2eq",
    title="604 教室 CO₂ 濃度變化趨勢",
    labels={"co2eq": "CO₂ (ppm)", "time": "時間"},
    height=500
)
# 加上 1000 ppm 的警戒線
fig.add_hline(
    y=1000,
    line_dash="dash",
    line_color="red",
    annotation_text="警戒值：1000 ppm",
    annotation_position="top left"
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

# 加上 560 ppb 的警戒線（= 0.56 ppm）
fig.add_hline(
    y=560,
    line_dash="dash",
    line_color="red",
    annotation_text="警戒值：560 ppb",
    annotation_position="top left"
)

st.plotly_chart(fig, use_container_width=True)
#------------------------------------------------------

# -------- PM 資料抓取與圖表（穩定版） ----------
# ---------- PM：最近 10 天 ----------
@st.cache_data(ttl=60)
def load_pm_data(table_name="wiolink", device_name="wiolink window", days=10):
    from datetime import datetime, timedelta, timezone
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(days=days)
    start_iso = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso   = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    resp = (
        supabase.table(table_name)
        .select("time, name, pm1_0_atm, pm2_5_atm, pm10_atm")
        .eq("name", device_name)
        .gte("time", start_iso)   # 最近 10 天（UTC）
        .lte("time", end_iso)
        .order("time", desc=False)
        .execute()
    )
    df = pd.DataFrame(resp.data)
    if df.empty:
        return df

    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert("Asia/Taipei")
    for col in ["pm1_0_atm", "pm2_5_atm", "pm10_atm"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df[df[col].notna()]
            df = df[df[col] >= 0]  # 若 0 是錯誤碼可改成 > 0
    return df.sort_values("time")


df_pm = load_pm_data(days=10)       # ← 這裡也是 10 天


# 防呆
if df_pm.empty:
    st.warning("PM 資料為空，請確認表名/欄位或時間篩選是否正確。")
else:
    # PM1.0
    fig = px.line(
        df_pm, x="time", y="pm1_0_atm",
        title="604 教室 PM1.0 濃度變化趨勢",
        labels={"pm1_0_atm": "PM1.0 (μg/m³)", "time": "時間"},
        height=420
    )
    fig.update_traces(mode="lines+markers")
    st.plotly_chart(fig, use_container_width=True)

    # PM2.5
    fig = px.line(
        df_pm, x="time", y="pm2_5_atm",
        title="604 教室 PM2.5 濃度變化趨勢",
        labels={"pm2_5_atm": "PM2.5 (μg/m³)", "time": "時間"},
        height=420
    )
    fig.update_traces(mode="lines+markers")
    fig.add_hline(y=35, line_dash="dash", line_color="red",
                  annotation_text="警戒值：35 μg/m³（24h平均）",
                  annotation_position="top left")
    st.plotly_chart(fig, use_container_width=True)

    # PM10
    fig = px.line(
        df_pm, x="time", y="pm10_atm",
        title="604 教室 PM10 濃度變化趨勢",
        labels={"pm10_atm": "PM10 (μg/m³)", "time": "時間"},
        height=420
    )
    fig.update_traces(mode="lines+markers")
    fig.add_hline(y=75, line_dash="dash", line_color="red",
                  annotation_text="警戒值：75 μg/m³（24h平均）",
                  annotation_position="top left")
    st.plotly_chart(fig, use_container_width=True)

#=========================================================
