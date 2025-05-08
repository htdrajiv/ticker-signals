import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
import pandas as pd
import ta
import plotly.graph_objects as go
import time

# --- Signal Analyzer Function ---
def analyze_advanced_trend(ticker, period='30d', interval=None):
    if interval is None:
        interval = '1h' if period in ['7d', '15d', '30d'] else '1d'

    data = yf.download(ticker, period=period, interval=interval)
    if data.empty:
        return {"Ticker": ticker, "Error": "No data found."}

    data.dropna(inplace=True)
    close_series = pd.Series(data['Close'].values.flatten(), index=data.index)
    rsi_window = 7 if interval == '1h' else 14
    rsi_series = ta.momentum.RSIIndicator(close=close_series, window=rsi_window).rsi()

    if interval == '1h':
        macd_calc = ta.trend.MACD(close=close_series, window_slow=13, window_fast=6, window_sign=5)
    else:
        macd_calc = ta.trend.MACD(close=close_series)

    macd_series = macd_calc.macd()
    signal_series = macd_calc.macd_signal()

    data['RSI'] = rsi_series
    data['MACD'] = macd_series
    data['MACD_Signal'] = signal_series
    data['Volume_SMA'] = data['Volume'].rolling(window=5).mean()
    data.dropna(inplace=True)

    if len(data) < 2:
        return {"Ticker": ticker, "Error": "Not enough data after indicators."}

    latest = data.iloc[-1]
    prev = data.iloc[-2]

    try:
        latest_macd = float(latest['MACD'])
        latest_signal = float(latest['MACD_Signal'])
        prev_macd = float(prev['MACD'])
        prev_signal = float(prev['MACD_Signal'])

        price_trend = "Up" if float(latest['Close']) > float(prev['Close']) else "Down"
        volume_trend = "Strong" if float(latest['Volume']) > float(latest['Volume_SMA']) else "Weak"
        if latest_macd > latest_signal and prev_macd <= prev_signal:
            macd_crossover = "Bullish"
        elif latest_macd < latest_signal and prev_macd >= prev_signal:
            macd_crossover = "Bearish"
        else:
            macd_crossover = "Neutral"
    except Exception as e:
        return {"Ticker": ticker, "Error": f"Invalid comparison: {e}"}

    signals = {
        "Price Trend": price_trend,
        "Volume": volume_trend,
        "RSI": latest['RSI'],
        "MACD": latest['MACD'],
        "MACD_Signal": latest['MACD_Signal'],
        "MACD_Crossover": macd_crossover,
        "Close": latest['Close']
    }

    rsi_val = float(pd.Series(signals["RSI"]).iloc[0]) if isinstance(signals["RSI"], pd.Series) else float(signals["RSI"])

    if signals["Price Trend"] == "Up" and signals["Volume"] == "Strong" and signals["MACD_Crossover"] == "Bullish" and rsi_val < 70:
        signals["Outlook"] = "UP (Strong Buy)"
    elif signals["Price Trend"] == "Down" and signals["MACD_Crossover"] == "Bearish" and rsi_val > 30:
        signals["Outlook"] = "DOWN (Sell)"
    elif rsi_val < 30:
        signals["Outlook"] = "UP (RSI Oversold)"
    elif rsi_val > 70:
        signals["Outlook"] = "DOWN (RSI Overbought)"
    else:
        signals["Outlook"] = "NEUTRAL / Wait"

    try:
        option_chain = yf.Ticker(ticker).option_chain()
        expiry_str = option_chain.expirations[0]
        if signals["Outlook"].startswith("UP"):
            calls = option_chain.calls
            nearest_call = calls[calls['strike'] >= latest['Close']].iloc[0]
            signals["Options Strategy"] = "Buy Call or Bull Call Spread"
            signals["Example Option"] = f"Buy ${nearest_call.strike} Call expiring {expiry_str}"
        elif signals["Outlook"].startswith("DOWN"):
            puts = option_chain.puts
            nearest_put = puts[puts['strike'] <= latest['Close']].iloc[-1]
            signals["Options Strategy"] = "Buy Put or Bear Put Spread"
            signals["Example Option"] = f"Buy ${nearest_put.strike} Put expiring {expiry_str}"
        else:
            signals["Options Strategy"] = "-"
            signals["Example Option"] = "-"
    except Exception:
        signals["Options Strategy"] = "-"
        signals["Example Option"] = "Options data unavailable"

    signals["Indicator Profile"] = "Fast MACD/RSI" if interval == '1h' else "Standard MACD/RSI"

    if signals["Outlook"].startswith("UP"):
        price_target = float(signals["Close"]) * 1.05
        signals["Price Target"] = f"${price_target:.2f} (in ~7 days)"
    elif signals["Outlook"].startswith("DOWN"):
        price_target = float(signals["Close"]) * 0.95
        signals["Price Target"] = f"${price_target:.2f} (in ~7 days)"
    else:
        signals["Price Target"] = "-"

    return {"Ticker": ticker, **signals}

# --- Streamlit UI ---
st.set_page_config(page_title="Stock Signal Dashboard", layout="wide")

