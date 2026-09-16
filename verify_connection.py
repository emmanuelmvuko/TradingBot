from mt5linux import MetaTrader5
import time

# Initialize the bridge
mt5 = MetaTrader5(port=18812)

if not mt5.initialize():
    print("❌ Failed to connect to the MT5 Bridge!")
    print("Check if 'wine python -m mt5linux' is running in another terminal.")
    quit()

# Get account information
account_info = mt5.account_info()

if account_info:
    print("✅ BRIDGE SUCCESSFUL")
    print("-" * 30)
    print(f"👤 Login ID:  {account_info.login}")
    print(f"🏢 Server:    {account_info.server}")
    print(f"💰 Balance:   {account_info.balance} {account_info.currency}")
    print(f"⚙️ Leverage:  1:{account_info.leverage}")
    print("-" * 30)
else:
    print("⚠️ Connected to bridge, but could not fetch account info.")
    print("Make sure you are logged into your Demo Account in the MT5 UI.")

mt5.shutdown()