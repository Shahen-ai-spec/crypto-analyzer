import streamlit as st
import pandas as pd
import os
import json
import ccxt
import time
import re
import requests
import streamlit.components.v1 as components
from datetime import datetime
from google import genai
from google.genai import types
from PIL import Image, ImageEnhance
from pydantic import BaseModel, Field
# --- ΑΠΟ ΕΔΩ ΚΑΙ ΚΑΤΩ ΦΟΡΤΩΝΕΙ Η ΕΦΑΡΜΟΓΗ ---
st.title("🐼 PANDA CRYPTO Analyzer")


LOG_FILE = "trade_log.csv"

# Αρχικοποίηση CSV αν δεν υπάρχει
if not os.path.exists(LOG_FILE):
    df_init = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Reason"])
    df_init.to_csv(LOG_FILE, index=False)

# Διάβασμα του API Key απευθείας από τα Secrets
api_key = st.secrets.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Pydantic Schema
class TradeSetup(BaseModel):
    pair: str
    direction: str  # "LONG", "SHORT", ή "NO TRADE"
    entry: float
    sl: float
    tp1: float
    reason: str     # Αιτιολογία για το trade

# --- ΔΥΝΑΜΙΚΟ TRADINGVIEW CHART ---
import yfinance as yf


import pandas as pd
import yfinance as yf


def calculate_rsi(prices, period=14):
    """Υπολογισμός RSI (14)"""
    delta = pd.Series(prices).diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]


def get_auto_analysis(symbol_ticker="SOL-USD"):
    try:
        df = yf.download(tickers=symbol_ticker, period="7d", interval="1h")

        if not df.empty:
            close_prices = df["Close"].values.flatten().tolist()
            high_prices = df["High"].values.flatten().tolist()
            low_prices = df["Low"].values.flatten().tolist()

            current_price = round(float(close_prices[-1]), 2)
            recent_high = round(float(max(high_prices[-24:])), 2)
            recent_low = round(float(min(low_prices[-24:])), 2)

            # 1. Υπολογισμός SMA 20
            sma20 = sum(close_prices[-20:]) / 20

            # 2. Υπολογισμός RSI 14
            rsi_val = round(calculate_rsi(close_prices, 14), 1)

            # 3. Υπολογισμός Fibonacci Levels (από το 24h High/Low)
            price_range = recent_high - recent_low
            fib_618 = round(recent_high - (price_range * 0.618), 2)
            fib_500 = round(recent_high - (price_range * 0.500), 2)

            # --- Συνδυαστική Λογική Σήματος ---
            # LONG αν η τιμή είναι κοντά/πάνω από το 0.618 Fib & RSI < 60
            # SHORT αν η τιμή είναι πάνω από SMA20 αλλά RSI > 70 (Overbought) ή κάτω από Fib 0.618
            if current_price >= fib_618 and rsi_val < 65:
                direction = "🟢 LONG (Fib Support & Good Momentum)"
                tp1 = round(recent_high, 2)
                sl = round(recent_low, 2)
            elif rsi_val >= 70:
                direction = "🔴 SHORT (RSI Overbought)"
                tp1 = fib_500
                sl = round(recent_high * 1.01, 2)
            elif current_price < fib_618 and rsi_val <= 40:
                direction = "🔴 SHORT (Broke Fib Support)"
                tp1 = round(recent_low, 2)
                sl = fib_500
            else:
                direction = "🟡 NEUTRAL / WAIT (No Clear Setup)"
                tp1 = round(recent_high, 2)
                sl = round(recent_low, 2)

            return {
                "price": current_price,
                "direction": direction,
                "tp1": tp1,
                "sl": sl,
                "sma20": round(sma20, 2),
                "rsi": rsi_val,
                "fib_618": fib_618,
                "fib_500": fib_500,
            }
        else:
            st.error("Δεν βρέθηκαν δεδομένα από το Yahoo Finance.")
    except Exception as e:
        st.error(f"Error: {str(e)}")
    return None
    
# --- ΑΥΤΟΜΑΤΗ ΑΝΑΛΥΣΗ (UI) ---
st.subheader("🤖 Αυτόματη Τεχνική Ανάλυση (Live)")

# Αυτόματη μετατροπή / σε - και USDT σε USD
user_input = st.text_input(
    "Γράψε Ticker (π.χ. SOL-USD, ENA-USD ή ENA/USDT):", value="SOL-USD"
)
selected_coin = (
    user_input.strip().upper().replace("/", "-").replace("-USDT", "-USD")
)
selected_coin = user_input.upper().replace("-USDT", "-USD")

