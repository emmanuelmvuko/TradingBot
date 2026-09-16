import pandas as pd
import MetaTrader5 as mt5
import requests
import time
from datetime import datetime, UTC, timedelta
import threading

# ---------------- CONFIG ---------------- #
SYMBOL = None
YF_SYMBOL = "GBPUSD=X"

LOT_SIZE = 0.01
RISK_REWARD = 2
ATR_MULTIPLIER = 2
MAX_DAILY_TRADES = 3
MAX_SPREAD = 0.0004  # 4 pips
MIN_SLOPE = 0.000015   # adjust this (IMPORTANT)

HTF = "1h"
ITF = "15m"
LTF = "5m"

TELEGRAM_TOKEN = "8686764910:AAHLnq0PXX1Na_wDvu4wVoc3vWpr2MqAW98"
CHAT_ID = "1117377957"

# ---------------------------------------- #
daily_trades = 0
last_trading_day = None
last_heartbeat_day = None

# -------- PERFORMANCE TRACKING -------- #
stats = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "profit": 0.0
}

last_report_day = None

# ---------------- TELEGRAM ---------------- #
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": msg
        })

        if response.status_code != 200:
            print("Telegram failed:", response.text)

    except Exception as e:
        print("❌ Telegram error:", e)

def detect_symbol():
    global SYMBOL

    symbols = mt5.symbols_get()

    for s in symbols:
        if "GBPUSD" in s.name:
            SYMBOL = s.name
            print(f"✅ Using symbol: {SYMBOL}")
            return True

    print("❌ GBPUSD symbol not found")
    return False

def calculate_lot_size(sl_price, entry_price):
    account = mt5.account_info()
    balance = account.balance

    risk_percent = 0.01  # 1% risk per trade
    risk_amount = balance * risk_percent

    pip_value = 10  # approximate for GBPUSD
    sl_pips = abs(entry_price - sl_price) * 10000

    lot = risk_amount / (sl_pips * pip_value)

    return 0.01 #round(max(lot, 0.01), 2)


# ---------------- MT5 CONNECT ---------------- #

def connect_mt5():
    print("\n===== MT5 BRIDGE TEST =====")

    if not mt5.initialize():
        print("❌ MT5 initialization failed")
        send_telegram("❌ MT5 Bridge initialization failed")
        return False

    print("✅ MT5 initialized")

    # ACCOUNT INFO
    account = mt5.account_info()

    if account is None:
        print("❌ Cannot read account info")
        send_telegram("❌ Cannot read MT5 account info")
        return False

    print(f"Account ID: {account.login}")
    print(f"Balance: {account.balance}")
    print(f"Leverage: 1:{account.leverage}")

    send_telegram(
        f"✅ MT5 Connected\n"
        f"Account: {account.login}\n"
        f"Balance: {account.balance}\n"
        f"Leverage: 1:{account.leverage}"
    )

    if not detect_symbol():
        return False

    # SYMBOL CHECK
    tick = mt5.symbol_info_tick(SYMBOL)

    if tick is None:
        print(f"❌ Cannot get price for {SYMBOL}")
        send_telegram(f"❌ Cannot get price for {SYMBOL}")
        return False

    print(f"Price received for {SYMBOL}: {tick.bid}")

    # TEST TRADE
    print("Testing trade execution...")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": 0.01,
        "type": mt5.ORDER_TYPE_BUY,
        "price": tick.ask,
        "deviation": 20,
        "magic": 999,
        "comment": "Bridge Test",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("❌ Test trade failed")
        send_telegram("❌ MT5 test trade failed")
        return False

    ticket = result.order

    print(f"✅ Test trade opened: {ticket}")

    time.sleep(3)

    positions = mt5.positions_get(ticket=ticket)

    if positions:
        position = positions[0]

        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL,
            "position": position.ticket,
            "price": mt5.symbol_info_tick(SYMBOL).bid,
            "deviation": 20,
            "magic": 999,
            "comment": "Bridge Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        }

        close_result = mt5.order_send(close_request)

        if close_result.retcode == mt5.TRADE_RETCODE_DONE:
            print("✅ Test trade closed successfully")
            send_telegram("✅ MT5 Bridge Test Successful")

        else:
            print("❌ Failed to close test trade")
            send_telegram("⚠️ Test trade could not close")

    print("===== SYSTEM READY =====\n")

    return True

# ---------------- DATA ---------------- #
def get_data(interval_str, num_candles=100):

    tf_map = {
        "1h": mt5.TIMEFRAME_H1,
        "15m": mt5.TIMEFRAME_M15,
        "5m": mt5.TIMEFRAME_M5
    }

    timeframe = tf_map.get(interval_str)

    mt5.symbol_select(SYMBOL, True)

    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, num_candles)

    if rates is None or len(rates) == 0:
        print(f"⚠️ MT5 Data failed for {interval_str}")
        return None

    df = pd.DataFrame(rates)

    df.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close'
    }, inplace=True)

    return df

