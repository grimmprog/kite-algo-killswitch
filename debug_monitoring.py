#!/usr/bin/env python3
"""Debug monitoring status and check why kill switch didn't trigger"""
import json
from advanced_killswitch import AdvancedKillSwitch

print("=" * 60)
print("MONITORING DEBUG")
print("=" * 60)

# Load kill switch
ks = AdvancedKillSwitch()

print(f"\nKill Switch Status:")
print(f"  Is Active: {ks.is_active}")
print(f"  Is Monitoring: {ks.is_monitoring()}")
print(f"  Capital: ₹{ks.capital:,}")
print(f"  Max Loss Threshold: ₹{ks.max_loss_threshold:,}")
print(f"  Loss Display: {ks.loss_display}")

# Check monitoring status file
try:
    with open('monitoring_status.json', 'r') as f:
        status = json.load(f)
        print(f"\nMonitoring Status File:")
        print(f"  Monitoring: {status.get('monitoring')}")
        print(f"  Timestamp: {status.get('timestamp')}")
except Exception as e:
    print(f"\nError reading monitoring status: {e}")

# Check kill switch status file
try:
    with open('killswitch_status.json', 'r') as f:
        status = json.load(f)
        print(f"\nKill Switch Status File:")
        print(f"  Active: {status.get('active')}")
        print(f"  Reason: {status.get('reason', 'N/A')}")
        print(f"  Timestamp: {status.get('timestamp')}")
except Exception as e:
    print(f"\nError reading kill switch status: {e}")

# Get current P&L
print(f"\nCurrent P&L:")
try:
    day_pnl, net_pnl = ks.get_total_pnl()
    print(f"  Day P&L: ₹{day_pnl:,.2f}")
    print(f"  Net P&L: ₹{net_pnl:,.2f}")
    
    day_pnl_percent = (day_pnl / ks.capital) * 100
    print(f"  Day P&L %: {day_pnl_percent:.2f}%")
    
    # Check if should trigger
    should_trigger, reason = ks.check_conditions(day_pnl, net_pnl)
    print(f"\nShould Trigger: {should_trigger}")
    print(f"Reason: {reason}")
    
    if day_pnl < -ks.max_loss_threshold:
        print(f"\n⚠️  THRESHOLD BREACH DETECTED!")
        print(f"  Day P&L: ₹{day_pnl:,.2f}")
        print(f"  Threshold: ₹-{ks.max_loss_threshold:,.2f}")
        print(f"  Difference: ₹{abs(day_pnl) - ks.max_loss_threshold:,.2f} over threshold")
    
except Exception as e:
    print(f"  Error getting P&L: {e}")
    import traceback
    traceback.print_exc()

# Check open positions
print(f"\nOpen Positions:")
try:
    positions = ks.get_open_positions()
    print(f"  Count: {len(positions)}")
    if positions:
        for pos in positions:
            print(f"    {pos.get('tradingsymbol')}: {pos.get('quantity')} @ ₹{pos.get('pnl', 0):.2f}")
except Exception as e:
    print(f"  Error getting positions: {e}")

print("\n" + "=" * 60)
