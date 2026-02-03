"""
Kill Switch System - Advanced Risk Management
Monitors daily P&L and automatically closes all positions based on rules:
1. Loss > ₹4,000 - Activate kill switch
2. Profit > ₹5,000 and drops by ₹2,000 - Activate kill switch
3. Profit > 10% of capital - Send warning
"""
from connect import get_kite_session
from notifier import notifier
import config
import time
import sys
from datetime import datetime

class KillSwitch:
    def __init__(self):
        self.kite = get_kite_session()
        self.capital = config.CAPITAL
        self.max_loss_threshold = 4000
        self.profit_threshold = 5000
        self.profit_drawdown = 2000
        self.profit_warning_percent = 10
        
        self.highest_pnl = 0
        self.kill_switch_active = False
        self.warning_sent = False
        
    def get_total_pnl(self):
        """Get total P&L for the day from all positions"""
        try:
            positions = self.kite.positions()
            
            # Net positions (current open positions)
            net_pnl = sum([pos['pnl'] for pos in positions['net']])
            
            # Day positions (includes closed positions)
            day_pnl = sum([pos['pnl'] for pos in positions['day']])
            
            return day_pnl, net_pnl
            
        except Exception as e:
            print(f"Error fetching P&L: {e}")
            return 0, 0
    
    def get_open_positions(self):
        """Get all open positions"""
        try:
            positions = self.kite.positions()['net']
            return [pos for pos in positions if pos['quantity'] != 0]
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []
    
    def close_all_positions(self, reason):
        """Close all open positions immediately"""
        print(f"\n{'=' * 60}")
        print(f"🚨 KILL SWITCH ACTIVATED: {reason}")
        print(f"{'=' * 60}")
        
        positions = self.get_open_positions()
        
        if not positions:
            print("No open positions to close.")
            return True
        
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
        
        print(f"\n{success_count}/{len(positions)} positions closed successfully.")
        
        # Send Telegram notification
        day_pnl, _ = self.get_total_pnl()
        message = (
            f"🚨 KILL SWITCH ACTIVATED\n\n"
            f"Reason: {reason}\n"
            f"Total Day P&L: ₹{day_pnl:,.2f}\n"
            f"Positions Closed: {success_count}/{len(positions)}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        notifier.send_message(message)
        
        return success_count == len(positions)
    
    def check_rules(self, day_pnl, net_pnl):
        """Check all kill switch rules"""
        
        # Update highest P&L
        if day_pnl > self.highest_pnl:
            self.highest_pnl = day_pnl
        
        # Rule 1: Loss > ₹4,000
        if day_pnl < -self.max_loss_threshold:
            self.close_all_positions(f"Daily loss exceeded ₹{self.max_loss_threshold:,}")
            self.kill_switch_active = True
            return True
        
        # Rule 2: Profit > ₹5,000 and dropped by ₹2,000
        if self.highest_pnl >= self.profit_threshold:
            drawdown = self.highest_pnl - day_pnl
            if drawdown >= self.profit_drawdown:
                self.close_all_positions(
                    f"Profit drawdown: Peak ₹{self.highest_pnl:,.2f} → Current ₹{day_pnl:,.2f} (₹{drawdown:,.2f} drop)"
                )
                self.kill_switch_active = True
                return True
        
        # Rule 3: Profit > 10% of capital - Warning only
        profit_percent = (day_pnl / self.capital) * 100
        if profit_percent >= self.profit_warning_percent and not self.warning_sent:
            message = (
                f"⚠️ PROFIT WARNING\n\n"
                f"Today's profit: ₹{day_pnl:,.2f} ({profit_percent:.1f}% of capital)\n"
                f"Consider booking profits or activating kill switch manually.\n"
                f"Peak P&L: ₹{self.highest_pnl:,.2f}\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}"
            )
            notifier.send_message(message)
            print(f"\n⚠️  Profit warning sent: {profit_percent:.1f}% of capital")
            self.warning_sent = True
        
        return False
    
    def monitor(self, check_interval=5):
        """
        Continuously monitor P&L and check kill switch rules
        check_interval: seconds between checks (default 5)
        """
        print("=" * 60)
        print("KILL SWITCH MONITOR STARTED")
        print("=" * 60)
        print(f"Capital: ₹{self.capital:,}")
        print(f"Max Loss Threshold: ₹{self.max_loss_threshold:,}")
        print(f"Profit Threshold: ₹{self.profit_threshold:,}")
        print(f"Profit Drawdown Limit: ₹{self.profit_drawdown:,}")
        print(f"Profit Warning: {self.profit_warning_percent}% of capital")
        print(f"Check Interval: {check_interval} seconds")
        print("=" * 60)
        print("\nMonitoring... (Press Ctrl+C to stop)\n")
        
        try:
            while not self.kill_switch_active:
                day_pnl, net_pnl = self.get_total_pnl()
                open_positions = len(self.get_open_positions())
                
                # Calculate percentages
                day_pnl_percent = (day_pnl / self.capital) * 100
                
                # Display status
                status = "🟢" if day_pnl >= 0 else "🔴"
                print(
                    f"\r{status} Day P&L: ₹{day_pnl:,.2f} ({day_pnl_percent:+.2f}%) | "
                    f"Peak: ₹{self.highest_pnl:,.2f} | "
                    f"Open: {open_positions} | "
                    f"Time: {datetime.now().strftime('%H:%M:%S')}",
                    end='', flush=True
                )
                
                # Check kill switch rules
                if self.check_rules(day_pnl, net_pnl):
                    break
                
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\n\n⚠️  Monitor stopped by user.")
            day_pnl, _ = self.get_total_pnl()
            print(f"Final Day P&L: ₹{day_pnl:,.2f}")
            print(f"Peak P&L: ₹{self.highest_pnl:,.2f}")
        except Exception as e:
            print(f"\n\n❌ Error: {e}")
            notifier.send_message(f"❌ Kill Switch Monitor Error: {e}")
    
    def manual_close_all(self):
        """Manually trigger kill switch"""
        day_pnl, _ = self.get_total_pnl()
        print(f"\nCurrent Day P&L: ₹{day_pnl:,.2f}")
        confirm = input("Manually close all positions? (yes/no): ").strip().lower()
        
        if confirm == 'yes':
            self.close_all_positions("Manual kill switch activation")
            self.kill_switch_active = True
        else:
            print("Manual close cancelled.")

def main():
    print("=" * 60)
    print("KILL SWITCH SYSTEM")
    print("=" * 60)
    print("\nOptions:")
    print("1. Start monitoring (auto kill switch)")
    print("2. Check current P&L")
    print("3. Manually close all positions")
    print("=" * 60)
    
    choice = input("\nSelect option (1/2/3): ").strip()
    
    ks = KillSwitch()
    
    if choice == '1':
        # Ask for check interval
        fast = input("Fast mode (2s checks) for active trading? (y/n): ").strip().lower()
        interval = 2 if fast == 'y' else 5
        ks.monitor(check_interval=interval)
        
    elif choice == '2':
        day_pnl, net_pnl = ks.get_total_pnl()
        positions = ks.get_open_positions()
        
        print("\n" + "=" * 60)
        print("CURRENT STATUS")
        print("=" * 60)
        print(f"Day P&L: ₹{day_pnl:,.2f} ({(day_pnl/ks.capital)*100:+.2f}%)")
        print(f"Net P&L: ₹{net_pnl:,.2f}")
        print(f"Open Positions: {len(positions)}")
        print("=" * 60)
        
        # Send to Telegram
        status_emoji = "🟢" if day_pnl >= 0 else "🔴"
        message = (
            f"{status_emoji} **DAILY STATUS UPDATE**\n\n"
            f"Day P&L: ₹{day_pnl:,.2f} ({(day_pnl/ks.capital)*100:+.2f}%)\n"
            f"Net P&L: ₹{net_pnl:,.2f}\n"
            f"Open Positions: {len(positions)}\n"
            f"Capital: ₹{ks.capital:,}\n"
            f"Time: {datetime.now().strftime('%d-%b %H:%M:%S')}"
        )
        
        if positions:
            print("\nOpen Positions:")
            message += "\n\n📊 Open Positions:\n"
            for pos in positions:
                print(f"  {pos['tradingsymbol']}: {pos['quantity']} @ ₹{pos['average_price']:.2f} | P&L: ₹{pos['pnl']:.2f}")
                message += f"• {pos['tradingsymbol']}: {pos['quantity']} @ ₹{pos['average_price']:.2f} | P&L: ₹{pos['pnl']:.2f}\n"
        
        notifier.send_message(message)
        print("\n✅ Status sent to Telegram")
        
    elif choice == '3':
        ks.manual_close_all()
    
    else:
        print("Invalid option.")

if __name__ == "__main__":
    main()
