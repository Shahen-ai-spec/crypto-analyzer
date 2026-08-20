import streamlit as st
import pandas as pd
import os
import json
import ccxt
import time
import re
import streamlit.components.v1 as components
from datetime import datetime
from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel, Field

st.set_page_config(page_title="Crypto Analyzer & Live Tracker", page_icon="📈", layout="wide")
st.title("📈 Crypto Chart Analyzer & Live Tracker")

LOG_FILE = "trade_log.csv"

# Αρχικοποίηση CSV αν δεν υπάρχει
if not os.path.exists(LOG_FILE):
    df_init = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Analysis"])
    df_init.to_csv(LOG_FILE, index=False)

api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

# Pydantic Schema
class TradeSetup(BaseModel):
    pair: str = Field(description="Το ζεύγος, π.χ. SOL/USDT")
    direction: str = Field(description="LONG ή SHORT")
    entry: str = Field(description="Τιμή εισόδου")
    sl: str = Field(description="Τιμή Stop Loss")
    tp1: str = Field(description="Τιμή Take Profit 1")
    tp2: str = Field(description="Τιμή Take Profit 2")
    rsi_value: str = Field(description="Τιμή RSI αν υπάρχει")
    analysis_summary: str = Field(description="Σύντομη περιγραφή Technical Analysis")

# --- ΔΥΝΑΜΙΚΟ TRADINGVIEW CHART ---
st.subheader("📊 Live TradingView Chart")

default_symbol = "BYBIT:SOLUSDT"
if os.path.exists(LOG_FILE):
    try:
        df_temp = pd.read_csv(LOG_FILE)
        if not df_temp.empty and "Pair" in df_temp.columns:
            last_pair = str(df_temp.iloc[0]["Pair"]).replace("/", "").upper().strip()
            if last_pair and last_pair != "NAN":
                default_symbol = f"BYBIT:{last_pair}"
    except Exception:
        pass

col_tv1, col_tv2 = st.columns([3, 1])
with col_tv1:
    tv_symbol = st.text_input("Σύμβολο TradingView:", value=default_symbol)
with col_tv2:
    timeframe = st.selectbox("Timeframe:", ["1", "3", "5", "15", "60", "240", "D"], index=2)

tv_widget_html = f"""
<div class="tradingview-widget-container" style="height:500px;width:100%;">
  <div id="tradingview_widget" style="height:500px;width:100%;"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{
    "autosize": true,
    "symbol": "{tv_symbol}",
    "interval": "{timeframe}",
    "timezone": "Etc/UTC",
    "theme": "dark",
    "style": "1",
    "locale": "el",
    "toolbar_bg": "#f1f3f6",
    "enable_publishing": false,
    "hide_legend": false,
    "studies": [
      "STD;RSI",
      "STD;EMA",
      "STD;MACD"
    ],
    "container_id": "tradingview_widget"
  }});
  </script>
</div>
"""
components.html(tv_widget_html, height=510)
st.divider()

# --- ΣΥΝΑΡΤΗΣΗ LIVE CHECK ΑΓΟΡΑΣ ---
def check_trade_status(row):
    status = str(row["Status"])
    if "Win" in status or "Loss" in status or "Canceled" in status:
        return status

    pair = str(row["Pair"]).upper().strip()
    direction = str(row["Direction"]).upper().strip()
    
    try:
        entry = float(row["Entry"])
        sl = float(row["SL"])
        tp1 = float(row["TP1"])
    except (ValueError, TypeError):
        return status

    try:
        trade_date = datetime.strptime(str(row["Date"]), "%Y-%m-%d %H:%M")
        since_timestamp = int(trade_date.timestamp() * 1000)
    except Exception:
        since_timestamp = None

    for exchange_class in [ccxt.bybit, ccxt.binance]:
        try:
            exchange = exchange_class()
            raw_pair = pair.replace("/", "")
            tickers_to_try = [
                pair, 
                raw_pair, 
                pair.replace("USDC", "USDT"), 
                raw_pair.replace("USDC", "USDT"),
                pair.replace("USDT", "USDC"),
                raw_pair.replace("USDT", "USDC")
            ]
            
            for symbol in tickers_to_try:
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    last_price = float(ticker['last'])
                    high_24h = float(ticker['high'])
                    low_24h = float(ticker['low'])

                    if direction == "LONG":
                        if last_price >= tp1 or high_24h >= tp1:
                            return "Win 🏆"
                        elif last_price <= sl:
                            return "Loss ❌"
                    elif direction == "SHORT":
                        if last_price <= tp1 or low_24h <= tp1:
                            return "Win 🏆"
                        elif last_price >= sl:
                            return "Loss ❌"

                    if since_timestamp:
                        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1m', since=since_timestamp, limit=1000)
                        for candle in ohlcv:
                            c_high, c_low = candle[2], candle[3]
                            if direction == "LONG":
                                if c_low <= sl:
                                    return "Loss ❌"
                                elif c_high >= tp1:
                                    return "Win 🏆"
                            elif direction == "SHORT":
                                if c_high >= sl:
                                    return "Loss ❌"
                                elif c_low <= tp1:
                                    return "Win 🏆"
                    break
                except Exception:
                    continue
        except Exception:
            continue

    return "Pending ⏳"

