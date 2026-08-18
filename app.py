import streamlit as st
from google import genai
from PIL import Image

st.set_page_config(page_title="Crypto Chart Analyzer", page_icon="📈")
st.title("📈 Crypto Chart Analyzer")
st.write("Ανέβασε το screenshot του chart σου για να λάβεις High-Probability Trade Setup.")

# Ανάκτηση API Key από τα Secrets του Streamlit ή από τη Sidebar
api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else st.sidebar.text_input("Gemini API Key", type="password")

uploaded_file = st.file_uploader("Επιλογή εικόνας chart...", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="Uploaded Chart", use_container_width=True)
    
    if st.button("🚀 Ανάλυση Chart"):
        if not api_key:
            st.error("Δεν βρέθηκε API Key! Παρακαλώ προσθέστε το στα Secrets ή στη sidebar.")
        else:
            with st.spinner("Γίνεται ανάλυση του διαγράμματος..."):
                try:
                    client = genai.Client(api_key=api_key)
                    
                    prompt = """
                    Είσαι ένας Senior Crypto Price Action Analyst.
                    Ανάλυσε το chart στην εικόνα και δώσε μου ΜΟΝΟ ΕΝΑ σενάριο (High Probability Trade Setup).

                    Δώσε μου τη δομημένη αναφορά στα Ελληνικά:
                    1. **Κύρια Τάση & Σχηματισμός:**
                    2. **Βασικά Επίπεδα:** Support & Resistance
                    3. **HIGH PROBABILITY TRADE:** (Long/Short, Trigger, Entry, SL, TP1/TP2, Risk/Reward)
                    4. **Invalidation:**
                    """
                    
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=[image, prompt]
                    )
                    
                    st.success("Η ανάλυση ολοκληρώθηκε!")
                    st.markdown("### 📊 Αποτέλεσμα Ανάλυσης")
                    st.markdown(response.text)
                    
                except Exception as e:
                    st.error(f"Προέκυψε σφάλμα: {e}")
