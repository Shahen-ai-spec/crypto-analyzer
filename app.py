import streamlit as st
import pandas as pd
import os
import json
import ccxt
from datetime import datetime
from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel, Field

st.set_page_config(page_title="Crypto Analyzer & Auto-Tracker", page_icon="📈", layout="wide")
st.title("📈 Crypto Chart Analyzer & Auto-Tracker")

LOG_FILE = "trade_log.csv"

# Αρχικοποίηση CSV αν δεν υπάρχει
if not os.path.exists(LOG_FILE):
    df_init = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Analysis"])
    df_init.to_csv(LOG_FILE, index=False)

api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

# Pydantic Schema για Structured JSON Output
class TradeSetup(BaseModel):
    pair: str = Field(description="Το ζεύγος σε μορφή π.χ. BTC/USDT, SOL/USDT, HYPE/USDT")
    direction: str = Field(description="LONG ή SHORT")
    entry: float = Field(description="Τιμή εισόδου ως αριθμός (float), π.χ. 59.55")
    sl: float = Field(description="Τιμή Stop Loss ως αριθμός (float), π.χ. 59.85")
    tp1: float = Field(description="Τιμή Take Profit 1 ως αριθμός (float), π.χ. 59.00")
    tp2: float = Field(description="Τιμή Take Profit 2 ως αριθμός (float), π.χ. 58.30")
    analysis_summary: str = Field(description="Σύντομη περιγραφή Price Action")

# --- ΣΥΝΑΡΤΗΣΗ LIVE CHECK ΑΓΟΡΑΣ ---
def check_trade_status(row):
    status = str(row["Status"])
    if status in ["Win 🏆", "Loss ❌", "Canceled 🚫"]:
        return status  # Αν έχει ήδη ολοκληρωθεί, μην το ξαναελέγχεις

    pair = str(row["Pair"]).upper().strip()
    direction = str(row["Direction"]).upper().strip()
    
    try:
        entry = float(row["Entry"])
        sl = float(row["SL"])
        tp1 = float(row["TP1"])
    except (ValueError, TypeError):
        return status

    try:
        # Χρήση του Bybit API μέσω CCXT
        exchange = ccxt.bybit()
        ticker = exchange.fetch_ticker(pair)
        current_price = ticker['last']
        high_price = ticker['high']
        low_price = ticker['low']

        if direction == "LONG":
            if low_price <= sl:
                return "Loss ❌"
            elif high_price >= tp1:
                return "Win 🏆"
        elif direction == "SHORT":
            if high_price >= sl:
                return "Loss ❌"
            elif low_price <= tp1:
                return "Win 🏆"

    except Exception:
        # Αν αποτύχει η Bybit, δοκιμή με Binance
        try:
            exchange = ccxt.binance()
            ticker = exchange.fetch_ticker(pair)
            current_price = ticker['last']
            high_price = ticker['high']
            low_price = ticker['low']

            if direction == "LONG":
                if low_price <= sl:
                    return "Loss ❌"
                elif high_price >= tp1:
                    return "Win 🏆"
            elif direction == "SHORT":
                if high_price >= sl:
                    return "Loss ❌"
                elif low_price <= tp1:
                    return "Win 🏆"
        except Exception:
            pass

    return "Pending ⏳"

# --- UPLOAD & ΑΝΑΛΥΣΗ EIKONΩΝ ---
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
                    Είσαι ένας Senior Crypto Price Action Analyst.
                    Ανάλυσε το chart και βγάλε ένα High Probability Trade Setup.
                    Συμπλήρωσε τα πεδία του JSON. Το pair να είναι σε μορφή 'SYMBOL/USDT' (π.χ. SOL/USDT).
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
                    
                    # Προβολή
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Pair", trade_data.get("pair"))
                    col2.metric("Direction", trade_data.get("direction"))
                    col3.metric("Entry", trade_data.get("entry"))
                    col4.metric("Stop Loss", trade_data.get("sl"))
                    
                    col5, col6 = st.columns(2)
                    col5.metric("Take Profit 1", trade_data.get("tp1"))
                    col6.metric("Take Profit 2", trade_data.get("tp2"))
                    
                    st.info(trade_data.get("analysis_summary"))
                    
                    # Καταγραφή
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
