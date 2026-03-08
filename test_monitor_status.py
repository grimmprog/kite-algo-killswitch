#!/usr/bin/env python3
"""
Test Monitor Status - Check if monitoring is actually running
"""
import sys
import time
from advanced_killswitch import AdvancedKillSwitch

def main():
    print("=" * 60)
    print("MONITOR STATUS TEST")
    print("=" * 60)
    
    ks = AdvancedKillSwitch()
    
    print(f"\nKill Switch Status:")
    print(f"  Active: {ks.is_active}")
    print(f"  Monitoring: {ks.is_monitoring()}")
    print(f"  Monitor Thread: {ks.monitor_thread}")
    print(f"  Thread Alive: {ks.monitor_thread.is_alive() if ks.monitor_thread else 'N/A'}")
    
    print(f"\nThresholds:")
    print(f"  Max Loss: {ks.loss_display}")
    print(f"  Profit Threshold: {ks.profit_display}")
    print(f"  Drawdown: {ks.drawdown_display}")
    
    print(f"\nCurrent P&L:")
    try:
        day_pnl, net_pnl = ks.get_total_pnl()
        print(f"  Day P&L: ₹{day_pnl:,.2f}")
        print(f"  Net P&L: ₹{net_pnl:,.2f}")
        
        loss_percent = (day_pnl / ks.capital) * 100
        print(f"  Loss %: {loss_percent:.2f}%")
        
        print(f"\nCondition Check:")
        should_trigger, reason = ks.check_conditions(day_pnl, net_pnl)
        print(f"  Should Trigger: {should_trigger}")
        print(f"  Reason: {reason}")
        
        if should_trigger:
            print(f"\n🚨 KILL SWITCH SHOULD HAVE TRIGGERED!")
            print(f"   Reason: {reason}")
        
    except Exception as e:
        print(f"  Error getting P&L: {e}")
    
    print("\n" + "=" * 60)
    
    # If monitoring is supposed to be active but thread is dead, restart it
    if ks.is_monitoring() and (not ks.monitor_thread or not ks.monitor_thread.is_alive()):
        print("\n⚠️  WARNING: Monitoring flag is True but thread is not running!")
        print("This explains why kill switch didn't trigger.")
        print("\nAttempting to restart monitoring...")
        
        # Stop and restart
        ks.monitoring = False
        ks.save_monitoring_status(False)
        time.sleep(1)
        
        success, msg = ks.start_monitoring(check_interval=5)
        if success:
            print(f"✅ Monitoring restarted: {msg}")
            print(f"   Thread alive: {ks.monitor_thread.is_alive()}")
        else:
            print(f"❌ Failed to restart: {msg}")

if __name__ == "__main__":
    main()
