import json
import os
import re
import time
from datetime import datetime

import ccxt
import pandas as pd
from PIL import Image, ImageEnhance
from pydantic import BaseModel, Field
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from google import genai
from google.genai import types

# --- ΑΡΧΙΚΟΠΟΙΗΣΗ SESSION STATE (ΣΤΗΝ ΑΡΧΗ ΤΟΥ ΚΩΔΙΚΑ) ---
if "saved_trades_list" not in st.session_state:
    st.session_state.saved_trades_list = []

if "saved_trades" not in st.session_state:
    st.session_state.saved_trades = []

st.title("🐼 PANDA CRYPTO Analyzer")

LOG_FILE = "trade_log.csv"

# Φόρτωση από CSV στην αρχή αν υπάρχει
if os.path.exists(LOG_FILE) and not st.session_state.saved_trades_list:
    try:
        df_disk = pd.read_csv(LOG_FILE)
        st.session_state.saved_trades_list = df_disk.to_dict("records")
    except Exception:
        pass

# API Client
api_key = st.secrets.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)


class TradeSetup(BaseModel):
    pair: str
    direction: str
    entry: float
    sl: float
    tp1: float
    reason: str


def clean_val(val):
    try:
        match = re.search(r"\d+\.?\d*", str(val))
        return float(match.group()) if match else 0.0
    except Exception:
        return 0.0


def calculate_rsi(prices, period=14):
    delta = pd.Series(prices).diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]


def get_auto_analysis(symbol_ticker="SOL-USD"):
    try:
        ticker_clean = symbol_ticker.strip().upper().replace("/", "-")
        if not ticker_clean.endswith("-USD") and not ticker_clean.endswith(
            "-USDT"
        ):
            ticker_clean = f"{ticker_clean}-USD"
        else:
            ticker_clean = ticker_clean.replace("-USDT", "-USD")

        df_1h = yf.download(tickers=ticker_clean, period="7d", interval="1h")
        df_4h = yf.download(tickers=ticker_clean, period="30d", interval="1h")

        if not df_1h.empty:
            close_1h = df_1h["Close"].values.flatten().tolist()
            high_1h = df_1h["High"].values.flatten().tolist()
            low_1h = df_1h["Low"].values.flatten().tolist()

            current_price = round(float(close_1h[-1]), 4)
            recent_high = round(float(max(high_1h[-24:])), 4)
            recent_low = round(float(min(low_1h[-24:])), 4)

            rsi_1h = round(calculate_rsi(close_1h, 14), 1)

            price_range = recent_high - recent_low
            fib_618 = round(recent_high - (price_range * 0.618), 4)

            df_4h_resampled = df_4h["Close"].resample("4h").last().dropna()
            close_4h = df_4h_resampled.values.flatten().tolist()

            sma50_4h = (
                sum(close_4h[-50:]) / 50 if len(close_4h) >= 50 else current_price
            )
            rsi_4h = round(calculate_rsi(close_4h, 14), 1)

            trend_4h = "BULLISH" if current_price > sma50_4h else "BEARISH"

            if current_price >= fib_618 or rsi_1h <= 45:
                sl = round(recent_low * 0.995, 4)
                if sl >= current_price:
                    sl = round(current_price * 0.98, 4)
                risk = current_price - sl
                tp1 = round(current_price + (risk * 3), 4)

                direction = (
                    "🟢 LONG (Bullish Trend)"
                    if trend_4h == "BULLISH"
                    else "🟡 LONG (Pullback Setup)"
                )

            elif rsi_1h >= 55 or current_price < fib_618:
                sl = round(recent_high * 1.005, 4)
                if sl <= current_price:
                    sl = round(current_price * 1.02, 4)
                risk = sl - current_price
                tp1 = round(current_price - (risk * 3), 4)

                direction = (
                    "🔴 SHORT (Bearish Trend)"
                    if trend_4h == "BEARISH"
                    else "⚠️ SHORT (Reversal Setup)"
                )
            else:
                direction = "🟡 NEUTRAL / WAIT"
                tp1 = None
                sl = None

            return {
                "coin": ticker_clean,
                "price": current_price,
                "direction": direction,
                "tp1": tp1,
                "sl": sl,
                "rsi_1h": rsi_1h,
                "rsi_4h": rsi_4h,
                "trend_4h": trend_4h,
                "fib_618": fib_618,
            }
        else:
            st.error(f"Δεν βρέθηκαν δεδομένα για το {symbol_ticker}.")
    except Exception as e:
        st.error(f"Error: {str(e)}")
    return None


