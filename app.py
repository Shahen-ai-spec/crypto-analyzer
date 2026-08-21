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
    pair: str = Field(description="Το ζεύγος, π.χ. SUI/USDT ή SOL/USDT")
    direction: str = Field(description="LONG ή SHORT")
    entry: str = Field(description="Τιμή εισόδου")
    sl: str = Field(description="Τιμή Stop Loss")
    tp1: str = Field(description="Τιμή Take Profit 1")
    tp2: str = Field(description="Τιμή Take Profit 2")
    rsi_value: str = Field(description="Τιμή RSI αν εμφανίζεται")
    analysis_summary: str = Field(description="Σύντομη περιγραφή Technical Analysis")

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
    status = str(row.get("Status", "Pending ⏳"))
    if "Win" in status or "Loss" in status or "Canceled" in status:
        return status

    pair = str(row.get("Pair", "")).upper().strip()
    direction = str(row.get("Direction", "")).upper().strip()

    try:
        entry = float(str(row["Entry"]).replace(",", "."))
        sl = float(str(row["SL"]).replace(",", "."))
        tp1 = float(str(row["TP1"]).replace(",", "."))
    except (ValueError, TypeError, KeyError):
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
                    # 1. Έλεγχος με Ιστορικά Κεριά (OHLCV) από την ώρα του trade
                    if since_timestamp:
                        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1m', since=since_timestamp, limit=1000)
                        for candle in ohlcv:
            c_high, c_low = candle[2], candle[3]
            
            if "LONG" in direction.upper():
                if tp1 > 0 and c_high >= tp1:
                    return "WIN 🏆"
                elif sl > 0 and c_low <= sl:
                    return "LOSS ❌"
                    
            elif "SHORT" in direction.upper():
                if tp1 > 0 and c_low <= tp1:
                    return "WIN 🏆"
                elif sl > 0 and c_high >= sl:
                    return "LOSS ❌"

                    # 2. Αν δεν βρει σήμα στα κεριά, έλεγχος με την Τρέχουσα Τιμή (Last Price)
                    ticker = exchange.fetch_ticker(symbol)
                    last_price = float(ticker['last'])

                    if "LONG" in direction:
                        if last_price >= tp1 and tp1 > 0:
                            return "Win 🏆"
                        elif last_price <= sl and sl > 0:
                            return "Loss ❌"
                    elif "SHORT" in direction:
                        if last_price <= tp1 and tp1 > 0:
                            return "Win 🏆"
                        elif last_price >= sl and sl > 0:
                            return "Loss ❌"

                    # Αν βρει επιτυχώς το ticker αλλά δεν χτύπησε SL/TP
                    return "Pending ⏳"

                except Exception:
                    continue
        except Exception:
            continue

    return "Pending ⏳"
# --- UPLOAD & ΑΝΑΛΥΣΗ EIKONΩΝ ---
st.subheader("📷 Ανάλυση Εικόνων Chart")
uploaded_files = st.file_uploader("Επιλογή εικόνων chart...", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="chart_uploader")

if uploaded_files:
    processed_images = []
    cols = st.columns(len(uploaded_files))
    
    for idx, uploaded_file in enumerate(uploaded_files):
        img = Image.open(uploaded_file).convert("RGB")
        
        # Αύξηση Contrast για καθαρότερη ανάγνωση αριθμών
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
Είσαι ένας αυστηρός Scalping Technical Analyst.
Ανάλυσε το γράφημα ΑΠΟΚΛΕΙΣΤΙΚΑ για ULTRA-SHORT SCALPING (Trades διάρκειας 15 λεπτών έως 2 ωρών).

ΑΥΣΤΗΡΟΙ ΚΑΝΟΝΕΣ ΠΟΣΟΣΤΩΝ:
1. **Pair**: Διάβασε το ζεύγος ΑΚΡΙΒΩΣ όπως αναγράφεται πάνω αριστερά στο chart (π.χ. SUI/USDC).
2. **Direction**: 
   - Αν o RSI είναι πάνω από 70 -> SHORT.
   - Αν o RSI είναι κάτω από 30 -> LONG.
   - Διαφορετικά ακολούθησε την τοπική τάση.
3. **Entry Price**: Χρησιμοποίησε ΑΚΡΙΒΩΣ την τιμή κλεισίματος (C / Close) που αναγράφεται πάνω αριστερά.
4. **Stop Loss (SL) & Take Profit (TP)** (Πολύ στενά για scalping):
   - Αν υπάρχει εργαλείο Long/Short Position στο chart, διάβασε ΑΚΡΙΒΩΣ τους αριθμούς του.
   - Αν ΔΕΝ υπάρχει εργαλείο, υπολόγισε μαθηματικά:
     * Για SHORT: SL = Entry * 1.005 (0.5% πάνω), TP1 = Entry * 0.985 (1.5% κάτω).
     * Για LONG:  SL = Entry * 0.995 (0.5% κάτω), TP1 = Entry * 1.015 (1.5% πάνω).

