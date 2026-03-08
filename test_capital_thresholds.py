#!/usr/bin/env python3
"""
Quick test to verify capital and threshold calculations
"""
import config

def test_thresholds():
    """Test threshold calculations with current config"""
    
    print("=" * 60)
    print("CAPITAL & THRESHOLD TEST")
    print("=" * 60)
    
    capital = config.CAPITAL
    print(f"\n💰 Configured Capital: ₹{capital:,}")
    
    # Loss Threshold
    print("\n📉 LOSS THRESHOLD:")
    if config.LOSS_THRESHOLD_PERCENT > 0:
        loss_threshold = (config.LOSS_THRESHOLD_PERCENT / 100) * capital
        print(f"   Percentage: {config.LOSS_THRESHOLD_PERCENT}%")
        print(f"   Amount: ₹{loss_threshold:,.0f}")
    else:
        print(f"   Fixed Amount: ₹{config.LOSS_THRESHOLD:,.0f}")
    
    # Profit Threshold
    print("\n📈 PROFIT THRESHOLD:")
    if config.PROFIT_THRESHOLD_PERCENT > 0:
        profit_threshold = (config.PROFIT_THRESHOLD_PERCENT / 100) * capital
        print(f"   Percentage: {config.PROFIT_THRESHOLD_PERCENT}%")
        print(f"   Amount: ₹{profit_threshold:,.0f}")
    else:
        print(f"   Fixed Amount: ₹{config.PROFIT_THRESHOLD:,.0f}")
    
    # Drawdown Threshold
    print("\n📊 DRAWDOWN THRESHOLD:")
    if config.DRAWDOWN_THRESHOLD_PERCENT > 0:
        print(f"   Percentage: {config.DRAWDOWN_THRESHOLD_PERCENT}%")
        print(f"   (Applied to peak profit)")
        print(f"   Example: If peak profit is ₹10,000")
        print(f"            Drawdown limit: ₹{(config.DRAWDOWN_THRESHOLD_PERCENT / 100) * 10000:,.0f}")
        print(f"            Kill switch triggers at: ₹{10000 - (config.DRAWDOWN_THRESHOLD_PERCENT / 100) * 10000:,.0f}")
    else:
        print(f"   Fixed Amount: ₹{config.DRAWDOWN_THRESHOLD:,.0f}")
        print(f"   Example: If peak profit is ₹10,000")
        print(f"            Kill switch triggers at: ₹{10000 - config.DRAWDOWN_THRESHOLD:,.0f}")
    
    print("\n" + "=" * 60)
    print("✅ All thresholds calculated successfully!")
    print("=" * 60)
    
    # Test with different capital values
    print("\n\n🔄 TESTING WITH DIFFERENT CAPITAL VALUES:")
    print("=" * 60)
    
    test_capitals = [20000, 25000, 30000, 40000, 50000]
    
    for test_cap in test_capitals:
        loss = (config.LOSS_THRESHOLD_PERCENT / 100) * test_cap if config.LOSS_THRESHOLD_PERCENT > 0 else config.LOSS_THRESHOLD
        profit = (config.PROFIT_THRESHOLD_PERCENT / 100) * test_cap if config.PROFIT_THRESHOLD_PERCENT > 0 else config.PROFIT_THRESHOLD
        
        print(f"\nCapital: ₹{test_cap:,}")
        print(f"  Loss Threshold: ₹{loss:,.0f}")
        print(f"  Profit Threshold: ₹{profit:,.0f}")

if __name__ == "__main__":
    test_thresholds()
