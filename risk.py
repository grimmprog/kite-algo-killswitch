import os
import datetime as dt

def kill_switch_active():
    return os.path.exists("kill_switch.flag")

def activate_kill_switch():
    with open("kill_switch.flag", "w") as f:
        f.write("1")

def calculate_option_sl(entry_price, index_sl_points=15):
    # Rule: ~1 index point ≈ 2% option premium (ATM)
    sl_percent = index_sl_points * 0.02
    return entry_price * (1 - sl_percent)

def calculate_risk_reward_ratio(entry_price, exit_price):
    risk = entry_price - exit_price
    reward = exit_price - entry_price
    return reward / risk

def calculate_position_size(capital, entry_price, sl_price):
    risk = entry_price - sl_price
    return capital / risk

def calculate_pnl(trade):
    return trade.exit_price - trade.entry_price

def calculate_daily_pnl(trades):
    return sum(trade.pnl for trade in trades)

def calculate_max_drawdown(trades):
    pnl = calculate_daily_pnl(trades)
    return min(pnl) / max(pnl)

def is_expiry_day():
    return dt.datetime.today().weekday() == 3  # Thursday