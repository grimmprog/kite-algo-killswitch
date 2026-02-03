from kiteconnect import KiteConnect
from config import *

kite = KiteConnect(api_key=API_KEY)
with open("access_token.txt") as f:
    ACCESS_TOKEN = f.read().strip()

kite.set_access_token(ACCESS_TOKEN)

def get_ltp(symbol):
    return kite.ltp(symbol)[symbol]["last_price"]

def place_order(symbol, txn_type):
    if MODE == "PAPER":
        print(f"[PAPER] {txn_type} {symbol}")
        return "PAPER_ORDER"

    return kite.place_order(
        variety=kite.VARIETY_REGULAR,
        exchange="NFO",
        tradingsymbol=symbol,
        transaction_type=txn_type,
        quantity=QTY,
        product=kite.PRODUCT_MIS,
        order_type=kite.ORDER_TYPE_MARKET
    )
