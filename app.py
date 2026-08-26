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
# --- ΑΡΧΙΚΟΠΟΙΗΣΗ SESSION STATE (ΒΑΛΤΕ ΤΟ ΣΤΗΝ ΑΡΧΗ ΤΟΥ APP.PY) ---
if "saved_trades" not in st.session_state:
    st.session_state.saved_trades = []

if "saved_trades_list" not in st.session_state:
    st.session_state.saved_trades_list = []
# --- ΑΠΟ ΕΔΩ ΚΑΙ ΚΑΤΩ ΦΟΡΤΩΝΕΙ Η ΕΦΑΡΜΟΓΗ ---
st.title("🐼 PANDA CRYPTO Analyzer")

LOG_FILE = "trade_log.csv"

# Αρχικοποίηση CSV αν δεν υπάρχει
if not os.path.exists(LOG_FILE):
    df_init = pd.DataFrame(
        columns=[
            "Date",
            "Pair",
            "Direction",
            "Entry",
            "SL",
            "TP1",
            "TP2",
            "Status",
            "Reason",
        ]
    )
    df_init.to_csv(LOG_FILE, index=False)

# Διάβασμα του API Key απευθείας από τα Secrets
api_key = st.secrets.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)


# Pydantic Schema για το Gemini AI
class TradeSetup(BaseModel):
    pair: str
    direction: str  # "LONG", "SHORT", ή "NO TRADE"
    entry: float
    sl: float
    tp1: float
    reason: str  # Αιτιολογία για το trade


# --- ΒΟΗΘΗΤΙΚΗ ΣΥΝΑΡΤΗΣΗ ΕΛΕΓΧΟΥ LIVE STATUS (CCXT) ---
def check_trade_status(row):
    """Ελέγχει live αν ένα trade χτύπησε TP1 ή SL χρησιμοποιώντας το CCXT (Bybit/Binance)."""
    status = str(row.get("Status", "Pending"))
    if status in ["TP Hit", "SL Hit", "Closed"]:
        return status

    pair = str(row.get("Pair", "")).upper().replace("-", "/").replace("USD", "USDT")
    if not pair or "/" not in pair:
        return status

    try:
        exchange = ccxt.bybit()
        ticker = exchange.fetch_ticker(pair)
        current_price = ticker["last"]

        entry = float(row.get("Entry", 0))
        sl = float(row.get("SL", 0))
        tp1 = float(row.get("TP1", 0))
        direction = str(row.get("Direction", "")).upper()

        if "LONG" in direction:
            if current_price >= tp1 and tp1 > 0:
                return "TP Hit"
            elif current_price <= sl and sl > 0:
                return "SL Hit"
        elif "SHORT" in direction:
            if current_price <= tp1 and tp1 > 0:
                return "TP Hit"
            elif current_price >= sl and sl > 0:
                return "SL Hit"
    except Exception:
        pass

    return "Pending"


# --- ΤΕΧΝΙΚΟΙ ΔΕΙΚΤΕΣ & MULTI-TIMEFRAME ANALYZER ---
def calculate_rsi(prices, period=14):
    """Υπολογισμός RSI (14)"""
    delta = pd.Series(prices).diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]


# --- ΒΕΛΤΙΩΜΕΝΗ ΣΥΝΑΡΤΗΣΗ ΑΥΤΟΜΑΤΗΣ ΑΝΑΛΥΣΗΣ ---
def get_auto_analysis(symbol_ticker="SOL-USD"):
    try:
        # Αυτόματη διόρθωση format (π.χ. BTC -> BTC-USD, BTC/USDT -> BTC-USD)
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

            # --- ΛΟΓΙΚΗ ΣΗΜΑΤΩΝ ΜΕ ΥΠΟΛΟΓΙΣΜΟ 1:3 RRR ---
            if current_price >= fib_618 or rsi_1h <= 45:
                # LONG SETUP
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
                # SHORT SETUP
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
            st.error(
                f"Δεν βρέθηκαν δεδομένα για το {symbol_ticker}. Τσέκαρε το σύμβολο (π.χ. BTC, ETH, SOL)."
            )
    except Exception as e:
        st.error(f"Error: {str(e)}")
    return None


# --- UI ΑΥΤΟΜΑΤΗΣ ΑΝΑΛΥΣΗΣ ---
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
                "Ticker": analysis["coin"],
                "Price": analysis["price"],
                "Signal": analysis["direction"],
                "TP1": analysis["tp1"],
                "SL": analysis["sl"],
                "4H Trend": analysis["trend_4h"],
            }
            st.session_state.saved_trades_list.append(new_trade)
            st.success(f"Το trade για {analysis['coin']} αποθηκεύτηκε!")
