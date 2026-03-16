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
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AdvancedKillSwitch:
    def __init__(self):
        # Log instance creation with unique ID for debugging
        logger.info(f"Creating AdvancedKillSwitch instance: {id(self)}")
        
        self.kite = get_kite_session()
        self.capital = config.CAPITAL
        self.kill_switch_file = "killswitch_status.json"
        
        # Thresholds - Use percentage if set, otherwise use fixed amount
        # Loss threshold
        if config.LOSS_THRESHOLD_PERCENT > 0:
            self.max_loss_threshold = (config.LOSS_THRESHOLD_PERCENT / 100) * self.capital
            self.loss_display = f"{config.LOSS_THRESHOLD_PERCENT}% (₹{self.max_loss_threshold:,.0f})"
        else:
            self.max_loss_threshold = config.LOSS_THRESHOLD
            self.loss_display = f"₹{self.max_loss_threshold:,.0f}"
        
        # Profit threshold
        if config.PROFIT_THRESHOLD_PERCENT > 0:
            self.profit_threshold = (config.PROFIT_THRESHOLD_PERCENT / 100) * self.capital
            self.profit_display = f"{config.PROFIT_THRESHOLD_PERCENT}% (₹{self.profit_threshold:,.0f})"
        else:
            self.profit_threshold = config.PROFIT_THRESHOLD
            self.profit_display = f"₹{self.profit_threshold:,.0f}"
        
        # Drawdown threshold (percentage of peak profit)
        if config.DRAWDOWN_THRESHOLD_PERCENT > 0:
            self.drawdown_percent = config.DRAWDOWN_THRESHOLD_PERCENT
            self.drawdown_display = f"{config.DRAWDOWN_THRESHOLD_PERCENT}% of peak"
        else:
            self.profit_drawdown = config.DRAWDOWN_THRESHOLD
            self.drawdown_percent = 0
            self.drawdown_display = f"₹{self.profit_drawdown:,.0f}"
        
        self.profit_warning_percent = 10
        
        self.highest_pnl = 0
        self.is_active = self.load_status()
        
        # Monitoring control
        self.monitoring_status_file = "monitoring_status.json"
        self.monitoring = False  # Always start as False
        self.monitor_thread = None
        self.last_warning_time = 0  # To prevent spam warnings
        self._stop_event = threading.Event()  # Used to wake thread immediately on stop
        
        # Auto-restart monitoring if it was active before restart
        should_monitor = self.load_monitoring_status()
        if should_monitor and not self.is_active:
            # Monitoring was active before restart, restart it now
            print("[Init] Auto-restarting monitoring from previous session...")
            self.start_monitoring(check_interval=5)
        
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

    def load_monitoring_status(self):
        """Load monitoring status from file"""
        if os.path.exists(self.monitoring_status_file):
            try:
                with open(self.monitoring_status_file, 'r') as f:
                    data = json.load(f)
                    return data.get('monitoring', False)
            except:
                return False
        return False

    def save_monitoring_status(self, monitoring):
        """Save monitoring status to file"""
        data = {
            'monitoring': monitoring,
            'timestamp': datetime.now().isoformat()
        }
        with open(self.monitoring_status_file, 'w') as f:
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
        """Get open positions with exchange information"""
        try:
            positions = self.kite.positions()['net']
            return [pos for pos in positions if pos['quantity'] != 0]
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []
    
    def analyze_positions_by_exchange(self, positions):
        """Analyze positions and determine which exchanges/segments to disable"""
        exchange_info = {
            'NFO': {'has_positions': False, 'pnl': 0, 'count': 0, 'segment': 'nfo'},
            'BFO': {'has_positions': False, 'pnl': 0, 'count': 0, 'segment': 'bfo'},
            'NSE': {'has_positions': False, 'pnl': 0, 'count': 0, 'segment': 'equity'},
            'BSE': {'has_positions': False, 'pnl': 0, 'count': 0, 'segment': 'bse_equity'}
        }
        
        for pos in positions:
            exchange = pos.get('exchange', '')
            pnl = pos.get('pnl', 0)
            
            if exchange in exchange_info:
                exchange_info[exchange]['has_positions'] = True
                exchange_info[exchange]['pnl'] += pnl
                exchange_info[exchange]['count'] += 1
        
        # Determine which segments to disable (only those with positions)
        segments_to_disable = []
        exchange_summary = []
        
        for exchange, info in exchange_info.items():
            if info['has_positions']:
                segments_to_disable.append(info['segment'])
                exchange_summary.append(
                    f"{exchange}: {info['count']} position(s), P&L: ₹{info['pnl']:,.2f}"
                )
        
        return segments_to_disable, exchange_summary
    
    def deactivate_segments(self, segments_to_disable):
        """Deactivate specific segments based on positions"""
        if not segments_to_disable:
            print("No segments to deactivate (no positions found)")
            return True, "No segments needed deactivation"
        
        print(f"\nSegments to deactivate: {', '.join(segments_to_disable)}")
        
        try:
            from segment_automation import ZerodhaSegmentAutomation
            
            automation = ZerodhaSegmentAutomation(headless=True)
            
            # Login
            if not automation.login_to_zerodha_selenium():
                return False, "Login failed"
            
            # Navigate to segment page
            automation.driver.get("https://console.zerodha.com/account/segment-activation")
            time.sleep(3)
            
            if "login" in automation.driver.current_url.lower():
                automation.close()
                return False, "Failed to navigate to segment page"
            
            # Deactivate each segment
            success_count = 0
            failed_segments = []
            
            for segment in segments_to_disable:
                print(f"Deactivating {segment}...")
                try:
                    success = automation.toggle_segment(segment, activate=False)
                    if success:
                        success_count += 1
                        print(f"  ✅ {segment} deactivated")
                    else:
                        failed_segments.append(segment)
                        print(f"  ❌ {segment} failed")
                except Exception as e:
                    failed_segments.append(segment)
                    print(f"  ❌ {segment} error: {e}")
            
            # Click Continue to save
            if not automation.click_continue_button():
                print("⚠️ Could not click Continue button")
            
            automation.close()
            
            if success_count == len(segments_to_disable):
                return True, f"All {success_count} segment(s) deactivated"
            elif success_count > 0:
                return False, f"Partial: {success_count}/{len(segments_to_disable)} deactivated. Failed: {', '.join(failed_segments)}"
            else:
                return False, f"Failed to deactivate: {', '.join(failed_segments)}"
                
        except Exception as e:
            return False, f"Segment automation error: {e}"
    
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
            
            # Analyze positions by exchange
            segments_to_disable, exchange_summary = self.analyze_positions_by_exchange(positions)
            
            print("Position Analysis:")
            for summary in exchange_summary:
                print(f"  • {summary}")
            print()
            
            success_count = 0
            for pos in positions:
                symbol = pos['tradingsymbol']
                quantity = abs(pos['quantity'])
                transaction_type = "SELL" if pos['quantity'] > 0 else "BUY"
                exchange = pos['exchange']
                
                print(f"Closing {symbol} ({exchange}): {transaction_type} {quantity}...")
                
                try:
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange=exchange,
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
        
        # Deactivate relevant segments automatically
        print("\n" + "=" * 60)
        print("DEACTIVATING SEGMENTS")
        print("=" * 60)
        
        if positions:
            segments_to_disable, exchange_summary = self.analyze_positions_by_exchange(positions)
            
            if segments_to_disable:
                print(f"Detected positions on: {', '.join(segments_to_disable)}")
                print("Deactivating only relevant segments...\n")
                
                segment_success, segment_message = self.deactivate_segments(segments_to_disable)
                
                if segment_success:
                    print(f"✅ {segment_message}")
                    segment_status = f"✅ Segments deactivated: {', '.join(segments_to_disable)}"
                else:
                    print(f"⚠️ {segment_message}")
                    segment_status = f"⚠️ {segment_message}"
            else:
                print("No segments to deactivate (no positions found)")
                segment_success = True
                segment_status = "ℹ️ No segments needed deactivation"
        else:
            print("No positions found, skipping segment deactivation")
            segment_success = True
            segment_status = "ℹ️ No positions to analyze"
        
        # Send comprehensive notification
        message = (
            f"🚨 **KILL SWITCH ACTIVATED**\n\n"
            f"**Reason:** {reason}\n"
            f"**Final P&L:** ₹{day_pnl:,.2f}\n"
            f"**Positions Closed:** {success_count}/{len(positions) if positions else 0}\n"
            f"**Time:** {datetime.now().strftime('%H:%M:%S')}\n\n"
        )
        
        if positions and exchange_summary:
            message += "**Position Breakdown:**\n"
            for summary in exchange_summary:
                message += f"• {summary}\n"
            message += "\n"
        
        message += f"**Segment Status:**\n{segment_status}\n\n"
        message += (
            f"**Actions Taken:**\n"
            f"1. ✅ All positions closed\n"
            f"2. ✅ Bot stopped trading\n"
            f"3. {'✅' if segment_success else '⚠️'} Segments {'deactivated' if segment_success else 'need manual action'}\n\n"
        )
        
        if not segment_success:
            message += (
                f"⚠️ **MANUAL ACTION REQUIRED:**\n"
                f"Deactivate segments manually at:\n"
                f"https://console.zerodha.com/account/segment-activation\n\n"
            )
        
        message += f"To reactivate: Send /reactivate command"
        
        notifier.send_message(message)
        
        print("\n" + "=" * 60)
        if not segment_success:
            print("⚠️  MANUAL ACTION REQUIRED:")
            print("=" * 60)
            print("1. Deactivate segments manually at:")
            print("   https://console.zerodha.com/account/segment-activation")
            print("2. This prevents any accidental trades")
        print("3. Review your trades for today")
        print("=" * 60)
        
        return True
    
    def check_conditions(self, day_pnl, net_pnl):
        """Check if kill switch should be triggered"""
        
        # Check if monitoring is still active - exit early if not
        if not self.monitoring:
            return False, "Monitoring not active"
        
        # Update highest P&L
        if day_pnl > self.highest_pnl:
            self.highest_pnl = day_pnl
        
        # Rule 1: Loss exceeds threshold
        if day_pnl < -self.max_loss_threshold:
            return True, f"Daily loss exceeded {self.loss_display}"
        
        # Rule 2: Profit drawdown from peak
        if self.highest_pnl >= self.profit_threshold:
            # Calculate drawdown
            if self.drawdown_percent > 0:
                # Percentage-based drawdown
                max_allowed_drawdown = (self.drawdown_percent / 100) * self.highest_pnl
                actual_drawdown = self.highest_pnl - day_pnl
                
                if actual_drawdown >= max_allowed_drawdown:
                    return True, f"Profit drawdown: Peak ₹{self.highest_pnl:,.2f} → Current ₹{day_pnl:,.2f} (dropped {self.drawdown_percent}%)"
            else:
                # Fixed amount drawdown
                drawdown = self.highest_pnl - day_pnl
                if drawdown >= self.profit_drawdown:
                    return True, f"Profit drawdown: Peak ₹{self.highest_pnl:,.2f} → Current ₹{day_pnl:,.2f} (dropped ₹{drawdown:,.2f})"
        
        # Rule 3: Profit > 10% warning (not auto-trigger, just warning)
        # Only send warnings if monitoring is active AND market is open
        if self.monitoring and self.is_market_open():
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
    
    def is_market_open(self):
        """Check if current time is within market hours (9:15 AM to 3:30 PM)"""
        now = datetime.now()
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close
    
    def start_monitoring(self, check_interval=5):
        """Start monitoring in background thread"""
        logger.info(f"start_monitoring called on instance {id(self)}")
        
        if self.monitoring:
            logger.warning(f"Monitoring already active on instance {id(self)}")
            return False, "Monitoring already active"
        
        if self.is_active:
            logger.warning(f"Cannot start monitoring - kill switch is active on instance {id(self)}")
            return False, "Kill switch is already active"
        
        logger.info(f"Starting monitoring thread on instance {id(self)} with {check_interval}s interval")
        self.monitoring = True
        self.save_monitoring_status(True)
        self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(check_interval,), daemon=False)
        self.monitor_thread.start()
        logger.info(f"Monitoring thread started successfully on instance {id(self)}")
        
        return True, f"Monitoring started (checking every {check_interval}s)"
    
    def stop_monitoring(self):
        """Stop background monitoring immediately"""
        logger.info(f"stop_monitoring called on instance {id(self)}")
        
        if not self.monitoring:
            logger.warning(f"Monitoring is not active on instance {id(self)}")
            return False, "Monitoring is not active"
        
        logger.info(f"Stopping monitoring thread on instance {id(self)}")
        self.monitoring = False
        self.last_warning_time = 0
        self._stop_event.set()  # Wake the thread immediately from sleep
        self.save_monitoring_status(False)
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        self._stop_event.clear()
        return True, "Monitoring stopped"
    
    def is_monitoring(self):
        """Check if monitoring is active and thread is alive"""
        if self.monitoring and self.monitor_thread and self.monitor_thread.is_alive():
            return True
        # If flag is True but thread is dead, clean up the stale state
        if self.monitoring:
            logger.warning(f"Monitoring flag is True but thread is dead — cleaning up (instance {id(self)})")
            self.monitoring = False
            self.save_monitoring_status(False)
        return False
    
    def _monitor_loop(self, check_interval):
        """Internal monitoring loop (runs in background thread)"""
        logger.info(f"[Monitor] Thread started on instance {id(self)} (interval: {check_interval}s)")
        print(f"[Monitor] Started background monitoring (interval: {check_interval}s)")
        
        try:
            while self.monitoring:
                # Check if monitoring was turned off while sleeping
                if not self.monitoring:
                    logger.info(f"[Monitor] Monitoring flag set to False, exiting loop on instance {id(self)}")
                    break
                    
                if self.is_active:
                    # Kill switch already active, stop monitoring
                    logger.info(f"[Monitor] Kill switch is active, stopping monitoring on instance {id(self)}")
                    print("[Monitor] Kill switch is active, stopping monitoring")
                    self.monitoring = False
                    self.save_monitoring_status(False)
                    break
                
                # Check if market is open - if not, exit monitoring thread
                if not self.is_market_open():
                    logger.info(f"[Monitor] Market is closed, stopping monitoring thread on instance {id(self)}")
                    print("[Monitor] Market is closed, stopping monitoring")
                    self.monitoring = False
                    self.save_monitoring_status(False)
                    break
                
                try:
                    day_pnl, net_pnl = self.get_total_pnl()
                    
                    # Check conditions
                    should_trigger, reason = self.check_conditions(day_pnl, net_pnl)
                    
                    if should_trigger:
                        logger.warning(f"[Monitor] Trigger condition met on instance {id(self)}: {reason}")
                        print(f"[Monitor] Trigger condition met: {reason}")
                        self.close_all_positions(reason)
                        self.monitoring = False
                        self.save_monitoring_status(False)
                        break
                    
                except Exception as e:
                    logger.error(f"[Monitor] Error in monitoring loop on instance {id(self)}: {e}")
                    print(f"[Monitor] Error in monitoring loop: {e}")
                
                # Interruptible sleep — wakes immediately if stop_monitoring() is called
                self._stop_event.wait(timeout=check_interval)
            
            logger.info(f"[Monitor] Thread exiting normally on instance {id(self)}")
                
        except Exception as e:
            logger.error(f"[Monitor] Fatal error in monitoring thread on instance {id(self)}: {e}", exc_info=True)
            print(f"[Monitor] Fatal error in monitoring thread: {e}")
            self.monitoring = False
            self.save_monitoring_status(False)
        
        print("[Monitor] Background monitoring stopped")
    
    def monitor(self, check_interval=5):
        """Monitor P&L and auto-trigger kill switch"""
        print("=" * 60)
        print("ADVANCED KILL SWITCH MONITOR")
        print("=" * 60)
        print(f"Capital: ₹{self.capital:,}")
        print(f"Max Loss: {self.loss_display}")
        print(f"Profit Threshold: {self.profit_display}")
        print(f"Profit Drawdown: {self.drawdown_display}")
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