# ---------------- INDICATORS ---------------- #
def add_indicators(df):
    try:
        # ATR calculation manually
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        df["tr"] = (high - low).combine(
            abs(high - close.shift()), max
        ).combine(
            abs(low - close.shift()), max
        )

        df["atr"] = df["tr"].rolling(14).mean()

        return df

    except Exception as e:
        print("Indicator error:", e)
        return df

# ---------------- TRENDLINES ---------------- #
def find_peaks_simple(data, distance=5, mode="max"):
    peaks = []
    for i in range(distance, len(data) - distance):
        window = data[i - distance:i + distance + 1]

        if mode == "max" and data[i] == max(window):
            peaks.append(i)
        elif mode == "min" and data[i] == min(window):
            peaks.append(i)

    return peaks


def get_trendlines(df):
    highs = df["High"].tolist()
    lows = df["Low"].tolist()

    peaks = find_peaks_simple(highs, mode="max")
    valleys = find_peaks_simple(lows, mode="min")

    if len(peaks) < 2 or len(valleys) < 2:
        return None, None, None

    # RESISTANCE
    x1_res, x2_res = peaks[-2], peaks[-1]
    y1_res, y2_res = highs[x1_res], highs[x2_res]
    slope_res = (y2_res - y1_res) / (x2_res - x1_res) if x2_res != x1_res else 0

    # SUPPORT
    x1_sup, x2_sup = valleys[-2], valleys[-1]
    y1_sup, y2_sup = lows[x1_sup], lows[x2_sup]
    slope_sup = (y2_sup - y1_sup) / (x2_sup - x1_sup) if x2_sup != x1_sup else 0

    # Project lines
    support = y2_sup + slope_sup * (len(df)-1 - x2_sup)
    resistance = y2_res + slope_res * (len(df)-1 - x2_res)

    print("Slope sup:", slope_sup, "| Slope res:", slope_res)

    # Average slope (clean trend detection)
    if slope_sup < -MIN_SLOPE and slope_res < -MIN_SLOPE:
        return resistance, support, "SELL"

    elif slope_sup > MIN_SLOPE and slope_res > MIN_SLOPE:
        return resistance, support, "BUY"

    return resistance, support, None



# ---------------- SL/TP ---------------- #
def calculate_sl_tp(price, atr, side):
    risk = atr * ATR_MULTIPLIER
    if side == "BUY":
        sl = price - risk
        tp = price + (risk * RISK_REWARD)
    else:
        sl = price + risk
        tp = price - (risk * RISK_REWARD)
    return sl, tp

# ---------------- NEWS FILTER ---------------- #
def high_impact_news():
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        data = requests.get(url).json()
        now = datetime.now(UTC)
        for event in data:
            if event["impact"] == "High":
                event_time = datetime.strptime(event["date"] + " " + event["time"], "%Y-%m-%d %H:%M:%S")
                diff = (event_time - now).total_seconds() / 3600
                if -1 < diff < 1:
                    return True
    except:
        pass
    return False

# ---------------- SPREAD CHECK ---------------- #
def spread_ok():
    tick = mt5.symbol_info_tick(SYMBOL)

    if tick is None:
        return False

    spread = tick.ask - tick.bid

    if spread > MAX_SPREAD:
        print(f"Spread too high: {spread}")
        return False

    return True




def market_safe():
    now = datetime.now(UTC).hour

    if now == 21 or now == 22:
        return False

    return True

# ---------------- STRATEGY ---------------- #

def breakout_retest_confirmation(price, resistance, support, df):
    last_close = df["Close"].iloc[-1]
    prev_close = df["Close"].iloc[-2]

    tolerance = 0.0002  # adjust per pair

    # 🔴 SELL (support break)
    if support:
        if prev_close > support and last_close < support:
            # breakout happened

            # wait for retest
            if abs(price - support) < tolerance:
                if candle_confirmation(df, "SELL"):
                    return "SELL"

    # 🟢 BUY (resistance break)
    if resistance:
        if prev_close < resistance and last_close > resistance:
            # breakout happened

            # wait for retest
            if abs(price - resistance) < tolerance:
                if candle_confirmation(df, "BUY"):
                    return "BUY"

    return None

def bounce_confirmation(price, resistance, support, df):
    tolerance = 0.0002

    # 🟢 BUY from support
    if support and abs(price - support) < tolerance:
        if candle_confirmation(df, "BUY"):
            return "BUY"

    # 🔴 SELL from resistance
    if resistance and abs(price - resistance) < tolerance:
        if candle_confirmation(df, "SELL"):
            return "SELL"

    return None


        #Support & Resistance Zones
