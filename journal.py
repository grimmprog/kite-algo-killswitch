import csv
import os
from datetime import datetime
from notifier import send_alert
FILE = "trade_journal.csv"

HEADERS = [
    "date", "time", "symbol", "direction",
    "entry_price", "sl_price", "exit_price",
    "pnl", "trend_ok", "setup_ok",
    "exit_reason"
]

def log_trade(data: dict):
    file_exists = os.path.isfile(FILE)

    with open(FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)
    send_alert(f"TRADE EXECUTED: {data['symbol']} - {data['pnl']}") 
    
