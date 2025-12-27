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

# --- 2. 使用 Form 封裝輸入項 (增加「開始」按鈕) ---
# 使用 form 可以防止每改一個字就重新載入，讓操作更順暢
with st.form("investment_settings"):
    st.subheader("🛠️ 投資配置設定")
    num_assets = st.number_input("標的數量", min_value=1, max_value=20, value=1, step=1)
    
    tickers = []
    weights = []
    
    # 標的輸入區
    st.markdown("##### 股票與權重設定")
    for i in range(int(num_assets)):
        c1, c2 = st.columns([3, 2])
        t = c1.text_input(f"代碼 {i+1}", value="0050.TW" if i==0 else "", key=f"t{i}").upper()
        w = c2.number_input(f"權重 %", value=100//int(num_assets), key=f"w{i}")
        tickers.append(t)
        weights.append(w / 100)

    st.divider()
    st.subheader("💰 投入金額與時間")
    c_date, c_init, c_mon = st.columns([1, 1, 1])
    start_date = c_date.date_input("開始日期", datetime(2018, 12, 1))
    initial_cash = c_init.number_input("首筆投入 (TWD)", value=3000)
    monthly_invest = c_mon.number_input("每月扣款 (TWD)", value=3000)

    # --- 關鍵：開始按鈕 ---
    submit_button = st.form_submit_button("🚀 開始執行回測")

# --- 3. 極速數據抓取邏輯 (多線程優化) ---
@st.cache_data(ttl=86400) # 快取 24 小時
def get_global_data_fast(tickers, start):
    # 整理所有需要的代碼 (股票 + 匯率)
    needed = set(tickers)
    for t in tickers:
        if t and ".TW" not in t and ".TWO" not in t:
            needed.add("GBPTWD=X" if ".L" in t else "TWD=X")
    
    # 使用 threads=True 大幅提升多標的下載速度
    data = yf.download(list(needed), start=start, threads=True, progress=False)['Adj Close']
    
    # 處理單一標的情況 (yfinance 回傳 Series 的問題)
    if isinstance(data, pd.Series): 
        data = data.to_frame(name=list(needed)[0])
    return data.ffill().dropna()

# --- 4. 點擊按鈕後才執行的運算區 ---
if submit_button:
    try:
        # 過濾空的代碼
        active_tickers = [t for t in tickers if t.strip() != ""]
        if not active_tickers:
            st.error("請至少輸入一個標的代碼！")
            st.stop()
            
        if abs(sum(weights) - 1.0) > 0.05: # 容許 5% 以內的微小誤差
            st.error(f"❌ 總權重必須約為 100% (目前為 {sum(weights)*100:.1f}%)")
        else:
            with st.status("⚡ 正在從全球交易所同步數據...", expanded=False) as status:
                raw_df = get_global_data_fast(active_tickers, start_date)
                status.update(label="✅ 數據抓取完成，計算回測中...", state="complete")
            
            # 換匯計算 (確保標的與權重對齊)
            adj_df = pd.DataFrame(index=raw_df.index)
            for t in active_tickers:
                if ".TW" in t or ".TWO" in t:
                    adj_df[t] = raw_df[t]
                elif ".L" in t:
                    adj_df[t] = raw_df[t] * raw_df["GBPTWD=X"]
                else:
                    adj_df[t] = raw_df[t] * raw_df["TWD=X"]
            
            # 報酬率運算
            rets = adj_df.pct_change().dropna()
            # 根據下載後的欄位順序重新抓權重
            ordered_weights = [weights[tickers.index(c)] for c in adj_df.columns]
            p_ret = (rets * ordered_weights).sum(axis=1)

            # 複利資產價值計算
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

            # --- 結果顯示 ---
            st.divider()
            v_final, c_final = v_hist[-1], c_hist[-1]
            roi = ((v_final / c_final) - 1) * 100
            
            m1, m2, m3 = st.columns(3)
            m1.metric("資產現值 (TWD)", f"${v_final:,.0f}")
            m2.metric("累積投入成本", f"${c_final:,.0f}")
            m3.metric("總報酬率", f"{roi:.2f}%")

            # 圖表展示
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=p_ret.index, y=v_hist, name="總價值", fill='tozeroy', line=dict(color='#00d1b2')))
            fig.add_trace(go.Scatter(x=p_ret.index, y=c_hist, name="累積投入", line=dict(dash='dash', color='#718096')))
            fig.update_layout(height=400, margin=dict(l=0,r=0,t=20,b=0), 
                              legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
            st.plotly_chart(fig, use_container_width=True)

            # 蒙地卡羅 (未來模擬)
            with st.expander("🔮 未來走勢風險模擬"):
                mu, std = p_ret.mean(), p_ret.std()
                f2 = go.Figure()
                for _ in range(15):
                    path = [v_final]
                    for _ in range(252): path.append(path[-1]*(1+np.random.normal(mu, std)))
                    f2.add_trace(go.Scatter(y=path, mode='lines', opacity=0.3, showlegend=False))
                st.plotly_chart(f2, use_container_width=True)

    except Exception as e:
        st.error(f"運算發生問題：{e}")
else:
    st.info("💡 請設定好參數後，點擊「🚀 開始執行回測」按鈕。")
