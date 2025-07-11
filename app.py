import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import os
from supabase import create_client
from datetime import datetime, timedelta, timezone
# 字型設定（針對 Windows 中文支援）
import matplotlib
matplotlib.rc('font', family='Noto Sans CJK TC')

# ---------- Supabase 設定 ----------
# Supabase 設定
# === Supabase 設定（從 GitHub Secrets 環境變數取得） ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- 讀取資料 ----------
@st.cache_data(ttl=900)  # 每5分鐘自動重新抓資料
def load_data():
    now = datetime.now(timezone(timedelta(hours=8)))
    past_72h = now - timedelta(hours=72)

    response = supabase.table("wiolink") \
        .select("*") \
        .gte("timestamp", past_72h.isoformat()) \
        .order("timestamp", desc=False) \
        .execute()

    df = pd.DataFrame(response.data)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["dust"] = pd.to_numeric(df["dust"], errors="coerce")
    df = df.dropna(subset=["timestamp", "sensor_name"])
    df = df[df["dust"] != 0.62]  # 移除異常值
    return df

df = load_data()

# ---------- Streamlit UI ----------
st.title("🌿 教室感測器資料儀表板")
st.write("資料時間範圍：最近 72 小時，每 15 分鐘更新一次。")

critical_time = pd.to_datetime("2025-07-09 13:55:00")

# ---------- 各裝置最新資料表格 ----------
st.subheader("🆕 各裝置最新一筆感測資料")
latest_df = df.sort_values(by="timestamp", ascending=False).drop_duplicates(subset=["sensor_name"])
latest_df["timestamp"] = latest_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
st.dataframe(latest_df[[
    "timestamp", "sensor_name", "humidity", "celsius_degree",
    "light_intensity", "dust", "motion_detected", "door_status"
]]) 

# 最近牆面或窗戶 dust 與濕度趨勢
latest_wall = latest_df[latest_df["sensor_name"] == "wiolink wall"]
latest_window = latest_df[latest_df["sensor_name"] == "wiolink window"]

if not latest_wall.empty and not latest_window.empty:
    dust_now = latest_wall.iloc[0]["dust"]
    humidity_now = latest_wall.iloc[0]["humidity"]
    door_status = latest_window.iloc[0]["door_status"]

    st.subheader("📡 環境狀態分析與建議")

    if dust_now > 500:
        if door_status == "closed":
            st.warning(f"🟠 目前 Dust 為 {dust_now:.1f}，空氣品質不佳，建議開窗通風！")
        else:
            st.info(f"🟢 已開窗通風中，但 Dust 數值仍高（{dust_now:.1f}），可觀察後續變化")
    elif humidity_now < 40:
        st.info(f"💧 濕度偏低（{humidity_now:.1f}%），可適度關窗避免過度乾燥")
    elif dust_now < 150 and humidity_now > 50:
        st.success(f"✅ 室內環境穩定（Dust: {dust_now:.1f}, 濕度: {humidity_now:.1f}%），維持現狀即可")

# ---------- 圖表 1：Dust ----------
st.subheader("🟤 灰塵（每公升粒子數） (pcs/0.01cf)")
fig1, ax1 = plt.subplots(figsize=(10, 6))
ax1.scatter(df[df['door_status'] == 'open']["timestamp"], df[df['door_status'] == 'open']["dust"], color="blue", label='open')
ax1.scatter(df[df['door_status'] == 'closed']["timestamp"], df[df['door_status'] == 'closed']["dust"], color="orange", label='closed')
ax1.axhline(y=np.mean(df['dust']), color='green', linestyle='--', label='mean')
ax1.set_title("Dust Last 72 hours")
ax1.set_xlabel("time")
ax1.set_ylabel("Dust (pcs/0.01cf)")
ax1.legend()
st.pyplot(fig1)

# ---------- 圖表 2：Humidity ----------
st.subheader("💧 濕度 (%)")
fig2, ax2 = plt.subplots(figsize=(10, 6))
ax2.scatter(df[df['door_status'] == 'open']["timestamp"], df[df['door_status'] == 'open']["humidity"], color="blue", label='open')
ax2.scatter(df[df['door_status'] == 'closed']["timestamp"], df[df['door_status'] == 'closed']["humidity"], color="orange", label='closed')
ax2.axhline(y=np.mean(df['humidity']), color='green', linestyle='--', label='mean')
ax2.set_title("Humidity Last 72 hours")
ax2.set_xlabel("time")
ax2.set_ylabel("Humidity (%)")
ax2.set_ylim(0, 100)
ax2.legend()
st.pyplot(fig2)