# --- ΑΡΧΙΚΟΠΟΙΗΣΗ ΜΝΗΜΗΣ TRADES ---
if "saved_trades_list" not in st.session_state:
    st.session_state.saved_trades_list = []

# Φόρτωση από CSV στην αρχή αν υπάρχει
if os.path.exists(LOG_FILE) and not st.session_state.saved_trades_list:
    try:
        df_disk = pd.read_csv(LOG_FILE)
        st.session_state.saved_trades_list = df_disk.to_dict("records")
    except Exception:
        pass

# --- ΦΟΡΜΑ ΕΠΙΒΕΒΑΙΩΣΗΣ ΚΑΙ ΑΠΟΘΗΚΕΥΣΗΣ ---
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

        submit_save = st.form_submit_button("💾 Αποθήκευση στο Log")

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

        # 1. Αποθήκευση στη ζωντανή μνήμη του Streamlit
        st.session_state.saved_trades_list.append(new_entry)

        # 2. Αποθήκευση στο αρχείο CSV
        df_save = pd.DataFrame(st.session_state.saved_trades_list)
        df_save.to_csv(LOG_FILE, index=False)

        # 3. Καθαρισμός φόρμας
        st.session_state["parsed_trade"] = None
        st.success("Το trade αποθηκεύτηκε επιτυχώς!")
        st.rerun()


# --- LIVE TRADE TRACKER (ΕΜΦΑΝΙΖΕΤΑΙ ΠΑΝΤΑ) ---
st.divider()
st.subheader("📜 Live Trade Log Tracker")

if st.session_state.saved_trades_list:
    df_display = pd.DataFrame(st.session_state.saved_trades_list)
    st.dataframe(df_display, use_container_width=True)

    # --- ΔΙΑΓΡΑΦΗ TRADES ---
    st.markdown("#### 🗑️ Διαχείριση / Διαγραφή")
    col_del1, col_del2 = st.columns([2, 1])

    with col_del1:
        trade_options = [
            f"{idx}: {row['Pair']} ({row['Direction']}) - {row['Date']}"
            for idx, row in df_display.iterrows()
        ]
        selected_to_delete = st.selectbox(
            "Επίλεξε Trade για διαγραφή:", trade_options
        )

        if st.button("❌ Διαγραφή Επιλεγμένου Trade"):
            row_idx = int(selected_to_delete.split(":")[0])
            st.session_state.saved_trades_list.pop(row_idx)

            # Ενημέρωση CSV
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

# --- ΦΟΡΜΑ ΕΠΙΒΕΒΑΙΩΣΗΣ ΚΑΙ ΔΙΟΡΘΩΣΗΣ ΔΕΔΟΜΕΝΩΝ ---
if "parsed_trade" in st.session_state and st.session_state["parsed_trade"]:
    trade_data = st.session_state["parsed_trade"]
    st.markdown("### 📝 Επιβεβαίωση / Διόρθωση Στοιχείων Trade")

    with st.form("confirm_trade_form"):
        col_f1, col_f2 = st.columns(2)

        with col_f1:
            f_pair = st.text_input(
                "Pair", value=trade_data.get("pair", "SUI/USDT")
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

        submit_save = st.form_submit_button("💾 Αποθήκευση στο CSV Log")

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
            "Reason": f_reason,
        }

        if os.path.exists(LOG_FILE):
            df_log = pd.read_csv(LOG_FILE)
        else:
            df_log = pd.DataFrame()

        df_log = pd.concat(
            [df_log, pd.DataFrame([new_entry])], ignore_index=True
        )
        df_log.to_csv(LOG_FILE, index=False)

        st.session_state["parsed_trade"] = None
        st.success("Το trade αποθηκεύτηκε επιτυχώς!")
        st.rerun()

# --- LIVE TRADE TRACKER ---
st.divider()
st.subheader("📜 Live Trade Log Tracker (CSV File)")

df_history = pd.read_csv(LOG_FILE)

col_a, col_b = st.columns([1, 2])
with col_a:
    if st.button("🔄 Ενημέρωση Live Status Trades", key="update_status_btn"):
        with st.spinner("Έλεγχος ζωντανών τιμών από την αγορά..."):
            if not df_history.empty:
                df_history["Status"] = df_history.apply(
                    check_trade_status, axis=1
                )
                df_history.to_csv(LOG_FILE, index=False)
            st.rerun()