if st.button("Ανάλυση"):
    analysis = get_auto_analysis(selected_coin)
    if analysis:
        st.write(f"**Νόμισμα:** {selected_coin}")
        st.write(f"**Τρέχουσα Τιμή:** ${analysis['price']}")
        st.write(f"**Πρόταση (SMA20):** {analysis['direction']}")
        st.write(f"**Take Profit (TP1):** ${analysis['tp1']}")
        st.write(f"**Stop Loss (SL):** ${analysis['sl']}")
    else:
        st.error("Αποτυχία λήψης δεδομένων.")



# --- UPLOAD & ΑΝΑΛΥΣΗ EIKONΩΝ ---
st.subheader("📷 Ανάλυση Εικόνων Chart")
uploaded_files = st.file_uploader("Επιλογή εικόνων chart...", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="chart_uploader")

if uploaded_files:
    processed_images = []
    cols = st.columns(len(uploaded_files))
    
    for idx, uploaded_file in enumerate(uploaded_files):
        img = Image.open(uploaded_file).convert("RGB")
        enhancer = ImageEnhance.Contrast(img)
        enhanced_img = enhancer.enhance(1.2)
        
        processed_images.append(enhanced_img)
        with cols[idx]:
            st.image(img, caption=f"Εικόνα {idx+1}", use_container_width=True)

    if st.button("🚀 Ανάλυση Chart", type="primary"):
        try:
            # Διορθωμένο Prompt με RRR 1:3 και Liquidity Buffer για αποφυγή SL Sweeps
            prompt = """
            You are a Senior Price Action & Liquidity Scalper.
            Analyze the chart image to find the best immediate trade setup (LONG or SHORT) with strict risk controls.

            RULES:
            1. MARKET STRUCTURE: Identify current trend, key Break of Structure (BOS), or Change of Character (CHoCH).
            2. STOP LOSS PLACEMENT: Do NOT place Stop Loss tightly at immediate candle wicks. Add a wide safety buffer beyond major swing points/liquidity pools to avoid liquidity sweeps.
            3. RISK TO REWARD: Ensure Take Profit (TP1) achieves at least a 1:3 Risk-to-Reward Ratio (RRR >= 1:3) relative to the entry and buffered SL.
            4. Provide exact values for Entry, SL, and TP1.
            5. Return "NO TRADE" only if the chart structure is completely unreadable or an explicit 1:3 setup with safe SL cannot be formed.
            6. Write a brief explanation for your setup.

            Read the exact crypto pair symbol from the top left of the chart.
            """

            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=processed_images + [prompt],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema=TradeSetup,
                )
            )
            
            st.session_state["parsed_trade"] = response.parsed.model_dump()
            st.success("Η ανάλυση ολοκληρώθηκε!")

        except Exception as e:
            st.error(f"Σφάλμα κατά την ανάλυση: {e}")

# --- ΒΟΗΘΗΤΙΚΗ ΣΥΝΑΡΤΗΣΗ ΚΑΘΑΡΙΣΜΟΥ ΤΙΜΩΝ ---
def clean_val(val):
    try:
        match = re.search(r'\d+\.?\d*', str(val))
        return float(match.group()) if match else 0.0
    except Exception:
        return 0.0

# --- ΦΟΡΜΑ ΕΠΙΒΕΒΑΙΩΣΗΣ ΚΑΙ ΔΙΟΡΘΩΣΗΣ ΔΕΔΟΜΕΝΩΝ ---
if "parsed_trade" in st.session_state:
    trade_data = st.session_state["parsed_trade"]
    st.markdown("### 📝 Επιβεβαίωση / Διόρθωση Στοιχείων Trade")

    with st.form("confirm_trade_form"):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            f_pair = st.text_input("Pair", value=trade_data.get("pair", "SUI/USDT"))
            
            dir_val = str(trade_data.get("direction", "NO TRADE")).upper()
            opts = ["LONG", "SHORT", "NO TRADE"]
            dir_idx = opts.index(dir_val) if dir_val in opts else 2
            f_dir = st.selectbox("Direction", opts, index=dir_idx)
            
            f_entry = st.number_input("Entry Price", value=clean_val(trade_data.get("entry")), format="%.4f")
            f_sl = st.number_input("Stop Loss (SL)", value=clean_val(trade_data.get("sl")), format="%.4f")

        with col_f2:
            f_tp1 = st.number_input("Take Profit 1 (TP1)", value=clean_val(trade_data.get("tp1")), format="%.4f")
            f_reason = st.text_area("Analysis / Reason", value=trade_data.get("reason", ""))

        submit_save = st.form_submit_button("💾 Αποθήκευση Trade")

    if submit_save:
        new_entry = {
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Pair": f_pair,
            "Direction": f_dir,
            "Entry": f_entry,
            "SL": f_sl,
            "TP1": f_tp1,
            "TP2": 0.0,
            "Status": "Pending",
            "Reason": f_reason
        }

        if os.path.exists(LOG_FILE):
            df_log = pd.read_csv(LOG_FILE)
        else:
            df_log = pd.DataFrame()

        df_log = pd.concat([df_log, pd.DataFrame([new_entry])], ignore_index=True)
        df_log.to_csv(LOG_FILE, index=False)
        st.success("Το trade αποθηκεύτηκε επιτυχώς!")
        st.rerun()

