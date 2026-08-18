import streamlit as st
from google import genai
from PIL import Image

# Ρύθμιση τίτλου της εφαρμογής
st.set_page_config(page_title="Crypto Chart Analyzer", page_icon="📈")
st.title("📈 Crypto Chart Analyzer")
st.write("Ανέβασε το screenshot του chart σου για να λάβεις High-Probability Trade Setup.")

# Πλευρική μπάρα για εισαγωγή του API Key
st.sidebar.header("Ρυθμίσεις")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Εισάγετε το API Key από το Google AI Studio")

# Κουμπί για ανεβάσμα εικόνας
uploaded_file = st.file_uploader("Επιλογή εικόνας chart...", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    # Εμφάνιση της εικόνας που ανέβηκε
    image = Image.open(uploaded_file)
    st.image(image, caption="Uploaded Chart", use_container_width=True)
    
    # Κουμπί έναρξης ανάλυσης
    if st.button("🚀 Ανάλυση Chart"):
        if not api_key:
            st.error("Παρακαλώ εισάγετε το Gemini API Key στην αριστερή μπάρα!")
        else:
            with st.spinner("Γίνεται ανάλυση του διαγράμματος..."):
                try:
                    # Δημιουργία client
                    client = genai.Client(api_key=api_key)
                    
                    # Το prompt για 1 High Probability σενάριο
                    prompt = """
                    Είσαι ένας Senior Crypto Price Action Analyst.
                    Ανάλυσε το chart στην εικόνα και δώσε μου ΜΟΝΟ ΕΝΑ σενάριο (αυτό με τη μεγαλύτερη πιθανότητα επιτυχίας - High Probability Trade Setup).

                    Δώσε μου τη δομημένη αναφορά στα Ελληνικά με την εξής μορφή:

                    1. **Κύρια Τάση & Σχηματισμός:** (Σύντομη περιγραφή του pattern/trend)
                    2. **Βασικά Επίπεδα:** Support & Resistance
                    3. **HIGH PROBABILITY TRADE:** (Επίλεξε ΜΟΝΟ Long ή ΜΟΝΟ Short)
                       - **Trigger (Σημείο Επιβεβαίωσης):** Τι πρέπει να κάνει η τιμή για να μπούμε;
                       - **Entry (Τιμή Εισόδου):**
                       - **Stop Loss (SL):**
                       - **Take Profit (TP1 & TP2):**
                       - **Risk/Reward Ratio:**

                    4. **Invalidation:** Πότε ακυρώνεται τελείως το σενάριο;
                    """
                    
                    # Εκτέλεση με το μοντέλο gemini-3.6-flash
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=[image, prompt]
                    )
                    
                    st.success("Η ανάλυση ολοκληρώθηκε!")
                    st.markdown("### 📊 Αποτέλεσμα Ανάλυσης")
                    st.markdown(response.text)
                    
                except Exception as e:
                    st.error(f"Προέκυψε σφάλμα: {e}")