def key_levels(df):
    highs = df["High"]
    lows = df["Low"]

    resistance = highs.rolling(20).max().iloc[-1]
    support = lows.rolling(20).min().iloc[-1]

    return resistance, support

def candle_confirmation(df, direction):
    last = df.iloc[-1]

    # simpler confirmation
    if direction == "BUY":
        return last["Close"] > last["Open"]

    if direction == "SELL":
        return last["Close"] < last["Open"]

    return False



# ---------------- TRADE EXECUTION ---------------- #
def execute_trade(side, sl, tp):
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask if side == "BUY" else tick.bid
    lot = 0.01
    if tick.ask - tick.bid > MAX_SPREAD:
        print("Spread too high, skipping trade")
        return False
    order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "magic": 777,
        "comment": "Trendline Bot Multi-TF"
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        send_telegram(f"🚀 TRADE OPENED\nPair: {SYMBOL}\nSide: {side}\nSL: {sl}\nTP: {tp}")
        return True
    else:
        send_telegram(f"❌ Trade failed: {result.comment}")
        return False

def has_open_trade():
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        return True
    return False


last_checked_deal = None

def monitor_closed_trades():
    global last_checked_deal, stats

    from_date = datetime.now(UTC) - timedelta(days=1)
    to_date = datetime.now(UTC)

    deals = mt5.history_deals_get(from_date, to_date)

    if deals is None or len(deals) == 0:
        return

    # Sort deals (important)
    deals = sorted(deals, key=lambda x: x.ticket)

    # FIRST RUN → just initialize (DON'T SEND)
    if last_checked_deal is None:
        last_checked_deal = deals[-1].ticket
        return

    for deal in deals:

        if deal.ticket <= last_checked_deal:
            continue

        if deal.magic != 777:
            continue

        if deal.entry != mt5.DEAL_ENTRY_OUT:
            continue

        profit = deal.profit
        symbol = deal.symbol

        # Update stats
        stats["trades"] += 1
        stats["profit"] += profit

        if profit > 0:
            stats["wins"] += 1
            result = "✅ TP HIT"
        else:
            stats["losses"] += 1
            result = "❌ SL HIT"

        win_rate = (stats["wins"] / stats["trades"]) * 100 if stats["trades"] > 0 else 0

        send_telegram(
            f"📊 TRADE CLOSED\n"
            f"Pair: {symbol}\n"
            f"{result}\n"
            f"Profit: {round(profit,2)}\n"
            f"Win Rate: {round(win_rate,1)}%"
        )

        # Update LAST processed deal
        last_checked_deal = deal.ticket

def send_daily_report():
    global stats

    if stats["trades"] == 0:
        send_telegram("📊 DAILY REPORT\nNo trades taken today.")
        return

    win_rate = (stats["wins"] / stats["trades"]) * 100

    send_telegram(
        f"📊 DAILY REPORT\n"
        f"Trades: {stats['trades']}\n"
        f"Wins: {stats['wins']}\n"
        f"Losses: {stats['losses']}\n"
        f"Win Rate: {round(win_rate,1)}%\n"
        f"Total Profit: {round(stats['profit'],2)}"
    )

    # Reset stats after report
    stats = {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "profit": 0.0
    }

# ---------------- HEARTBEAT ---------------- #
def heartbeat_scheduler():
    global last_heartbeat_day, last_report_day

    while True:
        now = datetime.now(UTC) + timedelta(hours=3)  # Kenya time
        current_day = now.date()

        # 💓 Heartbeat
        if now.hour == 8 and last_heartbeat_day != current_day:
            send_telegram(" 8:00 AM:Woza wozaaa....Good morning. Bado niko rada")
            last_heartbeat_day = current_day

        # 📊 DAILY REPORT (9 PM Kenya time)
        if now.hour == 21 and last_report_day != current_day:
            send_daily_report()
            last_report_day = current_day

        time.sleep(60)

def market_structure_ok(df):
    highs = df["High"].tolist()
    lows = df["Low"].tolist()

    # simple structure check
    #return highs[-1] > highs[-5] or lows[-1] < lows[-5]
    return True