# --- LIVE TRADE TRACKER ---
st.divider()
st.subheader("📜 Live Trade Log Tracker")

df_history = pd.read_csv(LOG_FILE)

col_a, col_b = st.columns([1, 4])
with col_a:
    if st.button("🔄 Ενημέρωση Live Status Trades", key="update_status_btn"):
        with st.spinner("Έλεγχος ζωντανών τιμών από την αγορά..."):
            if not df_history.empty:
                df_history["Status"] = df_history.apply(check_trade_status, axis=1)
                df_history.to_csv(LOG_FILE, index=False)
            st.rerun()

st.dataframe(df_history, use_container_width=True)

if st.button("🗑️ Καθαρισμός Ιστορικού", key="clear_log_btn"):
    df_empty = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Reason"])
    df_empty.to_csv(LOG_FILE, index=False)
    st.rerun()

# --- ΑΥΤΟΜΑΤΟΣ ΥΠΟΛΟΓΙΣΜΟΣ ΡΙΣΚΟΥ & POSITION SIZE ---
st.markdown("---")
st.subheader("⚖️ Υπολογισμός Ρίσκου & Position Size")

col_acc1, col_acc2, col_acc3 = st.columns(3)
with col_acc1:
    account_balance = st.number_input("Συνολικό Κεφάλαιο ($)", value=50.0, step=10.0, key="risk_calc_balance")
with col_acc2:
    risk_percentage = st.number_input("Ρίσκο ανά Trade (%)", value=1.0, step=0.5, key="risk_calc_pct")
with col_acc3:
    leverage = st.number_input("Leverage (x)", value=10, min_value=1, max_value=100, step=1, key="risk_calc_lev")

try:
    parsed = st.session_state.get("parsed_trade", {})
    if parsed:
        e_val = float(str(parsed.get("entry", 0)).replace(",", "."))
        s_val = float(str(parsed.get("sl", 0)).replace(",", "."))
        t_val = float(str(parsed.get("tp1", 0)).replace(",", "."))
    else:
        df_last = pd.read_csv(LOG_FILE)
        if not df_last.empty:
            e_val = float(str(df_last.iloc[0]["Entry"]).replace(",", "."))
            s_val = float(str(df_last.iloc[0]["SL"]).replace(",", "."))
            t_val = float(str(df_last.iloc[0]["TP1"]).replace(",", "."))
        else:
            e_val, s_val, t_val = 0.0, 0.0, 0.0
except (ValueError, TypeError, Exception):
    e_val, s_val, t_val = 0.0, 0.0, 0.0

if e_val > 0 and s_val > 0 and e_val != s_val:
    risk_amount_usd = account_balance * (risk_percentage / 100.0)
    price_risk_per_unit = abs(e_val - s_val)
    
    position_size_units = risk_amount_usd / price_risk_per_unit
    position_size_usd = position_size_units * e_val
    margin_required = position_size_usd / leverage
    
    reward_per_unit = abs(t_val - e_val) if t_val > 0 else 0
    potential_profit_usd = position_size_units * reward_per_unit
    rrr = reward_per_unit / price_risk_per_unit if price_risk_per_unit > 0 else 0

    st.markdown("### 📊 Αποτελέσματα")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Μέγιστη Χασούρα", f"${risk_amount_usd:.2f}")
    c2.metric("Πιθανό Κέρδος", f"${potential_profit_usd:.2f}")
    c3.metric("Position Size ($)", f"${position_size_usd:.2f}")
    c4.metric(f"Margin (x{int(leverage)})", f"${margin_required:.2f}")
    c5.metric("Ποσότητα (Units)", f"{position_size_units:.4f}")
    c6.metric("Risk/Reward", f"1 : {rrr:.2f}")
else:
    st.info("💡 Μόλις ολοκληρωθεί η ανάλυση από το AI και συμπληρωθούν το Entry & Stop Loss, θα εμφανιστούν εδώ οι υπολογισμοί.")
