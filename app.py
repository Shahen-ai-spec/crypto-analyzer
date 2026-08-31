import json
import os
import re
import sqlite3
import time
from datetime import datetime

from google import genai
from google.genai import types
import pandas as pd
from PIL import Image, ImageEnhance
from pydantic import BaseModel, Field
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

# --- ΡΥΘΜΙΣΗ ΣΕΛΙΔΑΣ ---
st.set_page_config(page_title="PANDA CRYPTO Analyzer", layout="wide")
st.title("🐼 PANDA CRYPTO Analyzer")

LOG_FILE = "trade_log.csv"
DB_FILE = "panda_analyzer.db"


# --- 1. SQLite ΒΑΣΗ ΔΕΔΟΜΕΝΩΝ ---
def init_db():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            pair TEXT,
            direction TEXT,
            entry REAL,
            sl REAL,
            tp1 REAL,
            status TEXT,
            reason TEXT
        )
    """)
  conn.commit()
  conn.close()


def save_trade_to_db(trade):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO trades (date, pair, direction, entry, sl, tp1, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          trade.get("Date"),
          trade.get("Pair"),
          trade.get("Direction"),
          trade.get("Entry"),
          trade.get("SL"),
          trade.get("TP1"),
          trade.get("Status", "Pending"),
          trade.get("Reason", ""),
      ),
  )
  conn.commit()
  conn.close()


def load_trades_from_db():
  init_db()
  conn = sqlite3.connect(DB_FILE)
  df = pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC", conn)
  conn.close()
  if not df.empty:
    df.rename(
        columns={
            "date": "Date",
            "pair": "Pair",
            "direction": "Direction",
            "entry": "Entry",
            "sl": "SL",
            "tp1": "TP1",
            "status": "Status",
            "reason": "Reason",
        },
        inplace=True,
    )
    return df.to_dict("records")
  return []


def delete_trade_from_db(trade_id):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
  conn.commit()
  conn.close()


def clear_db():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("DELETE FROM trades")
  conn.commit()
  conn.close()


init_db()


def load_saved_trades():
  db_trades = load_trades_from_db()
  if db_trades:
    return db_trades
  if os.path.exists(LOG_FILE):
    try:
      df_disk = pd.read_csv(LOG_FILE)
      trades = df_disk.to_dict("records")
      for t in trades:
        save_trade_to_db(t)
      return load_trades_from_db()
    except Exception:
      return []
  return []


if "saved_trades_list" not in st.session_state:
  st.session_state.saved_trades_list = load_saved_trades()

api_key = st.secrets.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None


class TradeSetup(BaseModel):
  pair: str
  direction: str
  entry: float
  sl: float
  tp1: float
  reason: str


# --- 2. ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ & ANΑΛΥΣΗ ---
def clean_val(val):
  try:
    match = re.search(r"\d+\.?\d*", str(val))
    return float(match.group()) if match else 0.0
  except Exception:
    return 0.0


def calculate_rsi(prices, period=14):
  if not prices or len(prices) <= period:
    return 50.0
  delta = pd.Series(prices).diff()
  gain = delta.where(delta > 0, 0).rolling(window=period).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
  rs = gain / loss
  rsi = 100 - (100 / (1 + rs))
  if rsi.empty or pd.isna(rsi.iloc[-1]):
    return 50.0
  return rsi.iloc[-1]


def get_auto_analysis(symbol_ticker="SOL"):
  try:
    raw = symbol_ticker.strip().lower().replace("/", "").replace("-", "")
    if raw.endswith("usdt") or raw.endswith("usdc"):
      raw = raw[:-4]
    elif raw.endswith("usd"):
      raw = raw[:-3]

    crypto_map = {
        "sol": "solana",
        "btc": "bitcoin",
        "eth": "ethereum",
        "xrp": "ripple",
        "ada": "cardano",
        "avax": "avalanche-2",
        "doge": "dogecoin",
        "link": "chainlink",
        "sui": "sui",
        "near": "near",
    }
    coin_id = crypto_map.get(raw, raw)

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days=7"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=10)

    close_1h = []
    if res.status_code == 200:
      data = res.json()
      prices = data.get("prices", [])
      if prices:
        close_1h = [point[1] for point in prices]

    if not close_1h:
      clean_symbol = f"{raw.upper()}USDT"
      url_b = f"https://api.binance.com/api/v3/klines?symbol={clean_symbol}&interval=1h&limit=168"
      res_b = requests.get(url_b, timeout=5)
      if res_b.status_code == 200:
        data_b = res_b.json()
        if isinstance(data_b, list) and len(data_b) > 0:
          close_1h = [float(candle[4]) for candle in data_b]

    if not close_1h or len(close_1h) < 15:
      st.error(f"Δεν βρέθηκαν επαρκή δεδομένα για το '{symbol_ticker}'.")
      return None

    current_price = round(float(close_1h[-1]), 4)
    recent_high = (
        round(float(max(close_1h[-24:])), 4)
        if len(close_1h) >= 24
        else current_price
    )
    recent_low = (
        round(float(min(close_1h[-24:])), 4)
        if len(close_1h) >= 24
        else current_price
    )

    rsi_1h = round(calculate_rsi(close_1h, 14), 1)
    close_4h = close_1h[::4]
    rsi_4h = (
        round(calculate_rsi(close_4h, 14), 1) if len(close_4h) > 14 else rsi_1h
    )

    price_range = recent_high - recent_low
    fib_618 = round(recent_high - (price_range * 0.618), 4)

    sma50_4h = (
        sum(close_4h[-50:]) / len(close_4h[-50:])
        if len(close_4h) >= 50
        else current_price
    )
    trend_4h = "BULLISH" if current_price > sma50_4h else "BEARISH"

    if current_price >= fib_618 or rsi_1h <= 45:
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
        "coin": f"{raw.upper()}/USD",
        "price": current_price,
        "direction": direction,
        "tp1": tp1,
        "sl": sl,
        "rsi_1h": rsi_1h,
        "rsi_4h": rsi_4h,
        "trend_4h": trend_4h,
        "fib_618": fib_618,
    }
  except Exception as e:
    st.error(f"Σφάλμα κατά την ανάλυση: {str(e)}")
    return None


def fetch_solana_dex_data(token_address):
  try:
    if not token_address or not token_address.strip():
      return None

    clean_address = token_address.strip()
    url = f"https://api.dexscreener.com/latest/dex/tokens/{clean_address}"
    headers = {"User-Agent": "Mozilla/5.0"}

    res = requests.get(url, headers=headers, timeout=10)
    if res.status_code == 200:
      data = res.json()
      pairs = data.get("pairs")

      if pairs and isinstance(pairs, list) and len(pairs) > 0:
        sol_pairs = [
            p
            for p in pairs
            if isinstance(p, dict) and p.get("chainId") == "solana"
        ]
        best_pair = sol_pairs[0] if sol_pairs else pairs[0]

        base_token = best_pair.get("baseToken", {}) or {}
        liquidity = best_pair.get("liquidity", {}) or {}
        volume = best_pair.get("volume", {}) or {}
        txns = best_pair.get("txns", {}) or {}
        h1_txns = txns.get("h1", {}) or {}

        return {
            "name": base_token.get("name", "N/A"),
            "symbol": base_token.get("symbol", "N/A"),
            "price": float(best_pair.get("priceUsd") or 0.0),
            "liquidity": float(liquidity.get("usd") or 0.0),
            "fdv": float(best_pair.get("fdv") or 0.0),
            "volume_24h": float(volume.get("h24") or 0.0),
            "buys_1h": int(h1_txns.get("buys") or 0),
            "sells_1h": int(h1_txns.get("sells") or 0),
            "dex": str(best_pair.get("dexId", "N/A")),
            "url": str(best_pair.get("url", "#")),
        }
  except Exception as e:
    st.error(f"Σφάλμα DEX: {e}")
  return None


# --- 3. UI USER INTERFACE ---
tab_main, tab_dex = st.tabs(
    ["📊 CEX & Chart Analysis", "🪐 Solana DEX Scanner"]
)

with tab_main:
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
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Pair": analysis["coin"],
            "Direction": analysis["direction"],
            "Entry": analysis["price"],
            "SL": analysis["sl"],
            "TP1": analysis["tp1"],
            "Status": "Pending",
            "Reason": "Auto Analysis",
        }
        save_trade_to_db(new_trade)
        st.session_state.saved_trades_list = load_trades_from_db()
        pd.DataFrame(st.session_state.saved_trades_list).to_csv(
            LOG_FILE, index=False
        )
        st.success(f"Το trade για {analysis['coin']} αποθηκεύτηκε στη βάση!")
        st.rerun()

  st.divider()
  st.subheader("📷 Ανάλυση Εικόνων Chart (Gemini AI)")

  uploaded_files = st.file_uploader(
      "Επιλογή εικόνων chart...",
      type=["png", "jpg", "jpeg", "webp"],
      accept_multiple_files=True,
      key="chart_uploader",
  )

  if uploaded_files:
    processed_images = []
    cols = st.columns(len(uploaded_files))

    for idx, uploaded_file in enumerate(uploaded_files):
      img = Image.open(uploaded_file).convert("RGB")
      enhancer = ImageEnhance.Contrast(img)
      enhanced_img = enhancer.enhance(1.2)
      processed_images.append(enhanced_img)
      with cols[idx]:
        st.image(
            img, caption=f"Εικόνα {idx+1}", use_container_width=True
        )

    if st.button("🚀 Ανάλυση Chart με AI", type="primary"):
      if not client:
        st.error("Δεν βρέθηκε το GEMINI_API_KEY στα Secrets!")
      else:
        try:
          prompt = """
                    Analyze the chart image to find the best immediate trade setup (LONG or SHORT) with strict risk controls.
                    Ensure Take Profit (TP1) achieves strictly a 1:3 Risk-to-Reward Ratio (RRR = 1:3) relative to entry and buffered SL.
                    Read the exact crypto pair symbol from the chart.
                    """

          # ΕΔΩ ΕΓΙΝΕ Η ΑΛΛΑΓΗ ΣΤΟ ΝΕΟ ΜΟΝΤΕΛΟ:
          response = client.models.generate_content(
              model = 'gemini-3.6-flash'
              contents=processed_images + [prompt],
              config=types.GenerateContentConfig(
                  temperature=0.2,
                  response_mime_type="application/json",
                  response_schema=TradeSetup,
              ),
          )
          st.session_state["parsed_trade"] = response.parsed.model_dump()
          st.success("Η ανάλυση του screenshot ολοκληρώθηκε!")
        except Exception as e:
          st.error(f"Σφάλμα κατά την ανάλυση: {e}")

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

      submit_save = st.form_submit_button("💾 Αποθήκευση AI Trade")

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
      save_trade_to_db(new_entry)
      st.session_state.saved_trades_list = load_trades_from_db()
      pd.DataFrame(st.session_state.saved_trades_list).to_csv(
          LOG_FILE, index=False
      )
      st.session_state["parsed_trade"] = None
      st.success("Το trade αποθηκεύτηκε επιτυχώς!")
      st.rerun()

  st.divider()
  st.subheader("📜 Live Trade Log Tracker (Database SQL)")
  st.session_state.saved_trades_list = load_trades_from_db()

  if st.session_state.saved_trades_list:
    df_display = pd.DataFrame(st.session_state.saved_trades_list)
    st.dataframe(df_display, use_container_width=True)

    st.markdown("#### 🗑️ Διαχείριση / Διαγραφή")
    col_del1, col_del2 = st.columns([2, 1])

    with col_del1:
      trade_options = []
      for idx, row in df_display.iterrows():
        t_id = row.get("id") or idx
        pair_name = row.get("Pair") or "Unknown"
        direction = row.get("Direction") or "N/A"
        date_val = row.get("Date") or "Live"
        trade_options.append(
            f"ID {t_id}: {pair_name} ({direction}) - {date_val}"
        )

      selected_to_delete = st.selectbox(
          "Επίλεξε Trade για διαγραφή:", trade_options
      )

      if st.button("❌ Διαγραφή Επιλεγμένου Trade"):
        raw_id = selected_to_delete.split(":")[0].replace("ID ", "").strip()
        if raw_id.isdigit():
          delete_trade_from_db(int(raw_id))
        st.session_state.saved_trades_list = load_trades_from_db()
        pd.DataFrame(st.session_state.saved_trades_list).to_csv(
            LOG_FILE, index=False
        )
        st.success("Το trade διαγράφηκε!")
        st.rerun()

    with col_del2:
      st.write(" ")
      st.write(" ")
      if st.button("🗑️ Καθαρισμός Όλων", key="clear_log_btn"):
        clear_db()
        st.session_state.saved_trades_list = []
        if os.path.exists(LOG_FILE):
          os.remove(LOG_FILE)
        st.success("Όλα τα trades διαγράφηκαν!")
        st.rerun()
  else:
    st.info("💡 Δεν υπάρχουν ακόμα αποθηκευμένα trades.")

with tab_dex:
  st.subheader("🪐 Solana DEX & On-Chain Scanner (DexScreener)")
  token_contract = st.text_input(
      "Εισάγαγε Contract Address από Solana Token:", value=""
  )

  if st.button("🔍 Scan Token"):
    if token_contract:
      with st.spinner("Παραλαβή On-Chain δεδομένων..."):
        dex_info = fetch_solana_dex_data(token_contract)
        if dex_info:
          st.success(
              f"Βρέθηκε Token: {dex_info['name']} ({dex_info['symbol']})"
          )
          col1, col2, col3, col4 = st.columns(4)
          col1.metric("Τιμή", f"${dex_info['price']:.6f}")
          col2.metric("Liquidity", f"${dex_info['liquidity']:,.2f}")
          col3.metric("24h Volume", f"${dex_info['volume_24h']:,.2f}")
          col4.metric("FDV / Market Cap", f"${dex_info['fdv']:,.2f}")

          st.divider()
          col_b1, col_b2, col_b3 = st.columns(3)
          col_b1.metric("DEX", dex_info["dex"].upper())
          col_b2.metric("1h Buys", dex_info["buys_1h"])
          col_b3.metric("1h Sells", dex_info["sells_1h"])

          st.markdown(
              f"🔗 [Άνοιγμα στο DexScreener]({dex_info['url']})",
              unsafe_allow_html=True,
          )

          if st.button("💾 Αποθήκευση Solana Token στο Log"):
            dex_trade = {
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Pair": f"{dex_info['symbol']}/SOL",
                "Direction": "SOLANA DEX",
                "Entry": dex_info["price"],
                "SL": 0.0,
                "TP1": 0.0,
                "Status": "Watched",
                "Reason": (
                    f"Liquidity: ${dex_info['liquidity']:,.0f} | 1h"
                    f" Buys/Sells: {dex_info['buys_1h']}/{dex_info['sells_1h']}"
                ),
            }
            save_trade_to_db(dex_trade)
            st.session_state.saved_trades_list = load_trades_from_db()
            st.success("Το Solana token αποθηκεύτηκε στη βάση!")
        else:
          st.error(
              "Δεν βρέθηκαν δεδομένα. Βεβαιώσου ότι το Contract Address είναι"
              " σωστό."
          )
    else:
      st.warning("Παρακαλώ συμπλήρωσε ένα σωστό Contract Address.")
