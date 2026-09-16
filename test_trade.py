from mt5linux import MetaTrader5
import time

mt5 = MetaTrader5()
mt5.initialize()

symbol = "GBPUSDm"
lot = 0.01
deviation = 20

# 1. Prepare the Buy Request
request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": lot,
    "type": mt5.ORDER_TYPE_BUY,
    "price": mt5.symbol_info_tick(symbol).ask,
    "magic": 123456,
    "comment": "Linux Bridge Test",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}

# 2. Send the Trade
print(f"🚀 Sending test Buy order for {symbol}...")
result = mt5.order_send(request)

# 3. Check Result
if result.retcode != mt5.TRADE_RETCODE_DONE:
    print(f"❌ Trade Failed! Error code: {result.retcode}")
    print(f"Hint: Check if 'Algo Trading' is GREEN in the MT5 window.")
else:
    print(f"✅ TRADE PLACED SUCCESSFULLY! Ticket: {result.order}")
    print("Wait 5 seconds... closing it now to keep your balance safe.")
    
    time.sleep(5)
    
    # 4. Close the position immediately
    close_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_SELL,
        "position": result.order,
        "price": mt5.symbol_info_tick(symbol).bid,
        "magic": 123456,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    mt5.order_send(close_request)
    print("✅ Trade closed. Test complete.")

mt5.shutdown()