# --- UPLOAD & ΑΝΑΛΥΣΗ EIKONΩΝ ---
st.subheader("📷 Ανάλυση Εικόνων Chart")
uploaded_files = st.file_uploader("Επιλογή εικόνων chart...", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)

if uploaded_files:
    images = []
    cols = st.columns(len(uploaded_files))
    for idx, uploaded_file in enumerate(uploaded_files):
        img = Image.open(uploaded_file).convert("RGB")
        images.append(img)
        with cols[idx]:
            st.image(img, caption=f"Εικόνα {idx+1}", use_container_width=True)

    if st.button("🚀 Ανάλυση & Αυτόματη Αποθήκευση"):
        if not api_key:
            st.error("Δεν βρέθηκε API Key!")
        else:
            with st.spinner("Γίνεται ανάλυση και εξαγωγή δεδομένων..."):
                try:
                    client = genai.Client(api_key=api_key)

                    prompt = """
Είσαι ένας αντικειμενικός και ακριβής Technical Analyst.
Εξέτασε την εικόνα και εντόπισε αυστηρά τα εξής:

1. **Pair**: Το όνομα του ζεύγους (π.χ. SOL/USDT) όπως εμφανίζεται πάνω αριστερά.
2. **Direction**: "LONG" αν η τάση είναι ανοδική / πράσινο κουτί, ή "SHORT" αν είναι καθοδική / κόκκινο κουτί.
3. **Entry, SL, TP1, TP2**: 
   - Αν υπάρχει το σχεδιαστικό εργαλείο Long/Short Position του TradingView, διάβασε ΑΚΡΙΒΩΣ τους αριθμούς που αναγράφονται πάνω του.
   - Αν δεν υπάρχει, χρησιμοποίησε τις τιμές από τον δεξιό άξονα τιμών.
4. **RSI**: Την ακριβή τιμή του RSI αν υπάρχει.
5. **Analysis**: Μία σύντομη πρόταση για το Price Action.

Να είσαι 100% ακριβής με τους αριθμούς της εικόνας χωρίς να μαντεύεις.
"""

                    response = None
                    for attempt in range(3):
                        try:
                            # Ρύθμιση temperature=0.0 για σταθερά/ deterministic αποτελέσματα
                            response = client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=images + [prompt],
                                config=types.GenerateContentConfig(
                                    temperature=0.0,
                                    seed=42,
                                    response_mime_type="application/json",
                                    response_schema=TradeSetup,
                                )
                            )
                            break
                        except Exception as e:
                            if "503" in str(e) and attempt < 2:
                                time.sleep(2)
                                continue
                            else:
                                raise e

                    trade_data = json.loads(response.text)
                    st.success("Η ανάλυση ολοκληρώθηκε!")

                    def parse_float(val):
                        try:
                            cleaned = re.sub(r'[^\d.]', '', str(val))
                            return float(cleaned) if cleaned else 0.0
                        except Exception:
                            return 0.0

                    entry_val = parse_float(trade_data.get("entry"))
                    sl_val = parse_float(trade_data.get("sl"))
                    tp1_val = parse_float(trade_data.get("tp1"))
                    tp2_val = parse_float(trade_data.get("tp2"))

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Pair", trade_data.get("pair"))
                    col2.metric("Direction", trade_data.get("direction"))
                    col3.metric("Entry", entry_val)
                    col4.metric("Stop Loss", sl_val)

                    col5, col6 = st.columns(2)
                    col5.metric("Take Profit 1", tp1_val)
                    col6.metric("Take Profit 2", tp2_val)

                    st.info(f"**RSI:** {trade_data.get('rsi_value')}\n\n**Ανάλυση:** {trade_data.get('analysis_summary')}")

                    new_entry = {
                        "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Pair": trade_data.get("pair"),
                        "Direction": trade_data.get("direction"),
                        "Entry": entry_val,
                        "SL": sl_val,
                        "TP1": tp1_val,
                        "TP2": tp2_val,
                        "Status": "Pending ⏳",
                        "Analysis": trade_data.get("analysis_summary")
                    }

                    df_log = pd.read_csv(LOG_FILE)
                    df_log = pd.concat([pd.DataFrame([new_entry]), df_log], ignore_index=True)
                    df_log.to_csv(LOG_FILE, index=False)
                    st.toast("Το trade αποθηκεύτηκε!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Σφάλμα: {e}")

# --- LIVE TRADE TRACKER ---
st.divider()
st.subheader("📜 Live Trade Log Tracker")

df_history = pd.read_csv(LOG_FILE)

col_a, col_b = st.columns([1, 4])
with col_a:
    if st.button("🔄 Ενημέρωση Live Status Trades"):
        with st.spinner("Έλεγχος ζωντανών τιμών από την αγορά..."):
            df_history["Status"] = df_history.apply(check_trade_status, axis=1)
            df_history.to_csv(LOG_FILE, index=False)
            st.success("Το ιστορικό ενημερώθηκε!")
            st.rerun()

st.dataframe(df_history, use_container_width=True)

if st.button("🗑️ Καθαρισμός Ιστορικού"):
    df_empty = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Analysis"])
    df_empty.to_csv(LOG_FILE, index=False)
    st.rerun()
