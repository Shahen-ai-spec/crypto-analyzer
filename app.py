import streamlit as st
from google import genai
from PIL import Image

st.set_page_config(page_title="Crypto Chart Analyzer", page_icon="📈")
st.title("📈 Crypto Chart Analyzer")
st.write("Ανέβασε screenshots ή φωτογραφίες από το chart σου για να λάβεις High-Probability Trade Setup.")

# Ανάκτηση API Key από τα Secrets του Streamlit ή από τη Sidebar
api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

# Επιλογή πολλαπλών αρχείων (screenshots & φωτογραφίες κάμερας)
uploaded_files = st.file_uploader(
    "Επιλογή εικόνων chart (Screenshots / Φωτογραφίες)...", 
    type=["png", "jpg", "jpeg", "webp"], 
    accept_multiple_files=True
)

if uploaded_files:
    images = []
    # Εμφάνιση των εικόνων που ανέβηκαν
    cols = st.columns(len(uploaded_files))
    for idx, uploaded_file in enumerate(uploaded_files):
        try:
            # Μετατροπή σε RGB για αποφυγή σφαλμάτων EXIF/Android camera formats
            img = Image.open(uploaded_file).convert("RGB")
            images.append(img)
            with cols[idx]:
                st.image(img, caption=f"Εικόνα {idx+1}", use_container_width=True)
        except Exception as e:
            st.error(f"Σφάλμα κατά την ανάγνωση της εικόνας {uploaded_file.name}: {e}")

    if st.button("🚀 Ανάλυση Chart"):
        if not api_key:
            st.error("Δεν βρέθηκε API Key! Παρακαλώ προσθέστε το στα Secrets ή στη sidebar.")
        else:
            with st.spinner("Γίνεται ανάλυση των διαγραμμάτων..."):
                try:
                    client = genai.Client(api_key=api_key)
                    
                    prompt = """
Είσαι ένας εξειδικευμένος Senior Price Action & Market Structure Analyst για Crypto Futures.
Ανάλυσε το chart στις εικόνες εφαρμόζοντας τις εξής αρχές:

1. MARKET STRUCTURE & TREND:
   - Προσδιόρισε τη δομή της τάσης (Higher Highs/Higher Lows ή Lower Highs/Lower Lows).
   - Εντόπισε τα κύρια Liquidity Pools (Equal Highs/Lows, Wick Sweeps).

2. ENTRY CONDITIONS (Αυστηροί Κανόνες):
   - Μην προτείνεις ποτέ εγγραφή (Entry) "στο κενό". Το entry πρέπει να είναι σε Order Block, Fair Value Gap (FVG) ή Retest επιπέδου Support/Resistance.
   - Απαγορεύεται το Risk/Reward Ratio κάτω από 1:2.

3. ΔΟΜΗ ΑΝΑΦΟΡΑΣ (Στα Ελληνικά):
   • Τάση & Δομή: (π.χ. Bearish Market Structure)
   • Βασικές Ζώνες: (Support, Resistance, FVG)
   • HIGH PROBABILITY TRADE SETUP:
     - Direction: LONG / SHORT
     - Trigger: (Τι πρέπει να περιμένει ο trader στο 5m, π.χ. Bearish Engulfing)
     - Entry Zone: $XX.XX - $XX.XX
     - Stop Loss: $XX.XX (Πίσω από το invalidation swing)
     - TP1: $XX.XX (50% κλείσιμο + Move SL to Breakeven)
     - TP2: $XX.XX (Final Target)
     - Risk/Reward: 1:X
   • Invalidation: (Ακριβές κλείσιμο κεριού που ακυρώνει το trade)
"""
                    
                    # Αποστολή όλων των εικόνων μαζί με το prompt στο Gemini
                    contents = images + [prompt]
                    
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=contents
                    )
                    
                    st.success("Η ανάλυση ολοκληρώθηκε!")
                    st.markdown("### 📊 Αποτέλεσμα Ανάλυσης")
                    st.markdown(response.text)
                    
                except Exception as e:
                    st.error(f"Προέκυψε σφάλμα κατά την ανάλυση: {e}")
