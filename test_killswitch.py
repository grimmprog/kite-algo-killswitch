"""
Test Kill Switch Command
"""
from connect import get_kite_session
import config

def test_killswitch():
    kite = get_kite_session()
    
    # Get P&L
    positions_data = kite.positions()
    day_pnl = sum([pos['pnl'] for pos in positions_data['day']])
    net_positions = [pos for pos in positions_data['net'] if pos['quantity'] != 0]
    
    print("=" * 60)
    print("KILL SWITCH TEST")
    print("=" * 60)
    
    # Calculate status
    max_loss = 4000
    profit_warning = config.CAPITAL * 0.10
    
    status = "🟢 SAFE"
    if day_pnl < -max_loss:
        status = "🚨 TRIGGERED"
    elif day_pnl < -config.MAX_DAILY_LOSS:
        status = "⚠️ WARNING"
    
    pnl_emoji = "🟢" if day_pnl >= 0 else "🔴"
    pnl_percent = (day_pnl / config.CAPITAL) * 100
    
    print(f"\nStatus: {status}")
    print(f"{pnl_emoji} Day P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)")
    print(f"Open Positions: {len(net_positions)}")
    print(f"Capital: ₹{config.CAPITAL:,}")
    
    print("\nThresholds:")
    print(f"• Max Loss: ₹{max_loss:,}")
    print(f"• Profit Warning: 10% (₹{int(profit_warning):,})")
    
    if net_positions:
        print("\n✅ Kill switch button WILL be shown (positions open)")
        print("\nOpen Positions:")
        for pos in net_positions:
            print(f"  • {pos['tradingsymbol']}: {pos['quantity']} @ ₹{pos['average_price']:.2f}")
    else:
        print("\n⚠️  Kill switch button will NOT be shown (no positions)")
    
    print("=" * 60)

if __name__ == "__main__":
    test_killswitch()