# --- 1. ΑΥΤΟΜΑΤΗ ΑΝΑΛΥΣΗ ---
st.subheader("🤖 Αυτόματη Τεχνική Ανάλυση (Live)")

user_input = st.text_input(
    "Γράψε Ticker (π.χ. BTC, ETH, SOL, XRP):", value="SOL"
)

if st.button("Ανάλυση"):
    analysis = get_auto_analysis(user_input)
    if analysis:
        st.session_state.current_analysis = analysis

if "current_analysis" in st.session_state:
    analysis = st.session_state.current_analysis

    st.write(f"**Νόμισμα:** {analysis['coin']}")
    st.write(f"**Τρέχουσα Τιμή:** ${analysis['price']}")
    st.write(f"**4H Macro Τάση:** {analysis['trend_4h']}")
    st.write(f"**Πρόταση Σήματος:** {analysis['direction']}")
    st.write(
        f"**RSI (1H / 4H):** {analysis['rsi_1h']} / {analysis['rsi_4h']}"
    )
    st.write(f"**Fibonacci 0.618:** ${analysis['fib_618']}")

    if analysis["tp1"] is not None and analysis["sl"] is not None:
        st.write(f"**Take Profit 1 (TP1):** ${analysis['tp1']}")
        st.write(f"**Stop Loss (SL):** ${analysis['sl']}")

        if st.button("💾 Αποθήκευση Trade"):
            new_trade = {
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Pair": analysis["coin"],
                "Direction": analysis["direction"],
                "Entry": analysis["price"],
                "SL": analysis["sl"],
                "TP1": analysis["tp1"],
                "Status": "Pending",
                "Reason": "Auto Analysis",
            }
            st.session_state.saved_trades_list.append(new_trade)
            pd.DataFrame(st.session_state.saved_trades_list).to_csv(
                LOG_FILE, index=False
            )
            st.success(f"Το trade για {analysis['coin']} αποθηκεύτηκε!")
            st.rerun()

# --- 2. UPLOAD & ΑΝΑΛΥΣΗ ΕΙΚΟΝΩΝ (GEMINI AI) ---
st.divider()
st.subheader("📷 Ανάλυση Εικόνων Chart (Gemini AI)")

uploaded_files = st.file_uploader(
    "Επιλογή εικόνων chart...",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    key="chart_uploader",
)

if uploaded_files:
    processed_images = []
    cols = st.columns(len(uploaded_files))

    for idx, uploaded_file in enumerate(uploaded_files):
        img = Image.open(uploaded_file).convert("RGB")
        enhancer = ImageEnhance.Contrast(img)
        enhanced_img = enhancer.enhance(1.2)

        processed_images.append(enhanced_img)
        with cols[idx]:
            st.image(
                img, caption=f"Εικόνα {idx+1}", use_container_width=True
            )

    if st.button("🚀 Ανάλυση Chart με AI", type="primary"):
        try:
            prompt = """
            Analyze the chart image to find the best immediate trade setup (LONG or SHORT) with strict risk controls.
            Ensure Take Profit (TP1) achieves strictly a 1:3 Risk-to-Reward Ratio (RRR = 1:3) relative to entry and buffered SL.
            Read the exact crypto pair symbol from the chart.
            """

            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=processed_images + [prompt],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=TradeSetup,
                ),
            )

            st.session_state["parsed_trade"] = response.parsed.model_dump()
            st.success("Η ανάλυση του screenshot ολοκληρώθηκε!")

        except Exception as e:
            st.error(f"Σφάλμα κατά την ανάλυση: {e}")

