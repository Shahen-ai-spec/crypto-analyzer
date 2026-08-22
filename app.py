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
from PIL import Image, ImageEnhance
from pydantic import BaseModel, Field

st.set_page_config(page_title="PANDA CRYPTO Analyzer", page_icon="🐼", layout="wide")

# --- ΑΣΦΑΛΕΙΑ / LOGIN SYSTEM ---
MY_PASSWORD = "Gitbtc2026shahen"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Εφαρμογή Κλειδωμένη")
    pwd_input = st.text_input("Εισάγετε τον κωδικό πρόσβασης:", type="password")
    
    if st.button("Σύνδεση"):
        if pwd_input.strip() == MY_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Λάθος κωδικός!")
    st.stop()

# --- ΑΠΟ ΕΔΩ ΚΑΙ ΚΑΤΩ ΦΟΡΤΩΝΕΙ Η ΕΦΑΡΜΟΓΗ ---
st.title("🐼 PANDA CRYPTO Analyzer")
st.caption("AI-Powered Ultra-Short Scalping & Position Risk Calculator")


LOG_FILE = "trade_log.csv"

# Αρχικοποίηση CSV αν δεν υπάρχει
if not os.path.exists(LOG_FILE):
    df_init = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Analysis"])
    df_init.to_csv(LOG_FILE, index=False)

api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

# Pydantic Schema
class TradeSetup(BaseModel):
    pair: str
    direction: str  # Θα επιστρέφει "LONG", "SHORT", ή "NO TRADE"
    entry: float
    sl: float
    tp1: float
    reason: str     # Αιτιολογία για το trade ή γιατί δίνει NO TRADE

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

# Ορισμός του HTML καθαρά χωρίς f-string για αποφυγή syntax errors
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

# Αντικατάσταση μεταβλητών
final_html = tv_widget_html.replace("SYMBOL_PLACEHOLDER", tv_symbol).replace("TIMEFRAME_PLACEHOLDER", str(timeframe))

# Εμφάνιση Widget
st.components.v1.html(final_html, height=500)
st.divider()

# --- ΣΥΝΑΡΤΗΣΗ LIVE CHECK ΑΓΟΡΑΣ ---
def check_trade_status(row):
    pair = str(row.get("Pair", "")).replace("/", "").replace(" ", "").upper()
    direction = str(row.get("Direction", "")).upper()
    current_status = str(row.get("Status", "Pending ⏳"))
    
    # Αν είναι ήδη WIN ή LOSS, μην αλλάζεις τίποτα
    if "WIN" in current_status or "LOSS" in current_status:
        return current_status

    if not pair or pair == "NAN":
        return current_status

    try:
        tp1 = float(str(row.get("TP1", 0)).replace(",", "."))
        sl = float(str(row.get("SL", 0)).replace(",", "."))
        
        # Καθαρισμός συμβόλου - Δοκιμή με USDT που έχει πάντα liquidity
        clean_symbol = pair.replace("USDC", "USDT")
        
        url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={clean_symbol}"
        response = requests.get(url, timeout=3)
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

    if st.button("🚀 Έναρξη Ανάλυσης Chart", key="analyze_btn_main"):
        if not api_key:
            st.error("Δεν βρέθηκε API Key!")
        else:
            with st.spinner("Γίνεται ανάλυση με το Gemini 3.6 Flash..."):
                try:
                    client = genai.Client(api_key=api_key)

                    prompt = """

You are a Senior Crypto Price Action Scalper and Strict Risk Manager.
Analyze the chart EXCLUSIVELY for ULTRA-SHORT SCALPING (1m-5m charts).
Your primary job is NOT to find a trade in every chart, but to PROTECT capital by approving ONLY high-probability setups.

STRICT PRICE ACTION RULES:
1. TREND ALIGNMENT: Identify market structure (HH/HL or LH/LL). Strictly NEVER take counter-trend trades.
2. MARKET STRUCTURE: Requires a clear Break of Structure (BOS) or Change of Character (CHoCH). Do NOT enter during low-volatility chop or ranges.
3. STOP LOSS & LIQUIDITY: Stop Loss MUST be placed beyond key liquidity pools (major swing points). Do NOT place tight SLs on immediate candle wicks. Give the trade room to breathe.
4. RISK/REWARD: Maintain a minimum Risk to Reward Ratio (RRR) of strictly 1:2.5.
5. NO TRADE MANDATE: If the chart lacks 8/10 setup clarity or structure, return "NO TRADE" in the direction field, set entry/sl/tp1 to 0.0, and explain why in the reason field.

Pair: Read the exact trading pair from the top-left of the chart (e.g., SUI/USDT).
"""

    # --- ΦΟΡΜΑ ΕΠΙΒΕΒΑΙΩΣΗΣ ΚΑΙ ΔΙΟΡΘΩΣΗΣ ΔΕΔΟΜΕΝΩΝ ---
    
    if "parsed_trade" in st.session_state:
        trade_data = st.session_state["parsed_trade"]

        st.markdown("### 📝 Επιβεβαίωση / Διόρθωση Στοιχείων Trade")
    
    def clean_val(val):
        try:
            match = re.search(r'\d+\.?\d*', str(val))
            return float(match.group()) if match else 0.0
        except Exception:
            return 0.0

    with st.form("confirm_trade_form"):
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            f_pair = st.text_input("Pair", value=trade_data.get("pair", "SUI/USDT"))
            f_dir = st.selectbox("Direction", ["LONG", "SHORT"], index=0 if str(trade_data.get("direction")).upper() == "LONG" else 1)
            f_entry = st.number_input("Entry Price", value=clean_val(trade_data.get("entry")), format="%.4f")
            f_sl = st.number_input("Stop Loss (SL)", value=clean_val(trade_data.get("sl")), format="%.4f")
        
        with col_f2:
            f_tp1 = st.number_input("Take Profit 1 (TP1)", value=clean_val(trade_data.get("tp1")), format="%.4f")
            f_tp2 = st.number_input("Take Profit 2 (TP2)", value=clean_val(trade_data.get("tp2")), format="%.4f")
            f_rsi = st.text_input("RSI Value", value=str(trade_data.get("rsi_value", "N/A")))
            f_analysis = st.text_area("Analysis Summary", value=trade_data.get("analysis_summary", ""))

        submit_save = st.form_submit_button("💾 Αποθήκευση στο Trade Log")
        
        if submit_save:
            new_entry = {
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Pair": f_pair,
                "Direction": f_dir,
                "Entry": f_entry,
                "SL": f_sl,
                "TP1": f_tp1,
                "TP2": f_tp2,
                "Status": "Pending ⏳",
                "Analysis": f_analysis
            }

            df_log = pd.read_csv(LOG_FILE)
            df_log = pd.concat([pd.DataFrame([new_entry]), df_log], ignore_index=True)
            df_log.to_csv(LOG_FILE, index=False)
            
            del st.session_state["parsed_trade"]
            st.toast("Το trade αποθηκεύτηκε επιτυχώς!")
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
    df_empty = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Analysis"])
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
