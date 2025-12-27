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
    
    ticker_inputs = []
    weight_inputs = []
    
    st.markdown("##### 股票與權重設定")
    for i in range(int(num_assets)):
        c1, c2 = st.columns([3, 2])
        default_t = "0050.TW" if i == 0 else ""
        t = c1.text_input(f"代碼 {i+1}", value=default_t, key=f"t{i}").upper().strip()
        w = c2.number_input(f"權重 %", value=100//int(num_assets), key=f"w{i}")
        ticker_inputs.append(t)
        weight_inputs.append(w)

    st.divider()
    st.subheader("💰 投入金額與時間")
    c_date, c_init, c_mon = st.columns([1, 1, 1])
    # 設定預設開始日期為 2018/12/01
    start_date = c_date.date_input("開始日期", datetime(2018, 12, 1))
    initial_cash = c_init.number_input("首筆投入 (TWD)", value=3000)
    monthly_invest = c_mon.number_input("每月扣款 (TWD)", value=3000)

    submit_button = st.form_submit_button("🚀 開始執行回測")

# --- 3. 核心數據處理 (徹底修復 Adj Close 錯誤) ---
def safe_get_prices(tickers, start):
    # 準備所有代碼 (包含匯率)
    needed = []
    for t in tickers:
        if t:
            needed.append(t)
            if ".TW" not in t and ".TWO" not in t:
                needed.append("GBPTWD=X" if ".L" in t else "TWD=X")
    
    needed = list(set(needed))
    # 強制一次抓取所有數據
    raw = yf.download(needed, start=start, progress=False, threads=True)
    
    if raw.empty:
        return None

    # 自動識別欄位結構
    final_prices = pd.DataFrame()
    
    for t in needed:
        try:
            # 如果是多層索引 (MultiIndex)
            if isinstance(raw.columns, pd.MultiIndex):
                if 'Adj Close' in raw.columns.levels[0] and t in raw['Adj Close'].columns:
                    final_prices[t] = raw['Adj Close'][t]
                else:
                    final_prices[t] = raw['Close'][t]
            # 如果是普通索引
            else:
                if 'Adj Close' in raw.columns:
                    final_prices[t] = raw['Adj Close']
                else:
                    final_prices[t] = raw['Close']
        except:
            continue
            
    return final_prices.ffill().dropna()

# --- 4. 運算區 ---
if submit_button:
    # 過濾有效輸入
    valid_tickers = [t for t in ticker_inputs if t]
    valid_weights = [weight_inputs[i]/100 for i, t in enumerate(ticker_inputs) if t]

    if not valid_tickers:
        st.error("請輸入有效代碼")
    elif abs(sum(valid_weights) - 1.0) > 0.05:
        st.error(f"❌ 權重總和必須約為 100% (目前: {sum(valid_weights)*100:.1f}%)")
    else:
        try:
            with st.status("⚡ 正在同步全球數據...", expanded=False):
                price_table = safe_get_prices(valid_tickers, start_date)
            
            if price_table is None or price_table.empty:
                st.error("找不到資料，請確認代碼是否正確 (例如台股需加 .TW)")
                st.stop()

            # 匯率轉換與資產價值對齊
            adj_p = pd.DataFrame(index=price_table.index)
            for t in valid_tickers:
                if t in price_table.columns:
                    if ".TW" in t or ".TWO" in t:
                        adj_p[t] = price_table[t]
                    elif ".L" in t:
                        adj_p[t] = price_table[t] * price_table["GBPTWD=X"]
                    else:
                        adj_p[t] = price_table[t] * price_table["TWD=X"]

            # 計算日報酬與權重加總
            rets = adj_p.pct_change().dropna()
            # 確保標的與權重對應正確
            p_weights = [valid_weights[valid_tickers.index(c)] for c in adj_p.columns]
            portfolio_ret = (rets * p_weights).sum(axis=1)

            # 複利計算
            val, cost, last_m = initial_cash, initial_cash, -1
            v_hist, c_hist = [], []
            for d, r in portfolio_ret.items():
                if d.month != last_m:
                    val += monthly_invest
                    cost += monthly_invest
                    last_m = d.month
                val *= (1 + r)
                v_hist.append(val)
                c_hist.append(cost)

            # --- 儀表板顯示 ---
            st.divider()
            v_f, c_f = v_hist[-1], c_hist[-1]
            total_roi = ((v_f / c_f) - 1) * 100
            
            m1, m2, m3 = st.columns(3)
            m1.metric("資產現值 (TWD)", f"${v_f:,.0f}")
            m2.metric("累積投入本金", f"${c_f:,.0f}")
            m3.metric("總報酬率", f"{total_roi:.2f}%")

            # 走勢圖
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=portfolio_ret.index, y=v_hist, name="資產價值", fill='tozeroy', line=dict(color='#00d1b2')))
            fig.add_trace(go.Scatter(x=portfolio_ret.index, y=c_hist, name="累計成本", line=dict(dash='dash', color='#718096')))
            fig.update_layout(height=400, margin=dict(l=0,r=0,t=20,b=0), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"發生未預期錯誤：{e}")