with st.sidebar.expander("📡 Real-Time Price Tracker", expanded=False):
    track_ticker = st.text_input("Enter Ticker Symbol (e.g., AAPL)", "AAPL")
    refresh_price = st.button("🔄 Refresh Price")
    placeholder = st.empty()
    price_chart_placeholder = st.empty()
    if refresh_price:
        with st.spinner("📈 Fetching real-time trading data..."):
            live_data = yf.download(tickers=track_ticker, period="1d", interval="1m")
            if not live_data.empty:
                current_price = live_data['Close'].iloc[-1]
                placeholder.metric(label=f"{track_ticker} Live Price", value=f"${float(current_price):.2f}")

                fig_live = go.Figure()
                fig_live.add_trace(go.Scatter(x=live_data.index, y=live_data['Close'], mode='lines', name='Live Close', line=dict(color='deepskyblue')))
                fig_live.update_layout(
                    title=f'{track_ticker} 1-min Price Chart (Live)',
                    height=300,
                    xaxis_title='Time',
                    yaxis_title='Price ($)',
                    template="plotly_white",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                price_chart_placeholder.plotly_chart(fig_live, use_container_width=True)
            else:
                placeholder.warning(f"No live data available for {track_ticker}")

st.title("📈 Multi-Ticker Stock Trend Dashboard")

tickers_input = st.text_input("Enter comma-separated tickers:", "AAPL,MSFT,GOOGL,TSLA,AMZN")
period = st.selectbox("Select period", ["7d", "15d", "30d", "50d", "90d", "180d", "1y"], index=2)

if st.button("🔍 Scan for Buy Signals") or tickers_input:
    with st.spinner("📊 Analyzing stock signals..."):
        tickers = [t.strip().upper() for t in tickers_input.split(",")]
        raw_results = [analyze_advanced_trend(t, period=period) for t in tickers]
        df = pd.DataFrame(raw_results)

    success_df = df[df['Outlook'].notna()] if 'Outlook' in df.columns else pd.DataFrame()
    error_df = df[df['Error'].notna()] if 'Error' in df.columns else pd.DataFrame()

    if not success_df.empty:
        buy_df = success_df[success_df['Outlook'].str.contains("Buy|Oversold", na=False)]
        sell_df = success_df[success_df['Outlook'].str.contains("Sell|Overbought", na=False)]

        st.markdown("### 🟢 Buy Signals")
        st.dataframe(buy_df[['Ticker', 'Outlook']])

        st.markdown("### 🔴 Sell Signals")
        st.dataframe(sell_df[['Ticker', 'Outlook']])

        def highlight_outlook(val):
            if "Buy" in val or "Oversold" in val:
                return 'background-color: lightgreen; font-weight: bold'
            elif "Sell" in val or "Overbought" in val:
                return 'background-color: lightcoral; font-weight: bold'
            return ''

        st.markdown("### 📋 Full Signal Table")
        display_df = success_df.copy()
        display_df['RSI'] = display_df['RSI'].apply(lambda x: f"{float(x):.2f}")
        display_df['MACD'] = display_df['MACD'].apply(lambda x: f"{float(x):.4f}")
        display_df['MACD_Signal'] = display_df['MACD_Signal'].apply(lambda x: f"{float(x):.4f}")
        display_df['Close'] = display_df['Close'].apply(lambda x: f"{float(x):.2f}")
        display_df['Price Target'] = display_df['Price Target'].astype(str)
        st.dataframe(
            display_df[
                ['Ticker', 'Outlook', 'Options Strategy', 'Example Option', 'Indicator Profile', 'Price Target', 'RSI', 'MACD', 'MACD_Signal', 'Close']
            ].style.map(highlight_outlook, subset=["Outlook"])
        )
    else:
        st.warning("No valid analysis results to display.")

    if not error_df.empty:
        st.markdown("### ⚠️ Tickers With Errors")
        if 'Ticker' in error_df.columns and 'Error' in error_df.columns:
            st.dataframe(error_df[['Ticker', 'Error']])
        else:
            st.dataframe(error_df)
    else:
        st.dataframe(error_df)

    selected_ticker = st.selectbox("Select a ticker to view charts", tickers)
    with st.spinner(f"📉 Loading historical chart for {selected_ticker}..."):
        data = yf.download(selected_ticker, period=period)
    if not data.empty:
        data.dropna(inplace=True)

        close_series = pd.Series(data['Close'].values.flatten(), index=data.index)
        data['RSI'] = ta.momentum.RSIIndicator(close=close_series).rsi()
        macd_calc = ta.trend.MACD(close=close_series)
        data['MACD'] = macd_calc.macd()
        data['MACD_Signal'] = macd_calc.macd_signal()
        data.dropna(inplace=True)

        fig_price = go.Figure()
        fig_price.add_trace(go.Scatter(x=data.index, y=data['Close'], name='Close'))
        fig_price.update_layout(title=f'{selected_ticker} Price', height=400)

        rsi_fig = go.Figure()
        rsi_fig.add_trace(go.Scatter(x=data.index, y=data['RSI'], name='RSI'))
        rsi_fig.add_hline(y=70, line_dash='dash', line_color='red')
        rsi_fig.add_hline(y=30, line_dash='dash', line_color='green')
        rsi_fig.update_layout(title='RSI Indicator', height=300)

        macd_fig = go.Figure()
        macd_fig.add_trace(go.Scatter(x=data.index, y=data['MACD'], name='MACD'))
        macd_fig.add_trace(go.Scatter(x=data.index, y=data['MACD_Signal'], name='Signal'))
        macd_fig.update_layout(title='MACD Indicator', height=300)

        st.plotly_chart(fig_price, use_container_width=True)
        st.plotly_chart(rsi_fig, use_container_width=True)
        st.plotly_chart(macd_fig, use_container_width=True)        
        # st.dataframe(error_df[['Ticker', 'Error']])
