import streamlit as st
import pandas as pd
import os
import json
import ccxt
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

# Pydantic Schema για Structured JSON Output
class TradeSetup(BaseModel):
    pair: str = Field(description="Το ζεύγος, π.χ. SOL/USDT")
    direction: str = Field(description="LONG ή SHORT")
    entry: float = Field(description="Τιμή εισόδου")
    sl: float = Field(description="Τιμή Stop Loss")
    tp1: float = Field(description="Τιμή Take Profit 1")
    tp2: float = Field(description="Τιμή Take Profit 2")
    rsi_value: str = Field(description="Η τιμή του RSI αν υπάρχει στο chart (π.χ. '68 - Overbought' ή '32 - Oversold' ή 'N/A')")
    confluence_factors: str = Field(description="Παράγοντες επιβεβαίωσης, π.χ. RSI Bearish Divergence, Key Support Level")
    analysis_summary: str = Field(description="Σύντομη περιγραφή Price Action")

# --- ΔΥΝΑΜΙΚΟ TRADINGVIEW CHART ---
st.subheader("📊 Live TradingView Chart")

# Υπολογισμός προεπιλεγμένου συμβόλου βάσει του τελευταίου trade
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

# TradingView Widget Embed με προεπιλεγμένο RSI
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
  "STD;EMA",          # Exponential Moving Average
  "STD;MACD"          # Moving Average Convergence Divergence
]
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
    # Αν έχει ήδη κλείσει το trade, μην το ξαναελέγχεις
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

    # Δοκιμή με CCXT (Bybit & Binance)
    for exchange_class in [ccxt.bybit, ccxt.binance]:
        try:
            exchange = exchange_class()
            
            # Αν είναι USDC, δοκιμάζουμε και με USDT αν αποτύχει
            tickers_to_try = [pair, pair.replace("USDC", "USDT")]
            
            for symbol in tickers_to_try:
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    high_price = float(ticker['high'])
                    low_price = float(ticker['low'])
                    last_price = float(ticker['last'])

                    if direction == "LONG":
                        if low_price <= sl:
                            return "Loss ❌"
                        elif high_price >= tp1 or last_price >= tp1:
                            return "Win 🏆"
                    elif direction == "SHORT":
                        if high_price >= sl:
                            return "Loss ❌"
                        elif low_price <= tp1 or last_price <= tp1:
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
Είσαι ένας Senior Crypto Technical Analyst.
Ανάλυσε το chart χρησιμοποιώντας Συνδυαστική Επιβεβαίωση (Confluence):

1. Trend (EMA): Έλεγξε τη σχέση της τιμής με τους Moving Averages. Μην δίνεις σήματα κόντρα στην τάση.
2. Momentum (RSI & MACD): Έλεγξε αν υπάρχει Bullish/Bearish Divergence ή Crossover.
3. Key Levels: Εντόπισε Support/Resistance ή Order Blocks για τα Entry, SL και TP.
4. Confluence Score: Δώσε σήμα ΜΟΝΟ αν τουλάχιστον 2 από τα 3 εργαλεία συμφωνούν προς την ίδια κατεύθυνση.

Συμπλήρωσε αυστηρά τη δομή JSON.
"""
                    
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=images + [prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=TradeSetup,
                        )
                    )
                    
                    trade_data = json.loads(response.text)
                    st.success("Η ανάλυση ολοκληρώθηκε!")
                    
                    # Προβολή Metrics
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Pair", trade_data.get("pair"))
                    col2.metric("Direction", trade_data.get("direction"))
                    col3.metric("Entry", trade_data.get("entry"))
                    col4.metric("Stop Loss", trade_data.get("sl"))
                    
                    col5, col6 = st.columns(2)
                    col5.metric("Take Profit 1", trade_data.get("tp1"))
                    col6.metric("Take Profit 2", trade_data.get("tp2"))
                    
                    st.info(trade_data.get("analysis_summary"))
                    
                    # Καταγραφή στο CSV
                    new_entry = {
                        "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Pair": trade_data.get("pair"),
                        "Direction": trade_data.get("direction"),
                        "Entry": trade_data.get("entry"),
                        "SL": trade_data.get("sl"),
                        "TP1": trade_data.get("tp1"),
                        "TP2": trade_data.get("tp2"),
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

# --- ΜΟΝΙΜΟ ΙΣΤΟΡΙΚΟ (LIVE TRADE TRACKER) ---
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
