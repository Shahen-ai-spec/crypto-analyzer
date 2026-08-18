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
                    Είσαι ένας Senior Crypto Price Action Analyst.
                    Ανάλυσε το chart (ή τα charts) στις εικόνες και δώσε μου ΜΟΝΟ ΕΝΑ σενάριο (High Probability Trade Setup).

                    Δώσε μου τη δομημένη αναφορά στα Ελληνικά:
                    1. **Κύρια Τάση & Σχηματισμός:**
                    2. **Βασικά Επίπεδα:** Support & Resistance
                    3. **HIGH PROBABILITY TRADE:** (Long/Short, Trigger, Entry, SL, TP1/TP2, Risk/Reward)
                    4. **Invalidation:**
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
