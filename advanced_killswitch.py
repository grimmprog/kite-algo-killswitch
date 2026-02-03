"""
Advanced Kill Switch System
- Monitors P&L continuously
- Auto-triggers on conditions
- Closes all positions
- Stops bot from trading
- Deactivates F&O segment automatically
"""
from connect import get_kite_session
from notifier import notifier
import config
import time
import os
import json
import threading
from datetime import datetime

class AdvancedKillSwitch:
    def __init__(self):
        self.kite = get_kite_session()
        self.capital = config.CAPITAL
        self.kill_switch_file = "killswitch_status.json"
        
        # Thresholds
        self.max_loss_threshold = 4000
        self.profit_threshold = 5000
        self.profit_drawdown = 2000
        self.profit_warning_percent = 10
        
        self.highest_pnl = 0
        self.is_active = self.load_status()
        
        # Monitoring control
        self.monitoring = False
        self.monitor_thread = None
        self.last_warning_time = 0  # To prevent spam warnings
        
    def load_status(self):
        """Load kill switch status from file"""
        if os.path.exists(self.kill_switch_file):
            try:
                with open(self.kill_switch_file, 'r') as f:
                    data = json.load(f)
                    return data.get('active', False)
            except:
                return False
        return False
    
    def save_status(self, active, reason=""):
        """Save kill switch status to file"""
        data = {
            'active': active,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }
        with open(self.kill_switch_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_total_pnl(self):
        """Get total P&L"""
        try:
            positions = self.kite.positions()
            day_pnl = sum([pos['pnl'] for pos in positions['day']])
            net_pnl = sum([pos['pnl'] for pos in positions['net']])
            return day_pnl, net_pnl
        except Exception as e:
            print(f"Error fetching P&L: {e}")
            return 0, 0
    
    def get_open_positions(self):
        """Get open positions"""
        try:
            positions = self.kite.positions()['net']
            return [pos for pos in positions if pos['quantity'] != 0]
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []
    
    def close_all_positions(self, reason):
        """Close all open positions"""
        print(f"\n{'=' * 60}")
        print(f"🚨 KILL SWITCH ACTIVATED: {reason}")
        print(f"{'=' * 60}")
        
        positions = self.get_open_positions()
        
        if not positions:
            print("No open positions to close.")
        else:
            print(f"Closing {len(positions)} position(s)...\n")
            
            success_count = 0
            for pos in positions:
                symbol = pos['tradingsymbol']
                quantity = abs(pos['quantity'])
                transaction_type = "SELL" if pos['quantity'] > 0 else "BUY"
                
                print(f"Closing {symbol}: {transaction_type} {quantity}...")
                
                try:
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange=pos['exchange'],
                        tradingsymbol=symbol,
                        transaction_type=transaction_type,
                        quantity=quantity,
                        product=pos['product'],
                        order_type=self.kite.ORDER_TYPE_MARKET
                    )
                    print(f"  ✅ Order placed: {order_id}")
                    success_count += 1
                except Exception as e:
                    print(f"  ❌ Failed: {e}")
            
            print(f"\n{success_count}/{len(positions)} positions closed.")
        
        # Mark kill switch as active
        self.is_active = True
        self.save_status(True, reason)
        
        # Get final P&L
        time.sleep(2)
        day_pnl, _ = self.get_total_pnl()
        
        # Deactivate F&O segment automatically
        print("\n" + "=" * 60)
        print("DEACTIVATING F&O SEGMENT")
        print("=" * 60)
        
        try:
            from segment_automation import ZerodhaSegmentAutomation
            
            print("Starting segment automation...")
            automation = ZerodhaSegmentAutomation(headless=True)
            segment_success = automation.deactivate_fno_segment()
            
            if segment_success:
                print("✅ F&O segment deactivated successfully!")
                segment_status = "✅ F&O segment deactivated"
            else:
                print("❌ Failed to deactivate segment automatically")
                segment_status = "⚠️ Manual segment deactivation required"
        except Exception as e:
            print(f"❌ Segment automation error: {e}")
            segment_status = "⚠️ Manual segment deactivation required"
        
        # Send comprehensive notification
        message = (
            f"🚨 **KILL SWITCH ACTIVATED**\n\n"
            f"**Reason:** {reason}\n"
            f"**Final P&L:** ₹{day_pnl:,.2f}\n"
            f"**Positions Closed:** {success_count}/{len(positions) if positions else 0}\n"
            f"**Time:** {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"**Segment Status:**\n{segment_status}\n\n"
            f"**Actions Taken:**\n"
            f"1. ✅ All positions closed\n"
            f"2. ✅ Bot stopped trading\n"
            f"3. {'✅' if segment_success else '⚠️'} F&O segment {'deactivated' if segment_success else 'needs manual deactivation'}\n\n"
        )
        
        if not segment_success:
            message += (
                f"⚠️ **MANUAL ACTION REQUIRED:**\n"
                f"Deactivate F&O segment at:\n"
                f"https://console.zerodha.com/account/segment-activation\n\n"
            )
        
        message += f"To reactivate: Send /reactivate command"
        
        notifier.send_message(message)
        
        print("\n" + "=" * 60)
        if not segment_success:
            print("⚠️  MANUAL ACTION REQUIRED:")
            print("=" * 60)
            print("1. Deactivate F&O segment at:")
            print("   https://console.zerodha.com/account/segment-activation")
            print("2. This prevents any accidental trades")
        print("3. Review your trades for today")
        print("=" * 60)
        
        return True
    
    def check_conditions(self, day_pnl, net_pnl):
        """Check if kill switch should be triggered"""
        
        # Update highest P&L
        if day_pnl > self.highest_pnl:
            self.highest_pnl = day_pnl
        
        # Rule 1: Loss > ₹4,000
        if day_pnl < -self.max_loss_threshold:
            return True, f"Daily loss exceeded ₹{self.max_loss_threshold:,}"
        
        # Rule 2: Profit > ₹5,000 and dropped by ₹2,000
        if self.highest_pnl >= self.profit_threshold:
            drawdown = self.highest_pnl - day_pnl
            if drawdown >= self.profit_drawdown:
                return True, f"Profit drawdown: Peak ₹{self.highest_pnl:,.2f} → Current ₹{day_pnl:,.2f}"
        
        # Rule 3: Profit > 10% warning (not auto-trigger, just warning)
        profit_percent = (day_pnl / self.capital) * 100
        if profit_percent >= self.profit_warning_percent:
            # Send warning but don't trigger (only once every 5 minutes)
            current_time = time.time()
            if current_time - self.last_warning_time > 300:  # 5 minutes
                message = (
                    f"⚠️ **PROFIT WARNING**\n\n"
                    f"Today's profit: ₹{day_pnl:,.2f} ({profit_percent:.1f}%)\n"
                    f"Peak P&L: ₹{self.highest_pnl:,.2f}\n\n"
                    f"Consider:\n"
                    f"• Booking profits\n"
                    f"• Activating kill switch manually\n"
                    f"• Reducing position sizes\n\n"
                    f"Send /killswitch to check status"
                )
                notifier.send_message(message)
                self.last_warning_time = current_time
        
        return False, "All systems normal"
    
    def start_monitoring(self, check_interval=5):
        """Start monitoring in background thread"""
        if self.monitoring:
            return False, "Monitoring already active"
        
        if self.is_active:
            return False, "Kill switch is already active"
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(check_interval,), daemon=True)
        self.monitor_thread.start()
        
        return True, f"Monitoring started (checking every {check_interval}s)"
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        if not self.monitoring:
            return False, "Monitoring is not active"
        
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        
        return True, "Monitoring stopped"
    
    def is_monitoring(self):
        """Check if monitoring is active"""
        return self.monitoring
    
    def _monitor_loop(self, check_interval):
        """Internal monitoring loop (runs in background thread)"""
        print(f"[Monitor] Started background monitoring (interval: {check_interval}s)")
        
        try:
            while self.monitoring:
                if self.is_active:
                    # Kill switch already active, stop monitoring
                    print("[Monitor] Kill switch is active, stopping monitoring")
                    self.monitoring = False
                    break
                
                try:
                    day_pnl, net_pnl = self.get_total_pnl()
                    
                    # Check conditions
                    should_trigger, reason = self.check_conditions(day_pnl, net_pnl)
                    
                    if should_trigger:
                        print(f"[Monitor] Trigger condition met: {reason}")
                        self.close_all_positions(reason)
                        self.monitoring = False
                        break
                    
                except Exception as e:
                    print(f"[Monitor] Error in monitoring loop: {e}")
                
                time.sleep(check_interval)
                
        except Exception as e:
            print(f"[Monitor] Fatal error in monitoring thread: {e}")
            self.monitoring = False
        
        print("[Monitor] Background monitoring stopped")
    
    def monitor(self, check_interval=5):
        """Monitor P&L and auto-trigger kill switch"""
        print("=" * 60)
        print("ADVANCED KILL SWITCH MONITOR")
        print("=" * 60)
        print(f"Capital: ₹{self.capital:,}")
        print(f"Max Loss: ₹{self.max_loss_threshold:,}")
        print(f"Profit Threshold: ₹{self.profit_threshold:,}")
        print(f"Profit Drawdown: ₹{self.profit_drawdown:,}")
        print(f"Check Interval: {check_interval}s")
        print("=" * 60)
        
        if self.is_active:
            print("\n⚠️  KILL SWITCH IS ALREADY ACTIVE")
            print("Bot will not place new trades.")
            print("Send /reactivate to reset.\n")
        else:
            print("\nMonitoring... (Press Ctrl+C to stop)\n")
        
        try:
            while True:
                if self.is_active:
                    # Just monitor, don't trigger again
                    day_pnl, _ = self.get_total_pnl()
                    print(f"\r🔴 KILL SWITCH ACTIVE | Day P&L: ₹{day_pnl:,.2f} | {datetime.now().strftime('%H:%M:%S')}", end='', flush=True)
                else:
                    day_pnl, net_pnl = self.get_total_pnl()
                    open_positions = len(self.get_open_positions())
                    
                    day_pnl_percent = (day_pnl / self.capital) * 100
                    status = "🟢" if day_pnl >= 0 else "🔴"
                    
                    print(
                        f"\r{status} P&L: ₹{day_pnl:,.2f} ({day_pnl_percent:+.2f}%) | "
                        f"Peak: ₹{self.highest_pnl:,.2f} | "
                        f"Open: {open_positions} | "
                        f"{datetime.now().strftime('%H:%M:%S')}",
                        end='', flush=True
                    )
                    
                    # Check conditions
                    should_trigger, reason = self.check_conditions(day_pnl, net_pnl)
                    
                    if should_trigger:
                        print("\n")  # New line before activation
                        self.close_all_positions(reason)
                        break
                
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\n\n⚠️  Monitor stopped by user.")
            day_pnl, _ = self.get_total_pnl()
            print(f"Final Day P&L: ₹{day_pnl:,.2f}")
            print(f"Peak P&L: ₹{self.highest_pnl:,.2f}")
    
    def deactivate(self):
        """Manually deactivate (reset kill switch)"""
        self.is_active = False
        self.save_status(False, "Manual reactivation")
        print("✅ Kill switch deactivated. Bot can trade again.")
        print("⚠️  Remember to reactivate F&O segment on Zerodha Console")
        
        notifier.send_message(
            "✅ Kill switch deactivated\n\n"
            "Bot can trade again.\n"
            "Make sure F&O segment is activated on Zerodha Console."
        )
    
    def status(self):
        """Check current status"""
        day_pnl, _ = self.get_total_pnl()
        positions = self.get_open_positions()
        
        print("=" * 60)
        print("KILL SWITCH STATUS")
        print("=" * 60)
        print(f"Active: {'🔴 YES' if self.is_active else '🟢 NO'}")
        print(f"Monitoring: {'🟢 YES' if self.monitoring else '🔴 NO'}")
        print(f"Day P&L: ₹{day_pnl:,.2f}")
        print(f"Peak P&L: ₹{self.highest_pnl:,.2f}")
        print(f"Open Positions: {len(positions)}")
        print("=" * 60)
        
        if self.is_active:
            print("\n⚠️  Kill switch is ACTIVE")
            print("Bot will NOT place new trades")
            print("To reactivate trading: Run with option 3")
        
        if self.monitoring:
            print("\n✅ Background monitoring is ACTIVE")
            print("Will auto-trigger on conditions")

def main():
    print("=" * 60)
    print("ADVANCED KILL SWITCH SYSTEM")
    print("=" * 60)
    print("\nOptions:")
    print("1. Start monitoring (auto-trigger)")
    print("2. Check status")
    print("3. Deactivate kill switch (allow trading)")
    print("4. Manually activate kill switch")
    print("=" * 60)
    
    choice = input("\nSelect option (1/2/3/4): ").strip()
    
    ks = AdvancedKillSwitch()
    
    if choice == '1':
        fast = input("Fast mode (2s checks)? (y/n): ").strip().lower()
        interval = 2 if fast == 'y' else 5
        ks.monitor(check_interval=interval)
    
    elif choice == '2':
        ks.status()
    
    elif choice == '3':
        ks.deactivate()
    
    elif choice == '4':
        confirm = input("Manually activate kill switch? (yes/no): ").strip().lower()
        if confirm == 'yes':
            ks.close_all_positions("Manual activation")
    
    else:
        print("Invalid option.")

if __name__ == "__main__":
    main()
