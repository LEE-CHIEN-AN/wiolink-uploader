import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client
from datetime import datetime, timedelta, timezone

# Supabase 設定
SUPABASE_URL = "https://orlmyfjhqcmlrbrlonbt.supabase.co"  # Supabase 專案網址
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ybG15ZmpocWNtbHJicmxvbmJ0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NTIwMjI1MCwiZXhwIjoyMDYwNzc4MjUwfQ.ThQYh9TgVpu9PEjuK-2Q2jaG_ewFzj4Osaq70RuH3rY"  # Supabase API 金鑰
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)  # 建立 Supabase 連線

# 資料抓取
@st.cache_data(ttl=900)  # 每15分鐘更新
def fetch_data():
    now = datetime.now(timezone(timedelta(hours=8)))
    past_72h = now - timedelta(hours=72)
    data = supabase.table("wiolink").select("*").gte("timestamp", past_72h.isoformat()).execute().data
    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["dust"] = pd.to_numeric(df["dust"], errors="coerce")
    return df.dropna(subset=["dust"])

# 介面
st.title("教室感測器資料儀表板")
df = fetch_data()
st.line_chart(df.set_index("timestamp")["dust"])
