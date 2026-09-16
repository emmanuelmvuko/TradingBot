from mt5linux import MetaTrader5

mt5 = MetaTrader5()
mt5.initialize()

# Request the last tick for GBP/USD
symbol = "GBPUSDm"
tick = mt5.symbol_info_tick(symbol)

if tick:
    print(f"✅ Price Data Received for {symbol}")
    print(f"Bid: {tick.bid}")
    print(f"Ask: {tick.ask}")
    print(f"Last Update: {tick.time} (Server Time)")
else:
    print(f"❌ Could not get price for {symbol}.")
    print("Check if the symbol is visible in your MT5 Market Watch.")

mt5.shutdown()