# ---------- 圖表 3：Temperature ----------
st.subheader("🌡️ 溫度 (°C)")
fig3, ax3 = plt.subplots(figsize=(10, 6))
ax3.scatter(df[df['door_status'] == 'open']["timestamp"], df[df['door_status'] == 'open']["celsius_degree"], color="blue", label='open')
ax3.scatter(df[df['door_status'] == 'closed']["timestamp"], df[df['door_status'] == 'closed']["celsius_degree"], color="orange", label='closed')
ax3.axhline(y=np.mean(df['celsius_degree']), color='green', linestyle='--', label='mean')
ax3.set_title("Temperature Last 72 hours")
ax3.set_xlabel("time")
ax3.set_ylabel("Temperature (°C)")
ax3.set_ylim(20, 35)
ax3.legend()
st.pyplot(fig3)

# ---------- 圖表 4：光照強度 ----------
st.subheader("☀️ 光照強度 (lux)")
fig4, ax4 = plt.subplots(figsize=(10, 6))
ax4.scatter(df[df['door_status'] == 'open']["timestamp"], df[df['door_status'] == 'open']["light_intensity"], color="blue", label='open')
ax4.scatter(df[df['door_status'] == 'closed']["timestamp"], df[df['door_status'] == 'closed']["light_intensity"], color="orange", label='closed')
ax4.axhline(y=np.mean(df['light_intensity']), color='green', linestyle='--', label='mean')
ax4.set_title("Light Intensity Last 72 hours")
ax4.set_xlabel("time")
ax4.set_ylabel("light intensity (lux)")
ax4.legend()
st.pyplot(fig4)




# ---------- 圖表 2：Humidity（依 sensor_name 區分） ----------
st.subheader("💧 濕度 (%)（依 sensor_name 區分）")
fig5, ax5 = plt.subplots(figsize=(10, 6))
for name, group in df.dropna(subset=["humidity"]).groupby("sensor_name"):
    ax5.plot(group["timestamp"], group["humidity"], label=name)
ax5.axhline(y=np.mean(df["humidity"]), color='red', linestyle='--', label='mean')
ax5.set_title("Humidity Last 72 hours by Sensor")
ax5.set_xlabel("time")
ax5.set_ylabel("Humidity (%)")
ax5.set_ylim(0, 100)
ax5.legend()
st.pyplot(fig5)



# ---------- 圖表 3：Temperature（依 sensor_name 區分） ----------
st.subheader("🌡️ 溫度 (°C)（依 sensor_name 區分）")
fig6, ax6 = plt.subplots(figsize=(10, 6))
for name, group in df.dropna(subset=["celsius_degree"]).groupby("sensor_name"):
    ax6.plot(group["timestamp"], group["celsius_degree"], label=name)
ax6.axhline(y=np.mean(df["celsius_degree"]), color='red', linestyle='--', label='mean')
ax6.set_title("Temperature Last 72 hours by Sensor")
ax6.set_xlabel("time")
ax6.set_ylabel("Temperature (°C)")
ax6.set_ylim(20, 35)
ax6.legend()
st.pyplot(fig6)

# ---------- 圖表 4：光照強度（依 sensor_name 區分） ----------
st.subheader("☀️ 光照強度 (lux)（依 sensor_name 區分）")
fig7, ax7 = plt.subplots(figsize=(10, 6))
for name, group in df.dropna(subset=["light_intensity"]).groupby("sensor_name"):
    ax7.plot(group["timestamp"], group["light_intensity"], label=name)
ax7.axhline(y=np.mean(df["light_intensity"]), color='red', linestyle='--', label='mean')
ax7.set_title("Light Intensity Last 72 hours by Sensor")
ax7.set_xlabel("time")
ax7.set_ylabel("light intensity (lux)")
ax7.legend()
st.pyplot(fig7)