st.dataframe(df_history, use_container_width=True)

# --- ΔΙΑΓΡΑΦΗ TRADES (ΑΣΦΑΛΗΣ ΕΛΕΓΧΟΣ ΣΤΗΛΩΝ) ---
    st.markdown("#### 🗑️ Διαχείριση / Διαγραφή")
    col_del1, col_del2 = st.columns([2, 1])

    with col_del1:
        trade_options = []
        for idx, row in df_display.iterrows():
            # Ασφαλής ανάγνωση Ticker/Pair
            pair_name = row.get("Pair") or row.get("Ticker") or "Unknown"
            direction = row.get("Direction") or row.get("Signal") or "N/A"
            date_val = row.get("Date") or "Live"

            trade_options.append(f"{idx}: {pair_name} ({direction}) - {date_val}")

        selected_to_delete = st.selectbox(
            "Επίλεξε Trade για διαγραφή:", trade_options
        )

        if st.button("❌ Διαγραφή Επιλεγμένου Trade"):
            row_idx = int(selected_to_delete.split(":")[0])
            st.session_state.saved_trades_list.pop(row_idx)

            # Ενημέρωση CSV
            df_updated = pd.DataFrame(st.session_state.saved_trades_list)
            df_updated.to_csv(LOG_FILE, index=False)

            st.success("Το trade διαγράφηκε!")
            st.rerun()

    with col_del2:
        st.write(" ")
        st.write(" ")
        if st.button("🗑️ Καθαρισμός Όλων", key="clear_log_btn"):
            df_empty = pd.DataFrame(
                columns=[
                    "Date",
                    "Pair",
                    "Direction",
                    "Entry",
                    "SL",
                    "TP1",
                    "TP2",
                    "Status",
                    "Reason",
                ]
            )
            df_empty.to_csv(LOG_FILE, index=False)
            st.rerun()

# --- ΑΥΤΟΜΑΤΟΣ ΥΠΟΛΟΓΙΣΜΟΣ ΡΙΣΚΟΥ & POSITION SIZE ---
st.markdown("---")
st.subheader("⚖️ Υπολογισμός Ρίσκου & Position Size")

col_acc1, col_acc2, col_acc3 = st.columns(3)
with col_acc1:
    account_balance = st.number_input(
        "Συνολικό Κεφάλαιο ($)", value=50.0, step=10.0, key="risk_calc_balance"
    )
with col_acc2:
    risk_percentage = st.number_input(
        "Ρίσκο ανά Trade (%)", value=1.0, step=0.5, key="risk_calc_pct"
    )
with col_acc3:
    leverage = st.number_input(
        "Leverage (x)",
        value=10,
        min_value=1,
        max_value=100,
        step=1,
        key="risk_calc_lev",
    )

try:
    parsed = st.session_state.get("parsed_trade", {})
    if parsed:
        e_val = float(str(parsed.get("entry", 0)).replace(",", "."))
        s_val = float(str(parsed.get("sl", 0)).replace(",", "."))
        t_val = float(str(parsed.get("tp1", 0)).replace(",", "."))
    else:
        df_last = pd.read_csv(LOG_FILE)
        if not df_last.empty:
            e_val = float(str(df_last.iloc[-1]["Entry"]).replace(",", "."))
            s_val = float(str(df_last.iloc[-1]["SL"]).replace(",", "."))
            t_val = float(str(df_last.iloc[-1]["TP1"]).replace(",", "."))
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
    rrr = (
        reward_per_unit / price_risk_per_unit if price_risk_per_unit > 0 else 0
    )

    st.markdown("### 📊 Αποτελέσματα")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Μέγιστη Χασούρα", f"${risk_amount_usd:.2f}")
    c2.metric("Πιθανό Κέρδος", f"${potential_profit_usd:.2f}")
    c3.metric("Position Size ($)", f"${position_size_usd:.2f}")
    c4.metric(f"Margin (x{int(leverage)})", f"${margin_required:.2f}")
    c5.metric("Ποσότητα (Units)", f"{position_size_units:.4f}")
    c6.metric("Risk/Reward", f"1 : {rrr:.2f}")
else:
    st.info(
        "💡 Μόλις ολοκληρωθεί η ανάλυση από το AI και συμπληρωθούν το Entry & Stop Loss, θα εμφανιστούν εδώ οι υπολογισμοί."
    )
