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
st.caption("AI-Powered Ultra-Short Scalping & Position Risk Calculator")

LOG_FILE = "trade_log.csv"

# Αρχικοποίηση CSV αν δεν υπάρχει
if not os.path.exists(LOG_FILE):
    df_init = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Reason"])
    df_init.to_csv(LOG_FILE, index=False)

api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

# Pydantic Schema
class TradeSetup(BaseModel):
    pair: str
    direction: str  # "LONG", "SHORT", ή "NO TRADE"
    entry: float
    sl: float
    tp1: float
    reason: str     # Αιτιολογία για το trade

# --- ΔΥΝΑΜΙΚΟ TRADINGVIEW CHART ---
st.subheader("📊 Live TradingView Chart")

default_symbol = "BYBIT:SUIUSDT"
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
    tv_symbol = st.text_input("Σύμβολο TradingView:", value=default_symbol, key="tv_symbol_input")
with col_tv2:
    timeframe = st.selectbox("Timeframe:", ["1", "3", "5", "15", "60", "240", "D"], index=2, key="tv_tf_select")

tv_widget_html = """
<div class="tradingview-widget-container" style="height:500px;width:100%;">
  <div id="tradingview_widget" style="height:500px;width:100%;"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({
    "autosize": true,
    "symbol": "SYMBOL_PLACEHOLDER",
    "interval": "TIMEFRAME_PLACEHOLDER",
    "timezone": "Europe/Athens",
    "theme": "dark",
    "style": "1",
    "locale": "el",
    "toolbar_bg": "#f1f3f6",
    "enable_publishing": false,
    "hide_legend": false,
    "studies": [],
    "container_id": "tradingview_widget"
  });
  </script>
</div>
"""

final_html = tv_widget_html.replace("SYMBOL_PLACEHOLDER", tv_symbol).replace("TIMEFRAME_PLACEHOLDER", str(timeframe))
st.components.v1.html(final_html, height=500)
st.divider()

# --- ΣΥΝΑΡΤΗΣΗ LIVE CHECK ΑΓΟΡΑΣ (ΔΙΟΡΘΩΜΕΝΗ) ---
def check_trade_status(row):
    pair = str(row.get("Pair", "")).replace("/", "").replace("-", "").replace(" ", "").upper()
    direction = str(row.get("Direction", "")).upper()
    current_status = str(row.get("Status", "Pending ⏳"))
    
    if "WIN" in current_status or "LOSS" in current_status:
        return current_status

    if not pair or pair == "NAN" or direction == "NO TRADE":
        return current_status

    try:
        tp1 = float(str(row.get("TP1", 0)).replace(",", "."))
        sl = float(str(row.get("SL", 0)).replace(",", "."))
        
        # Καθαρισμός συμβόλου για Bybit Linear Tickers
        clean_symbol = pair if pair.endswith("USDT") or pair.endswith("USDC") else f"{pair}USDT"
        clean_symbol = clean_symbol.replace("USDC", "USDT")
        
        url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={clean_symbol}"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get("retCode") == 0 and data["result"]["list"]:
            last_price = float(data["result"]["list"][0]["lastPrice"])
            
            if "LONG" in direction:
                if sl > 0 and last_price <= sl:
                    return "LOSS ❌"
                elif tp1 > 0 and last_price >= tp1:
                    return "WIN 🎯"
            elif "SHORT" in direction:
                if sl > 0 and last_price >= sl:
                    return "LOSS ❌"
                elif tp1 > 0 and last_price <= tp1:
                    return "WIN 🎯"
                    
            return f"Pending ⏳ ({last_price})"
    except Exception:
        pass
        
    return current_status

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
