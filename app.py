import json
import os
import re
import time
from datetime import datetime

import ccxt
from google import genai
from google.genai import types
import pandas as pd
from PIL import Image, ImageEnhance
from pydantic import BaseModel, Field
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

st.title("🐼 PANDA CRYPTO Analyzer")

LOG_FILE = "trade_log.csv"


# --- ΦΟΡΤΩΣΗ ΔΕΔΟΜΕΝΩΝ (ΣΤΑΘΕΡΗ ΑΝΕΞΑΡΤΗΤΩΣ REBOOT) ---
def load_saved_trades():
    if os.path.exists(LOG_FILE):
        try:
            df_disk = pd.read_csv(LOG_FILE)
            return df_disk.to_dict("records")
        except Exception:
            return []
    return []


# Αρχικοποίηση Session State πάντα από το αρχείο
if "saved_trades_list" not in st.session_state:
    st.session_state.saved_trades_list = load_saved_trades()

# API Client
api_key = st.secrets.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)
