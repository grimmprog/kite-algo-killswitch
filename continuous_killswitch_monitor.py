"""
Continuous Kill Switch Monitor
Runs in background and automatically:
1. Monitors P&L every 30 seconds
2. Closes positions when thresholds breached
3. Deactivates F&O segment automatically
4. Sends Telegram alerts
"""
from connect import get_kite_session
from notifier import notifier
from segment_automation import ZerodhaSegmentAutomation
import config
import time
import json
import os
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/killswitch_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ContinuousKillSwitchMonitor:
    def __init__(self):
        self.kite = get_kite_session()
        self.capital = config.CAPITAL
        self.status_file = "killswitch_status.json"
        
        # Thresholds
        self.max_loss_threshold = 4000  # ₹4,000 loss
        self.max_loss_percent = 10  # 10% of capital
        self.profit_threshold = 5000  # ₹5,000 profit
        self.profit_drawdown = 2000  # ₹2,000 drawdown from peak
        
        self.highest_pnl = 0
        self.is_active = self.load_status()
        self.segment_deactivated = False
        
        # Check interval (seconds)
        self.check_interval = 30  # Check every 30 seconds
        
    def load_status(self):
        """Load kill switch status"""
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r') as f:
                    data = json.load(f)
                    return data.get('active', False)
            except:
                return False
        return False
    
    def save_status(self, active, reason=""):
        """Save kill switch status"""
        data = {
            'active': active,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'segment_deactivated': self.segment_deactivated
        }
        with open(self.status_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_total_pnl(self):
        """Get total P&L"""
        try:
            positions = self.kite.positions()
            day_pnl = sum([pos['pnl'] for pos in positions['day']])
            net_pnl = sum([pos['pnl'] for pos in positions['net']])
            return day_pnl, net_pnl
        except Exception as e:
            logger.error(f"Error fetching P&L: {e}")
            return 0, 0
    
    def get_open_positions(self):
        """Get open positions"""
        try:
            positions = self.kite.positions()['net']
            return [pos for pos in positions if pos['quantity'] != 0]
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def close_all_positions(self):
        """Close all open positions"""
        positions = self.get_open_positions()
        
        if not positions:
            logger.info("No open positions to close")
            return 0
        
        logger.info(f"Closing {len(positions)} position(s)...")
        success_count = 0
        
        for pos in positions:
            try:
                transaction_type = "SELL" if pos['quantity'] > 0 else "BUY"
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=pos['exchange'],
                    tradingsymbol=pos['tradingsymbol'],
                    transaction_type=transaction_type,
                    quantity=abs(pos['quantity']),
                    product=pos['product'],
                    order_type=self.kite.ORDER_TYPE_MARKET
                )
                logger.info(f"✅ Closed {pos['tradingsymbol']}: {order_id}")
                success_count += 1
            except Exception as e:
                logger.error(f"❌ Failed to close {pos['tradingsymbol']}: {e}")
        
        return success_count
    
    def deactivate_segment(self):
        """Deactivate F&O segment using Selenium"""
        if self.segment_deactivated:
            logger.info("Segment already deactivated")
            return True
        
        logger.info("=" * 60)
        logger.info("DEACTIVATING F&O SEGMENT")
        logger.info("=" * 60)
        
        try:
            automation = ZerodhaSegmentAutomation(headless=True)
            success = automation.deactivate_fno_segment()
            
            if success:
                logger.info("✅ F&O segment deactivated successfully!")
                self.segment_deactivated = True
                return True
            else:
                logger.error("❌ Failed to deactivate segment")
                return False
                
        except Exception as e:
            logger.error(f"❌ Segment deactivation error: {e}")
            return False
    
    def activate_killswitch(self, reason):
        """Activate kill switch - close positions and deactivate segment"""
        logger.info("=" * 60)
        logger.info(f"🚨 KILL SWITCH ACTIVATED: {reason}")
        logger.info("=" * 60)
        
        # Get current P&L
        day_pnl, _ = self.get_total_pnl()
        pnl_percent = (day_pnl / self.capital) * 100
        
        # Step 1: Close all positions
        positions_closed = self.close_all_positions()
        
        # Wait for orders to execute
        time.sleep(3)
        
        # Step 2: Deactivate F&O segment
        segment_success = self.deactivate_segment()
        
        # Step 3: Mark as active
        self.is_active = True
        self.save_status(True, reason)
        
        # Step 4: Send comprehensive notification
        message = (
            f"🚨 **KILL SWITCH ACTIVATED**\n\n"
            f"**Reason:** {reason}\n"
            f"**Day P&L:** ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)\n"
            f"**Time:** {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"**Actions Taken:**\n"
            f"✅ Positions closed: {positions_closed}\n"
            f"{'✅' if segment_success else '❌'} F&O segment: {'Deactivated' if segment_success else 'Failed'}\n"
            f"✅ Bot stopped trading\n\n"
        )
        
        if not segment_success:
            message += (
                f"⚠️ **MANUAL ACTION REQUIRED:**\n"
                f"Deactivate F&O segment manually at:\n"
                f"https://console.zerodha.com/account/segment-activation\n\n"
            )
        
        message += f"**Capital:** ₹{self.capital:,}\n"
        message += f"**Peak P&L:** ₹{self.highest_pnl:,.2f}\n"
        
        notifier.send_message(message)
        
        logger.info("=" * 60)
        logger.info("KILL SWITCH ACTIVATION COMPLETE")
        logger.info("=" * 60)
        
        return True
    
    def check_conditions(self, day_pnl):
        """Check if kill switch should be triggered"""
        
        # Update highest P&L
        if day_pnl > self.highest_pnl:
            self.highest_pnl = day_pnl
        
        pnl_percent = (day_pnl / self.capital) * 100
        
        # Rule 1: Loss > ₹4,000 OR Loss > 10% of capital
        if day_pnl < -self.max_loss_threshold or pnl_percent < -self.max_loss_percent:
            return True, f"Loss threshold breached: ₹{day_pnl:,.2f} ({pnl_percent:.2f}%)"
        
        # Rule 2: Profit > ₹5,000 and dropped by ₹2,000
        if self.highest_pnl >= self.profit_threshold:
            drawdown = self.highest_pnl - day_pnl
            if drawdown >= self.profit_drawdown:
                return True, f"Profit drawdown: Peak ₹{self.highest_pnl:,.2f} → Current ₹{day_pnl:,.2f}"
        
        return False, "All systems normal"
    
    def monitor(self):
        """Continuous monitoring loop"""
        logger.info("=" * 60)
        logger.info("CONTINUOUS KILL SWITCH MONITOR")
        logger.info("=" * 60)
        logger.info(f"Capital: ₹{self.capital:,}")
        logger.info(f"Max Loss: ₹{self.max_loss_threshold:,} OR {self.max_loss_percent}%")
        logger.info(f"Profit Threshold: ₹{self.profit_threshold:,}")
        logger.info(f"Profit Drawdown: ₹{self.profit_drawdown:,}")
        logger.info(f"Check Interval: {self.check_interval}s")
        logger.info("=" * 60)
        
        if self.is_active:
            logger.warning("⚠️  KILL SWITCH IS ALREADY ACTIVE")
            logger.warning("Monitoring will continue but no new triggers")
        
        # Send startup notification
        notifier.send_message(
            f"🛡️ **Kill Switch Monitor Started**\n\n"
            f"Monitoring P&L every {self.check_interval}s\n"
            f"Max Loss: ₹{self.max_loss_threshold:,} ({self.max_loss_percent}%)\n"
            f"Profit Protection: ₹{self.profit_threshold:,}\n\n"
            f"Status: {'🔴 ACTIVE' if self.is_active else '🟢 MONITORING'}"
        )
        
        logger.info("\n🔍 Monitoring started... (Press Ctrl+C to stop)\n")
        
        try:
            while True:
                try:
                    # Get current P&L
                    day_pnl, net_pnl = self.get_total_pnl()
                    open_positions = len(self.get_open_positions())
                    
                    pnl_percent = (day_pnl / self.capital) * 100
                    status_emoji = "🟢" if day_pnl >= 0 else "🔴"
                    
                    # Display status
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    status_line = (
                        f"\r{status_emoji} P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%) | "
                        f"Peak: ₹{self.highest_pnl:,.2f} | "
                        f"Open: {open_positions} | "
                        f"{'🔴 ACTIVE' if self.is_active else '🟢 OK'} | "
                        f"{timestamp}"
                    )
                    print(status_line, end='', flush=True)
                    
                    # Check conditions (only if not already active)
                    if not self.is_active:
                        should_trigger, reason = self.check_conditions(day_pnl)
                        
                        if should_trigger:
                            print("\n")  # New line before activation
                            logger.warning(f"⚠️  THRESHOLD BREACHED: {reason}")
                            self.activate_killswitch(reason)
                            
                            # Continue monitoring but don't trigger again
                            logger.info("Kill switch activated. Continuing to monitor...")
                    
                except Exception as e:
                    logger.error(f"\n❌ Error in monitoring loop: {e}")
                
                # Wait before next check
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n\n⚠️  Monitor stopped by user")
            day_pnl, _ = self.get_total_pnl()
            logger.info(f"Final Day P&L: ₹{day_pnl:,.2f}")
            logger.info(f"Peak P&L: ₹{self.highest_pnl:,.2f}")
            logger.info(f"Kill Switch: {'ACTIVE' if self.is_active else 'INACTIVE'}")
            
            notifier.send_message(
                f"⚠️ **Kill Switch Monitor Stopped**\n\n"
                f"Final P&L: ₹{day_pnl:,.2f}\n"
                f"Status: {'🔴 ACTIVE' if self.is_active else '🟢 INACTIVE'}"
            )

def main():
    """Main function"""
    # Create logs directory
    os.makedirs('logs', exist_ok=True)
    
    # Start monitoring
    monitor = ContinuousKillSwitchMonitor()
    monitor.monitor()

if __name__ == "__main__":
    main()
