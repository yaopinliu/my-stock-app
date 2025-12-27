import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 頁面優化
st.set_page_config(page_title="全球投資回測 Pro", layout="centered")

st.markdown("# 📈 全球投資回測系統")
st.caption("支援美、台、英股 | 換匯台幣 | 股息再投資")

# --- 2. 投資參數設定 (Form 表單) ---
with st.form("investment_settings"):
    st.subheader("🛠️ 投資配置設定")
    num_assets = st.number_input("標的數量", min_value=1, max_value=20, value=1, step=1)
    
    tickers = []
    weights = []
    
    st.markdown("##### 股票與權重設定")
    for i in range(int(num_assets)):
        c1, c2 = st.columns([3, 2])
        # 預設值給 VOO 或 0050.TW
        default_t = "0050.TW" if i == 0 else ""
        t = c1.text_input(f"代碼 {i+1}", value=default_t, key=f"t{i}").upper().strip()
        w = c2.number_input(f"權重 %", value=100//int(num_assets), key=f"w{i}")
        if t:
            tickers.append(t)
            weights.append(w / 100)

    st.divider()
    st.subheader("💰 投入金額與時間")
    c_date, c_init, c_mon = st.columns([1, 1, 1])
    start_date = c_date.date_input("開始日期", datetime(2018, 12, 1))
    initial_cash = c_init.number_input("首筆投入 (TWD)", value=3000)
    monthly_invest = c_mon.number_input("每月扣款 (TWD)", value=3000)

    submit_button = st.form_submit_button("🚀 開始執行回測")

# --- 3. 強化版數據抓取函數 ---
@st.cache_data(ttl=86400)
def get_global_data_robust(tickers, start):
    needed = set(tickers)
    for t in tickers:
        if t and ".TW" not in t and ".TWO" not in t:
            needed.add("GBPTWD=X" if ".L" in t else "TWD=X")
    
    # 下載完整數據
    raw_data = yf.download(list(needed), start=start, threads=True, progress=False)
    
    if raw_data.empty:
        return None

    # 處理 yfinance 回傳結構問題 (核心修正處)
    if len(needed) > 1:
        # 多標的情況，選取 Adj Close 層
        data = raw_data['Adj Close']
    else:
        # 單一標的情況，直接檢查是否有 Adj Close 欄位
        if 'Adj Close' in raw_data.columns:
            data = raw_data[['Adj Close']]
            data.columns = list(needed) # 重新命名欄位為代碼
        else:
            # 備援方案：如果沒有 Adj Close 則取 Close
            data = raw_data[['Close']]
            data.columns = list(needed)
            
    return data.ffill().dropna()

# --- 4. 運算區 ---
if submit_button:
    if not tickers:
        st.error("請輸入至少一個標的代碼！")
    elif abs(sum(weights) - 1.0) > 0.05:
        st.error(f"❌ 總權重必須約為 100% (目前為 {sum(weights)*100:.1f}%)")
    else:
        try:
            with st.status("⚡ 正在從全球交易所同步數據...", expanded=False) as status:
                prices_df = get_global_data_robust(tickers, start_date)
                if prices_df is None:
                    st.error("抓不到資料，請檢查代碼是否正確或是網路問題。")
                    st.stop()
                status.update(label="✅ 數據抓取完成", state="complete")
            
            # 換匯與對齊
            adj_df = pd.DataFrame(index=prices_df.index)
            for t in tickers:
                if t in prices_df.columns:
                    if ".TW" in t or ".TWO" in t:
                        adj_df[t] = prices_df[t]
                    elif ".L" in t:
                        adj_df[t] = prices_df[t] * prices_df["GBPTWD=X"]
                    else:
                        adj_df[t] = prices_df[t] * prices_df["TWD=X"]
            
            # 計算回測
            rets = adj_df.pct_change().dropna()
            # 確保權重與欄位對齊
            final_weights = [weights[tickers.index(c)] for c in adj_df.columns]
            p_ret = (rets * final_weights).sum(axis=1)

            val, cost, last_m = initial_cash, initial_cash, -1
            v_hist, c_hist = [], []
            
            for d, r in p_ret.items():
                if d.month != last_m:
                    val += monthly_invest
                    cost += monthly_invest
                    last_m = d.month
                val *= (1 + r)
                v_hist.append(val)
                c_hist.append(cost)

            # --- 顯示圖表 ---
            st.divider()
            v_f, c_f = v_hist[-1], c_hist[-1]
            roi = ((v_f / c_f) - 1) * 100
            
            m1, m2, m3 = st.columns(3)
            m1.metric("資產現值 (TWD)", f"${v_f:,.0f}")
            m2.metric("累積投入本金", f"${c_f:,.0f}")
            m3.metric("總報酬率", f"{roi:.2f}%")

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=p_ret.index, y=v_hist, name="總價值", fill='tozeroy'))
            fig.add_trace(go.Scatter(x=p_ret.index, y=c_hist, name="投入本金", line=dict(dash='dash')))
            st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"運算發生問題：{e}")
            st.info("提示：如果出現 'Adj Close' 錯誤，請確認標代碼格式是否正確（例如台股要加 .TW）。")
