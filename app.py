import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 頁面優化 (手機版自動適應)
st.set_page_config(page_title="全球投資回測 Pro", layout="centered")

st.markdown("# 📈 全球投資回測系統")
st.caption("支援美、台、英股 | 換匯台幣 | 股息再投資")

# --- 2. 核心設定區 (置頂顯示，確保 iPhone 看得到) ---
with st.container():
    st.subheader("🛠️ 投資配置設定")
    num_assets = st.number_input("標的數量", min_value=1, max_value=20, value=2, step=1)
    
    tickers = []
    weights = []
    
    # 使用 Expander 節省手機空間
    with st.expander("點擊展開：設定股票與比例", expanded=True):
        for i in range(int(num_assets)):
            c1, c2 = st.columns([3, 2])
            t = c1.text_input(f"代碼 {i+1}", value="VOO" if i==0 else "2330.TW", key=f"t{i}").upper()
            w = c2.number_input(f"權重 %", value=100//int(num_assets), key=f"w{i}")
            tickers.append(t)
            weights.append(w / 100)

    with st.expander("💰 點擊展開：設定投入金額"):
        start_date = st.date_input("開始日期", datetime.now() - timedelta(days=365*5))
        initial_cash = st.number_input("首筆投入 (TWD)", value=100000)
        monthly_invest = st.number_input("每月扣款 (TWD)", value=10000)

# --- 3. 數據抓取邏輯 ---
@st.cache_data(ttl=86400)
def get_stock_data(tickers, start):
    needed = set(tickers)
    for t in tickers:
        if ".TW" not in t and ".TWO" not in t:
            needed.add("GBPTWD=X" if ".L" in t else "TWD=X")
    data = yf.download(list(needed), start=start)['Adj Close']
    if isinstance(data, pd.Series): 
        data = data.to_frame(name=list(needed)[0])
    return data.ffill().dropna()

# --- 4. 運算與繪圖 ---
try:
    if abs(sum(weights) - 1.0) > 0.01:
        st.error(f"❌ 總權重必須為 100% (目前為 {sum(weights)*100:.1f}%)")
    else:
        with st.spinner('計算中...'):
            raw_df = get_stock_data(tickers, start_date)
            
            # 換匯計算
            adj_df = pd.DataFrame(index=raw_df.index)
            for t in tickers:
                if ".TW" in t or ".TWO" in t:
                    adj_df[t] = raw_df[t]
                elif ".L" in t:
                    adj_df[t] = raw_df[t] * raw_df["GBPTWD=X"]
                else:
                    adj_df[t] = raw_df[t] * raw_df["TWD=X"]
            
            # 報酬率
            rets = adj_df.pct_change().dropna()
            # 確保欄位順序正確
            ordered_weights = [weights[tickers.index(c)] for c in adj_df.columns]
            p_ret = (rets * ordered_weights).sum(axis=1)

            # 滾動資產價值
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

            # 數據儀表板
            st.divider()
            v_final, c_final = v_hist[-1], c_hist[-1]
            roi = ((v_final / c_final) - 1) * 100
            
            m1, m2 = st.columns(2)
            m1.metric("資產現值 (TWD)", f"${v_final:,.0f}")
            m1.metric("總報酬率", f"{roi:.2f}%")
            m2.metric("累計成本", f"${c_final:,.0f}")
            m2.metric("獲利總額", f"${v_final-c_final:,.0f}")

            # 歷史圖表
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=p_ret.index, y=v_hist, name="總價值", fill='tozeroy'))
            fig.add_trace(go.Scatter(x=p_ret.index, y=c_hist, name="投入本金", line=dict(dash='dash')))
            fig.update_layout(height=350, margin=dict(l=0,r=0,t=10,b=0), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)

            # 蒙地卡羅
            if st.checkbox("🔮 顯示未來一年風險模擬"):
                mu, std = p_ret.mean(), p_ret.std()
                f2 = go.Figure()
                for _ in range(15):
                    p = [v_final]
                    for _ in range(252): p.append(p[-1]*(1+np.random.normal(mu, std)))
                    f2.add_trace(go.Scatter(y=p, mode='lines', opacity=0.3, showlegend=False))
                f2.update_layout(height=250)
                st.plotly_chart(f2, use_container_width=True)

except Exception as e:
    st.info("💡 請輸入代碼並等待數據載入 (美股 AAPL, 台股 0050.TW)")