ΜΗΝ δίνεις μακρινούς στόχους swing trading (όπως 2% ή 4%). Θέλουμε μόνο την αμέσως επόμενη μικρή κίνηση.

Επίστρεψε ΑΠΟΚΛΕΙΣΤΙΚΑ ένα JSON object στη μορφή:
{"pair": "SUI/USDC", "direction": "LONG", "entry": 0.0, "sl": 0.0, "tp1": 0.0}
"""
                    response = None
                    for attempt in range(4):
                        try:
                            response = client.models.generate_content(
                                model='gemini-3.6-flash',
                                contents=processed_images + [prompt],
                                config=types.GenerateContentConfig(
                                    temperature=0.0,
                                    seed=42,
                                    response_mime_type="application/json",
                                    response_schema=TradeSetup,
                                )
                            )
                            break
                        except Exception as e:
                            if ("429" in str(e) or "503" in str(e)) and attempt < 3:
                                time.sleep(5 * (attempt + 1))
                                continue
                            else:
                                raise e
                    
                    st.session_state["parsed_trade"] = json.loads(response.text)
                    st.success("Η ανάλυση ολοκληρώθηκε!")

                except Exception as e:
                    st.error(f"Σφάλμα κατά την ανάλυση: {e}")
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
            df_history["Status"] = df_history.apply(check_trade_status, axis=1)
            df_history.to_csv(LOG_FILE, index=False)
            st.success("Το ιστορικό ενημερώθηκε!")
            st.rerun()

st.dataframe(df_history, use_container_width=True)

if st.button("🗑️ Καθαρισμός Ιστορικού", key="clear_log_btn"):
    df_empty = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Analysis"])
    df_empty.to_csv(LOG_FILE, index=False)
    st.rerun()
    # --- ΑΥΤΟΜΑΤΟΣ ΥΠΟΛΟΓΙΣΜΟΣ ΡΙΣΚΟΥ & POSITION SIZE ---
st.markdown("---")
st.subheader("⚖️ Υπολογισμός Ρίσκου & Position Size")

# 1. Inputs για Κεφάλαιο, Ρίσκο & Leverage με μοναδικά keys
col_acc1, col_acc2, col_acc3 = st.columns(3)
with col_acc1:
    account_balance = st.number_input("Συνολικό Κεφάλαιο ($)", value=50.0, step=10.0, key="risk_calc_balance")
with col_acc2:
    risk_percentage = st.number_input("Ρίσκο ανά Trade (%)", value=1.0, step=0.5, key="risk_calc_pct")
with col_acc3:
    leverage = st.number_input("Leverage (x)", value=10, min_value=1, max_value=100, step=1, key="risk_calc_lev")

# 2. Τραβάμε τις τιμές αυτόματα από το session state ή το CSV
try:
    parsed = st.session_state.get("parsed_trade", {})
    if parsed:
        e_val = float(str(parsed.get("entry", 0)).replace(",", "."))
        s_val = float(str(parsed.get("sl", 0)).replace(",", "."))
        t_val = float(str(parsed.get("tp1", 0)).replace(",", "."))
    else:
        # Αν το session state είναι άδειο, παίρνουμε το τελευταίο trade από το CSV
        df_last = pd.read_csv(LOG_FILE)
        if not df_last.empty:
            e_val = float(str(df_last.iloc[0]["Entry"]).replace(",", "."))
            s_val = float(str(df_last.iloc[0]["SL"]).replace(",", "."))
            t_val = float(str(df_last.iloc[0]["TP1"]).replace(",", "."))
        else:
            e_val, s_val, t_val = 0.0, 0.0, 0.0
except (ValueError, TypeError, Exception):
    e_val, s_val, t_val = 0.0, 0.0, 0.0

# 3. Υπολογισμοί & Εμφάνιση
if e_val > 0 and s_val > 0 and e_val != s_val:
    risk_amount_usd = account_balance * (risk_percentage / 100.0)
    price_risk_per_unit = abs(e_val - s_val)
    
    position_size_units = risk_amount_usd / price_risk_per_unit
    position_size_usd = position_size_units * e_val
    margin_required = position_size_usd / leverage  # Δικά σου λεφτά με μόχλευση
    
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
