import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime
from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel, Field

st.set_page_config(page_title="Crypto Chart Analyzer & Auto Trade Log", page_icon="📈", layout="wide")
st.title("📈 Crypto Chart Analyzer & Auto Trade Log")

LOG_FILE = "trade_log.csv"

# Αρχικοποίηση CSV αν δεν υπάρχει
if not os.path.exists(LOG_FILE):
    df_init = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Analysis"])
    df_init.to_csv(LOG_FILE, index=False)

api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

# Pydantic Schema για Structured JSON Output
class TradeSetup(BaseModel):
    pair: str = Field(description="Το ζεύγος κρυπτονομίσματος, π.χ. HYPEUSDC ή BTCUSDT")
    direction: str = Field(description="LONG ή SHORT")
    entry: str = Field(description="Τιμή ή εύρος εισόδου, π.χ. 59.55")
    sl: str = Field(description="Τιμή Stop Loss, π.χ. 59.85")
    tp1: str = Field(description="Τιμή Take Profit 1, π.χ. 59.00")
    tp2: str = Field(description="Τιμή Take Profit 2, π.χ. 58.30")
    analysis_summary: str = Field(description="Σύντομη ελληνική περιγραφή της τάσης, του trigger και του invalidation")

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
                    Ανάλυσε το chart στις εικόνες και εξαγάγε ένα High Probability Trade Setup.
                    Συμπλήρωσε όλα τα πεδία του JSON αυστηρά βάσει της ανάλυσης του Price Action.
                    """
                    
                    # Κλήση με Structured JSON Output
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=images + [prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=TradeSetup,
                        )
                    )
                    
                    # Parsing του JSON
                    trade_data = json.loads(response.text)
                    
                    st.success("Η ανάλυση ολοκληρώθηκε επιτυχώς!")
                    
                    # Εμφάνιση Αποτελεσμάτων
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Pair", trade_data.get("pair", "N/A"))
                    col2.metric("Direction", trade_data.get("direction", "N/A"))
                    col3.metric("Entry", trade_data.get("entry", "N/A"))
                    col4.metric("Stop Loss", trade_data.get("sl", "N/A"))
                    
                    col5, col6 = st.columns(2)
                    col5.metric("Take Profit 1", trade_data.get("tp1", "N/A"))
                    col6.metric("Take Profit 2", trade_data.get("tp2", "N/A"))
                    
                    st.markdown("#### 📝 Σύνοψη Ανάλυσης")
                    st.info(trade_data.get("analysis_summary", ""))
                    
                    # Καταγραφή στο CSV
                    new_entry = {
                        "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Pair": trade_data.get("pair", "N/A"),
                        "Direction": trade_data.get("direction", "N/A"),
                        "Entry": trade_data.get("entry", "N/A"),
                        "SL": trade_data.get("sl", "N/A"),
                        "TP1": trade_data.get("tp1", "N/A"),
                        "TP2": trade_data.get("tp2", "N/A"),
                        "Status": "Pending",
                        "Analysis": trade_data.get("analysis_summary", "")
                    }
                    
                    df_log = pd.read_csv(LOG_FILE)
                    df_log = pd.concat([pd.DataFrame([new_entry]), df_log], ignore_index=True)
                    df_log.to_csv(LOG_FILE, index=False)
                    st.toast("Το trade αποθηκεύτηκε αυτόματα στο Trade Log!")

                except Exception as e:
                    st.error(f"Σφάλμα: {e}")

# --- ΜΟΝΙΜΟ ΙΣΤΟΡΙΚΟ (TRADE LOG) ---
st.divider()
st.subheader("📜 Μόνιμο Ιστορικό Αναλύσεων (Trade Log)")

df_history = pd.read_csv(LOG_FILE)

# Επεξεργάσιμος Πίνακας (st.data_editor) για να μπορείς να αλλάζεις το Status
edited_df = st.data_editor(
    df_history,
    column_config={
        "Status": st.column_config.SelectboxColumn(
            "Status",
            options=["Pending", "Win 🏆", "Loss ❌", "Canceled 🚫"],
            required=True
        )
    },
    disabled=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Analysis"],
    use_container_width=True,
    num_rows="dynamic"
)

if st.button("💾 Αποθήκευση Αλλαγών Status"):
    edited_df.to_csv(LOG_FILE, index=False)
    st.success("Οι αλλαγές αποθηκεύτηκαν!")

if st.button("🗑️ Καθαρισμός Ιστορικού"):
    df_empty = pd.DataFrame(columns=["Date", "Pair", "Direction", "Entry", "SL", "TP1", "TP2", "Status", "Analysis"])
    df_empty.to_csv(LOG_FILE, index=False)
    st.rerun()
