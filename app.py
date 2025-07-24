import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import os
from supabase import create_client
from datetime import datetime, timedelta, timezone
# 字型設定（針對 Windows 中文支援）
import matplotlib

# ---------- Supabase 設定 ----------
# Supabase 設定
# === Supabase 設定（從 GitHub Secrets 環境變數取得） ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ========== 資料抓取 ==========
@st.cache_data(ttl=300)  # 每5分鐘更新
def load_data_407():
    now = datetime.now(timezone(timedelta(hours=8)))
    start_time = now - timedelta(hours=12)

    response = supabase.table("wiolink") \
        .select("time, name, co2eq, celsius_degree, humidity, total_voc") \
        .eq("name", "407_air_quality") \
        .gte("time", start_time.isoformat()) \
        .order("time", desc=False) \
        .execute()

    df = pd.DataFrame(response.data)
    df["time"] = pd.to_datetime(df["time"])
    return df.dropna()

df = load_data_407()

# ========== 畫面與圖表 ==========
st.title("🌱 407 空氣品質即時概況")

# 取最後一筆資料
latest = df.iloc[-1]

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
            <div class="value">{latest["total_voc"]}</div>
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

st.title("🌱 407 空氣品質感測看板")
fig, axs = plt.subplots(2, 2, figsize=(12, 8))

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



plt.tight_layout()
st.pyplot(fig)


#===========================================
# ========== 資料抓取 ==========
@st.cache_data(ttl=300)  # 每5分鐘更新
def load_data_604():
    now = datetime.now(timezone(timedelta(hours=8)))
    start_time = now - timedelta(hours=12)

    response = supabase.table("wiolink") \
        .select("time, name, light_intensity, celsius_degree, humidity") \
        .eq("name", "wiolink wall") \
        .gte("time", start_time.isoformat()) \
        .order("time", desc=False) \
        .execute()

    df = pd.DataFrame(response.data)
    df["time"] = pd.to_datetime(df["time"])
    return df.dropna()

df_604 = load_data_604()

# ========== 畫面與圖表 ==========

st.title("🌱 604 空氣品質即時概況")
# 取最後一筆資料
latest = df_604.iloc[-1]

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

st.title("🌱 604 環境感測看板")

fig, axs = plt.subplots(1, 3, figsize=(18, 6))

# light
axs[0].plot(df_604["time"], df_604["light_intensity"], marker='o', color='brown')
axs[0].set_title("Light intensity")
axs[0].set_ylabel("lux")
axs[0].tick_params(axis='x', rotation=45)

# Temperature
axs[1].plot(df_604["time"], df_604["celsius_degree"], marker='o', color='gold')
axs[1].set_title("Temperature")
axs[1].set_ylabel("°C")
axs[1].tick_params(axis='x', rotation=45)

# Humidity
axs[2].plot(df_604["time"], df_604["humidity"], marker='o', color='blue')
axs[2].set_title("Humidity")
axs[2].set_ylabel("%")
axs[2].tick_params(axis='x', rotation=45)



plt.tight_layout()
st.pyplot(fig)
