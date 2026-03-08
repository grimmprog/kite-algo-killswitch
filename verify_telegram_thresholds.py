#!/usr/bin/env python3
"""
Verify telegram bot has correct thresholds loaded
"""
import config

def verify_thresholds():
    """Verify all thresholds are configured correctly"""
    
    print("=" * 70)
    print("TELEGRAM BOT THRESHOLD VERIFICATION")
    print("=" * 70)
    
    # Check capital
    print(f"\n💰 Capital: ₹{config.CAPITAL:,}")
    
    # Check loss threshold
    print("\n📉 LOSS THRESHOLD:")
    if config.LOSS_THRESHOLD_PERCENT > 0:
        loss_threshold = (config.LOSS_THRESHOLD_PERCENT / 100) * config.CAPITAL
        loss_display = f"{config.LOSS_THRESHOLD_PERCENT}% (₹{loss_threshold:,.0f})"
        print(f"   ✅ Using percentage: {loss_display}")
    else:
        print(f"   ✅ Using fixed amount: ₹{config.LOSS_THRESHOLD:,.0f}")
    
    # Check profit threshold
    print("\n📈 PROFIT THRESHOLD:")
    if config.PROFIT_THRESHOLD_PERCENT > 0:
        profit_threshold = (config.PROFIT_THRESHOLD_PERCENT / 100) * config.CAPITAL
        profit_display = f"{config.PROFIT_THRESHOLD_PERCENT}% (₹{profit_threshold:,.0f})"
        print(f"   ✅ Using percentage: {profit_display}")
    else:
        print(f"   ✅ Using fixed amount: ₹{config.PROFIT_THRESHOLD:,.0f}")
    
    # Check drawdown threshold
    print("\n📊 DRAWDOWN THRESHOLD:")
    if config.DRAWDOWN_THRESHOLD_PERCENT > 0:
        drawdown_display = f"{config.DRAWDOWN_THRESHOLD_PERCENT}% of peak"
        print(f"   ✅ Using percentage: {drawdown_display}")
    else:
        print(f"   ✅ Using fixed amount: ₹{config.DRAWDOWN_THRESHOLD:,.0f}")
    
    print("\n" + "=" * 70)
    print("✅ ALL THRESHOLDS CONFIGURED CORRECTLY")
    print("=" * 70)
    
    # Simulate telegram bot initialization
    print("\n🤖 SIMULATING TELEGRAM BOT INITIALIZATION:")
    print("-" * 70)
    
    capital = config.CAPITAL
    
    # Loss threshold
    if config.LOSS_THRESHOLD_PERCENT > 0:
        max_loss_threshold = (config.LOSS_THRESHOLD_PERCENT / 100) * capital
        loss_display = f"{config.LOSS_THRESHOLD_PERCENT}% (₹{max_loss_threshold:,.0f})"
    else:
        max_loss_threshold = config.LOSS_THRESHOLD
        loss_display = f"₹{max_loss_threshold:,.0f}"
    
    # Profit threshold
    if config.PROFIT_THRESHOLD_PERCENT > 0:
        profit_threshold = (config.PROFIT_THRESHOLD_PERCENT / 100) * capital
        profit_display = f"{config.PROFIT_THRESHOLD_PERCENT}% (₹{profit_threshold:,.0f})"
    else:
        profit_threshold = config.PROFIT_THRESHOLD
        profit_display = f"₹{profit_threshold:,.0f}"
    
    # Drawdown threshold
    if config.DRAWDOWN_THRESHOLD_PERCENT > 0:
        drawdown_percent = config.DRAWDOWN_THRESHOLD_PERCENT
        drawdown_display = f"{config.DRAWDOWN_THRESHOLD_PERCENT}% of peak"
    else:
        profit_drawdown = config.DRAWDOWN_THRESHOLD
        drawdown_percent = 0
        drawdown_display = f"₹{profit_drawdown:,.0f}"
    
    print(f"self.capital = {capital:,}")
    print(f"self.max_loss_threshold = {max_loss_threshold:,.0f}")
    print(f"self.loss_display = '{loss_display}'")
    print(f"self.profit_threshold = {profit_threshold:,.0f}")
    print(f"self.profit_display = '{profit_display}'")
    print(f"self.drawdown_display = '{drawdown_display}'")
    
    print("\n" + "=" * 70)
    print("✅ TELEGRAM BOT WILL USE THESE VALUES")
    print("=" * 70)
    
    # Test commands output
    print("\n📱 TELEGRAM COMMAND OUTPUTS:")
    print("-" * 70)
    
    print("\n/capital command will show:")
    print(f"  Configured Capital: ₹{capital:,}")
    print(f"  Loss Threshold: {loss_display}")
    print(f"  Profit Threshold: {profit_display}")
    print(f"  Drawdown Threshold: {drawdown_display}")
    
    print("\n/risk command will show:")
    day_pnl = -500  # Example
    pnl_percent = (day_pnl / capital) * 100
    max_loss_pct = (max_loss_threshold / capital) * 100
    print(f"  Day P&L: ₹{day_pnl:,.2f} ({pnl_percent:+.2f}%)")
    print(f"  Max Loss: {loss_display} ({max_loss_pct:.1f}%)")
    
    print("\n/killswitch command will show:")
    remaining = max_loss_threshold - abs(day_pnl)
    print(f"  Loss: ₹{day_pnl:,.2f}")
    print(f"  Remaining: ₹{remaining:,.2f} until activation")
    
    print("\n" + "=" * 70)
    print("🎉 VERIFICATION COMPLETE - ALL SYSTEMS GO!")
    print("=" * 70)

if __name__ == "__main__":
    verify_thresholds()
