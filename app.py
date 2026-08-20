# --- ΣΥΝΑΡΤΗΣΗ LIVE CHECK ΑΓΟΡΑΣ (Live Ticker & Ιστορικά 1m/5m OHLCV) ---
def check_trade_status(row):
    status = str(row["Status"])
    if "Win" in status or "Loss" in status or "Canceled" in status:
        return status

    pair = str(row["Pair"]).upper().strip()
    direction = str(row["Direction"]).upper().strip()
    
    try:
        entry = float(row["Entry"])
        sl = float(row["SL"])
        tp1 = float(row["TP1"])
    except (ValueError, TypeError):
        return status

    try:
        trade_date = datetime.strptime(str(row["Date"]), "%Y-%m-%d %H:%M")
        since_timestamp = int(trade_date.timestamp() * 1000)
    except Exception:
        since_timestamp = None

    for exchange_class in [ccxt.bybit, ccxt.binance]:
        try:
            exchange = exchange_class()
            # Δοκιμή όλων των πιθανών μορφών του σύμβολου
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
                    # 1. Έλεγχος Live Τιμής (Ticker)
                    ticker = exchange.fetch_ticker(symbol)
                    last_price = float(ticker['last'])
                    high_24h = float(ticker['high'])
                    low_24h = float(ticker['low'])

                    if direction == "LONG":
                        if last_price >= tp1 or high_24h >= tp1:
                            return "Win 🏆"
                        elif last_price <= sl:
                            return "Loss ❌"
                    elif direction == "SHORT":
                        if last_price <= tp1 or low_24h <= tp1:
                            return "Win 🏆"
                        elif last_price >= sl:
                            return "Loss ❌"

                    # 2. Έλεγχος Ιστορικών Κεριών (1-minute timeframe για ακρίβεια στις φυτίλες)
                    if since_timestamp:
                        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1m', since=since_timestamp, limit=1000)
                        for candle in ohlcv:
                            c_high, c_low = candle[2], candle[3]
                            if direction == "LONG":
                                if c_low <= sl:
                                    return "Loss ❌"
                                elif c_high >= tp1:
                                    return "Win 🏆"
                            elif direction == "SHORT":
                                if c_high >= sl:
                                    return "Loss ❌"
                                elif c_low <= tp1:
                                    return "Win 🏆"
                    break
                except Exception:
                    continue
        except Exception:
            continue

    return "Pending ⏳"