# ---------------- MULTI-TF CONFIRMATION ---------------- #
def multi_tf_signal():
    try:
       df_htf = get_data(HTF)
       df_itf = get_data(ITF)
       df_ltf = get_data(LTF)

       if df_htf is None or df_itf is None or df_ltf is None:
           return None

       df_htf = add_indicators(df_htf)
       df_itf = add_indicators(df_itf)
       df_ltf = add_indicators(df_ltf)
    except Exception as e:
        print("Data error:", e)
        return None

    if not market_structure_ok(df_htf) or not market_structure_ok(df_ltf):
        return None

    # Trendlines
    res_htf, sup_htf, trend_htf = get_trendlines(df_htf)
    res_itf, sup_itf, trend_itf = get_trendlines(df_itf)
    res_ltf, sup_ltf, trend_ltf = get_trendlines(df_ltf)

    price_htf = df_htf["Close"].iloc[-1]
    prev_htf = df_htf["Close"].iloc[-2]
    price_itf = df_itf["Close"].iloc[-1]
    prev_itf = df_itf["Close"].iloc[-2]
    price_ltf = df_ltf["Close"].iloc[-1]
    prev_ltf = df_ltf["Close"].iloc[-2]
    
    # Reject if no clear structure
   # if res_ltf is None and sup_ltf is None:
    #    return None

        # Determine trend direction (HTF)
    trend_direction = trend_htf

    key_res, key_sup = key_levels(df_ltf)

    zone_range = key_res - key_sup
    mid_zone_low = key_sup + (zone_range * 0.2)
    mid_zone_high = key_sup + (zone_range * 0.8)

   # if mid_zone_low < price_ltf < mid_zone_high:
    #    return None


    # BREAKOUT signals
    signal_htf = (
        breakout_retest_confirmation(price_htf, res_htf, sup_htf, df_htf)
        or bounce_confirmation(price_htf, res_htf, sup_htf, df_htf)
    )

    signal_itf = (
        breakout_retest_confirmation(price_itf, res_itf, sup_itf, df_itf)
        or bounce_confirmation(price_itf, res_itf, sup_itf, df_itf)
    )

    trend_direction = trend_htf

    if trend_direction is None:
        return None

    # LTF candle signal
    last_candle = df_ltf.iloc[-1]

    if trend_direction == "BUY" and last_candle["Close"] > last_candle["Open"]:
        signal_ltf = "BUY"

    elif trend_direction == "SELL" and last_candle["Close"] < last_candle["Open"]:
        signal_ltf = "SELL"

    else:
        signal_ltf = None

    print("Trend:", trend_direction,
      "| LTF:", signal_ltf,
      "| ITF:", signal_itf,
      "| HTF:", signal_htf)

    save_trendlines_for_mt5(res_ltf, sup_ltf)

    

    if signal_ltf == trend_direction:

    # extra safety: avoid weak setups
        if signal_itf != trend_direction and signal_htf != trend_direction:
            return None
        atr = df_ltf["atr"].iloc[-1]
        price = price_ltf

        if atr < 0.00010:
            return None

        return signal_ltf, price, atr

    

    return None

 
last_trendlines = (None, None)  # put this at top of file

def save_trendlines_for_mt5(resistance, support):
    global last_trendlines

    try:
        # 🚫 Skip if nothing changed
        if (resistance, support) == last_trendlines:
            return

        path = "C:/Users/Henzo/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Files/trendlines.txt"

        with open(path, "w") as f:
            f.write(f"{resistance},{support}")

        last_trendlines = (resistance, support)


    except Exception as e:
        print("❌ Error saving trendlines:", e)

# ---------------- MAIN LOOP ---------------- #
def run_bot():
    global daily_trades, last_trading_day
    connect_mt5()
    send_telegram("🤖 GBPUSD Trendline Bot Started. Lets win")

    while True:
        try:
            monitor_closed_trades()

            # Reset daily trades at UTC midnight
            current_day = datetime.now(UTC).date()
            if current_day != last_trading_day:
                daily_trades = 0
                last_trading_day = current_day

            if daily_trades >= MAX_DAILY_TRADES:
                time.sleep(60)
                continue

            if not market_safe():
                time.sleep(300)
                continue

            if has_open_trade():
                time.sleep(60)
                continue

            if high_impact_news():
                print("High-impact news, skipping trade")
                time.sleep(300)
                continue

            if not spread_ok():
                time.sleep(60)
                continue

            result = multi_tf_signal()

            if result:
                side, price, atr = result
                sl, tp = calculate_sl_tp(price, atr, side)

                if execute_trade(side, sl, tp):
                    daily_trades += 1
                    time.sleep(600)  # cooldown after trade
                    continue  # ⛔ IMPORTANT

            # ✅ BASE LOOP DELAY (ADD THIS)
            time.sleep(15)

        except Exception as e:
            print(e)
            time.sleep(60)
# ---------------- RUN ---------------- #
if __name__ == "__main__":
    threading.Thread(target=heartbeat_scheduler, daemon=True).start()
    run_bot()