# Φόρμα Επιβεβαίωσης AI
if "parsed_trade" in st.session_state and st.session_state["parsed_trade"]:
    trade_data = st.session_state["parsed_trade"]
    st.markdown("### 📝 Επιβεβαίωση / Διόρθωση Στοιχείων Trade")

    with st.form("confirm_trade_form"):
        col_f1, col_f2 = st.columns(2)

        with col_f1:
            f_pair = st.text_input(
                "Pair", value=trade_data.get("pair", "BTC/USDT")
            )
            dir_val = str(trade_data.get("direction", "NO TRADE")).upper()
            opts = ["LONG", "SHORT", "NO TRADE"]
            dir_idx = opts.index(dir_val) if dir_val in opts else 2
            f_dir = st.selectbox("Direction", opts, index=dir_idx)

            f_entry = st.number_input(
                "Entry Price",
                value=clean_val(trade_data.get("entry")),
                format="%.4f",
            )
            f_sl = st.number_input(
                "Stop Loss (SL)",
                value=clean_val(trade_data.get("sl")),
                format="%.4f",
            )

        with col_f2:
            f_tp1 = st.number_input(
                "Take Profit 1 (TP1)",
                value=clean_val(trade_data.get("tp1")),
                format="%.4f",
            )
            f_reason = st.text_area(
                "Analysis / Reason", value=trade_data.get("reason", "")
            )

        submit_save = st.form_submit_button("💾 Αποθήκευση AI Trade")

    if submit_save:
        new_entry = {
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Pair": f_pair,
            "Direction": f_dir,
            "Entry": f_entry,
            "SL": f_sl,
            "TP1": f_tp1,
            "Status": "Pending",
            "Reason": f_reason,
        }
        st.session_state.saved_trades_list.append(new_entry)
        pd.DataFrame(st.session_state.saved_trades_list).to_csv(
            LOG_FILE, index=False
        )

        st.session_state["parsed_trade"] = None
        st.success("Το trade αποθηκεύτηκε επιτυχώς!")
        st.rerun()

# --- 3. LIVE TRADE TRACKER & ΔΙΑΓΡΑΦΗ ---
st.divider()
st.subheader("📜 Live Trade Log Tracker")

if st.session_state.saved_trades_list:
    df_display = pd.DataFrame(st.session_state.saved_trades_list)
    st.dataframe(df_display, use_container_width=True)

    st.markdown("#### 🗑️ Διαχείριση / Διαγραφή")
    col_del1, col_del2 = st.columns([2, 1])

    with col_del1:
        trade_options = []
        for idx, row in df_display.iterrows():
            pair_name = row.get("Pair") or row.get("Ticker") or "Unknown"
            direction = row.get("Direction") or row.get("Signal") or "N/A"
            date_val = row.get("Date") or "Live"

            trade_options.append(
                f"{idx}: {pair_name} ({direction}) - {date_val}"
            )

        selected_to_delete = st.selectbox(
            "Επίλεξε Trade για διαγραφή:", trade_options
        )

        if st.button("❌ Διαγραφή Επιλεγμένου Trade"):
            row_idx = int(selected_to_delete.split(":")[0])
            st.session_state.saved_trades_list.pop(row_idx)

            df_updated = pd.DataFrame(st.session_state.saved_trades_list)
            df_updated.to_csv(LOG_FILE, index=False)

            st.success("Το trade διαγράφηκε!")
            st.rerun()

    with col_del2:
        st.write(" ")
        st.write(" ")
        if st.button("🗑️ Καθαρισμός Όλων", key="clear_log_btn"):
            st.session_state.saved_trades_list = []
            if os.path.exists(LOG_FILE):
                os.remove(LOG_FILE)
            st.success("Όλα τα trades διαγράφηκαν!")
            st.rerun()
else:
    st.info("💡 Δεν υπάρχουν ακόμα αποθηκευμένα trades στον πίνακα.")
