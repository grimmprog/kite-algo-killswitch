"""Quick test: verify Kite connection works and can retrieve trades."""
from connect import get_kite_session

kite = get_kite_session()
profile = kite.profile()
print(f"Profile: {profile['user_name']} ({profile['user_id']})")
print(f"Email: {profile['email']}")

trades = kite.trades()
print(f"Trades today: {len(trades)}")

positions = kite.positions()
net = positions.get("net", [])
day = positions.get("day", [])
print(f"Positions - Net: {len(net)}, Day: {len(day)}")

if trades:
    print("\nRecent trades:")
    for t in trades[:3]:
        print(f"  {t['tradingsymbol']} {t['transaction_type']} qty={t['quantity']} @ {t['average_price']}")
