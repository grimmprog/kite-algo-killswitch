"""
Emergency Kill Switch
Manually trigger segment deactivation when loss exceeds threshold
"""
from segment_automation import ZerodhaSegmentAutomation
from connect import get_kite_session
from notifier import notifier
import config
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_current_pnl():
    """Get current P&L"""
    try:
        kite = get_kite_session()
        positions = kite.positions()
        day_pnl = sum([pos['pnl'] for pos in positions['day']])
        return day_pnl
    except Exception as e:
        logger.error(f"Error fetching P&L: {e}")
        return 0

def trigger_emergency_killswitch():
    """Trigger emergency kill switch"""
    print("=" * 60)
    print("🚨 EMERGENCY KILL SWITCH")
    print("=" * 60)
    
    # Get current P&L
    day_pnl = get_current_pnl()
    pnl_percent = (day_pnl / config.CAPITAL) * 100
    
    print(f"\nCurrent Status:")
    print(f"  Day P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)")
    print(f"  Capital: ₹{config.CAPITAL:,}")
    print(f"  Loss Threshold: 10% (₹{config.CAPITAL * 0.1:,.0f})")
    
    if day_pnl >= 0:
        print(f"\n✅ No loss detected. Kill switch not needed.")
        return
    
    loss_percent = abs(pnl_percent)
    
    if loss_percent < 10:
        print(f"\n⚠️  Loss is {loss_percent:.2f}% (below 10% threshold)")
        confirm = input("Activate kill switch anyway? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Kill switch cancelled.")
            return
    else:
        print(f"\n🚨 CRITICAL: Loss is {loss_percent:.2f}% (exceeds 10% threshold)")
        print("Kill switch activation REQUIRED!")
    
    print("\n" + "=" * 60)
    print("ACTIONS TO BE TAKEN:")
    print("=" * 60)
    print("1. Deactivate F&O (NFO) segment on Zerodha")
    print("2. Prevent any new trades")
    print("3. Send Telegram notification")
    print("4. Mark kill switch as active")
    print("=" * 60)
    
    confirm = input("\nProceed with kill switch activation? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("\n❌ Kill switch cancelled by user.")
        return
    
    print("\n" + "=" * 60)
    print("ACTIVATING KILL SWITCH...")
    print("=" * 60)
    
    # Step 1: Deactivate F&O segment
    print("\n1. Deactivating F&O segment...")
    try:
        automation = ZerodhaSegmentAutomation(headless=False)  # Show browser for confirmation
        success = automation.deactivate_fno_segment()
        
        if success:
            print("   ✅ F&O segment deactivated successfully")
            segment_status = "✅ F&O segment deactivated"
        else:
            print("   ❌ Failed to deactivate segment automatically")
            print("   ⚠️  Please deactivate manually at:")
            print("   https://console.zerodha.com/account/segment-activation")
            segment_status = "⚠️ Manual deactivation required"
    except Exception as e:
        print(f"   ❌ Error: {e}")
        segment_status = "⚠️ Manual deactivation required"
        success = False
    
    # Step 2: Mark kill switch as active
    print("\n2. Marking kill switch as active...")
    try:
        import json
        kill_switch_data = {
            'active': True,
            'reason': f'Loss exceeded 10% threshold: {loss_percent:.2f}%',
            'timestamp': datetime.now().isoformat(),
            'day_pnl': day_pnl,
            'segment_deactivated': success
        }
        
        with open('killswitch_status.json', 'w') as f:
            json.dump(kill_switch_data, f, indent=2)
        
        print("   ✅ Kill switch status saved")
    except Exception as e:
        print(f"   ⚠️  Failed to save status: {e}")
    
    # Step 3: Send Telegram notification
    print("\n3. Sending Telegram notification...")
    try:
        message = (
            f"🚨 **EMERGENCY KILL SWITCH ACTIVATED**\n\n"
            f"**Reason:** Loss exceeded 10% threshold\n"
            f"**Day P&L:** ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)\n"
            f"**Loss:** {loss_percent:.2f}% of capital\n"
            f"**Time:** {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"**Actions Taken:**\n"
            f"1. {segment_status}\n"
            f"2. ✅ Kill switch marked as active\n"
            f"3. ✅ Bot will not place new trades\n\n"
        )
        
        if not success:
            message += (
                f"⚠️ **MANUAL ACTION REQUIRED:**\n"
                f"Deactivate F&O segment immediately:\n"
                f"https://console.zerodha.com/account/segment-activation\n\n"
            )
        
        message += (
            f"**Next Steps:**\n"
            f"1. Review today's trades\n"
            f"2. Analyze what went wrong\n"
            f"3. Do NOT trade for rest of the day\n"
            f"4. Review strategy before next session\n\n"
            f"To reactivate: Send /reactivate (only after review)"
        )
        
        notifier.send_message(message)
        print("   ✅ Telegram notification sent")
    except Exception as e:
        print(f"   ⚠️  Failed to send notification: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("🚨 KILL SWITCH ACTIVATED")
    print("=" * 60)
    print(f"\nFinal Status:")
    print(f"  Day P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)")
    print(f"  Segment: {'Deactivated' if success else 'Manual deactivation required'}")
    print(f"  Kill Switch: ACTIVE")
    print(f"  Trading: STOPPED")
    
    if not success:
        print(f"\n⚠️  IMPORTANT: Manually deactivate F&O segment at:")
        print(f"  https://console.zerodha.com/account/segment-activation")
    
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS:")
    print("=" * 60)
    print("1. Stop all trading for today")
    print("2. Review all trades and identify issues")
    print("3. Analyze strategy performance")
    print("4. Check risk management settings")
    print("5. Do NOT attempt recovery trades")
    print("6. Take a break and review tomorrow")
    print("=" * 60)

if __name__ == "__main__":
    trigger_emergency_killswitch()
