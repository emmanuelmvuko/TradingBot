from mt5linux import MetaTrader5
mt5 = MetaTrader5()

if mt5.initialize():
    print("✅ SUCCESS: Ubuntu is talking to MT5!")
    account_info = mt5.account_info()
    if account_info:
        print(f"Account Balance: {account_info.balance}")
    mt5.shutdown()
else:
    print("❌ FAILED: Start the bridge server first (wine python -m mt5linux)")

        # wine python -m mt5linux   terminal1
    # python3 ~/TradingBot/bot_engine.py    terminal2