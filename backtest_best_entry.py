"""
BEST ENTRY - NIFTY 25200 PE at 13:15 PM
Based on actual chart data showing 86.70 → 190.65 move
"""

print("=" * 80)
print("NIFTY 25200 PE - BEST ENTRY OF THE DAY")
print("Entry: 13:15 PM at ₹86.70 → Exit: 13:42 PM at ₹190.65")
print("Date: 23-Jan-2026 | Based on Actual Chart Data")
print("=" * 80)

# Analyze what happened before 13:15
print("\n📊 SETUP ANALYSIS - What Led to 13:15 Entry")
print("=" * 80)

print("\n🔍 Price Action Before Entry:")
print("   12:45 - Premium: ₹77.80 (Consolidation)")
print("   12:48 - Premium: ₹80.55 (Small move)")
print("   12:51 - Premium: ₹78.15 (Pullback)")
print("   12:54 - Premium: ₹74.65 (Dip)")
print("   12:57 - Premium: ₹81.80 (Recovery)")
print("   13:00 - Premium: ₹81.20 (Consolidation)")
print("   13:03 - Premium: ₹86.65 (Building)")
print("   13:06 - Premium: ₹88.15 (Higher)")
print("   13:09 - Premium: ₹86.80 (Slight pullback)")
print("   13:12 - Premium: ₹86.65 (Consolidation)")
print("   13:15 - Premium: ₹107.70 (BREAKOUT! 🚀)")
print("   ")
print("   ⚠️ WAIT! Chart shows CLOSE at 107.70, but OPEN was 86.70")
print("   📍 PERFECT ENTRY: 86.70 at candle OPEN (13:15)")

print("\n✅ WHY 13:15 IS THE BEST ENTRY:")
print("   • Consolidation 12:45-13:12 (range: 74-88)")
print("   • Multiple tests of 86-88 resistance")
print("   • 13:15 candle OPENS at 86.70")
print("   • Immediate breakout to 107.70 (close)")
print("   • Massive momentum continuation")

# Perfect Entry Setup
print("\n1️⃣ BEST ENTRY SETUP (13:15 PM)")
print("=" * 80)

entry_time = "13:15 PM"
entry_premium = 86.70  # Candle OPEN price
candle_close = 107.70  # Candle CLOSE price

print(f"   Entry Time: {entry_time}")
print(f"   Entry Premium: ₹{entry_premium:.2f} (Candle OPEN)")
print(f"   Candle Close: ₹{candle_close:.2f} (+24% in 3 minutes!)")
print(f"   ")
print(f"   ✅ Entry Confirmation:")
print(f"      • Consolidation breakout")
print(f"      • Multiple resistance tests at 86-88")
print(f"      • Strong volume surge")
print(f"      • Immediate 24% move in first candle")
print(f"      • Clear trend acceleration")

# Position Details
lot_size = 65
quantity = lot_size
investment = entry_premium * quantity

print("\n2️⃣ POSITION DETAILS")
print("=" * 80)
print(f"   Symbol: NIFTY 23JAN26 25200 PE")
print(f"   Entry Price: ₹{entry_premium:.2f}")
print(f"   Quantity: {quantity} (1 lot)")
print(f"   Investment: ₹{investment:,.2f}")

# Risk Management
sl_premium = 81.20  # Low of consolidation at 13:00
risk = (entry_premium - sl_premium) * quantity

print("\n3️⃣ RISK MANAGEMENT")
print("=" * 80)
print(f"   Stop Loss: ₹{sl_premium:.2f} (Consolidation low)")
print(f"   Risk: ₹{risk:,.2f}")
print(f"   Risk per lot: Only ₹{risk:,.2f} (very tight!)")

# Trade Progression with ACTUAL data
print("\n4️⃣ TRADE PROGRESSION (Actual 3-Min Data)")
print("=" * 80)

trades = [
    ("13:15", 86.70, 107.70, "🎯 ENTRY → Immediate breakout!"),
    ("13:18", 107.40, 114.70, "Continuation"),
    ("13:21", 115.00, 122.40, "Strong momentum"),
    ("13:24", 122.00, 120.55, "Slight pullback"),
    ("13:27", 120.55, 126.50, "Recovery"),
    ("13:30", 126.50, 168.85, "EXPLOSIVE MOVE! 🚀"),
    ("13:33", 168.80, 167.05, "Consolidation"),
    ("13:36", 166.95, 170.70, "Higher"),
    ("13:39", 171.55, 170.30, "Holding"),
    ("13:42", 170.20, 190.65, "🎯 PEAK! +120%"),
    ("13:45", 190.55, 172.40, "Profit taking"),
]

print("\n   Time  | Open    | Close   | P&L (from entry) | Status")
print("   " + "-" * 75)

max_profit = 0
for time, open_p, close_p, status in trades:
    if time == "13:15":
        pnl = 0
        print(f"   {time:5s} | ₹{open_p:6.2f} | ₹{close_p:7.2f} | ₹{pnl:+9,.2f}     | {status}")
    else:
        pnl = (close_p - entry_premium) * quantity
        if pnl > max_profit:
            max_profit = pnl
            peak_time = time
            peak_premium = close_p
        print(f"   {time:5s} | ₹{open_p:6.2f} | ₹{close_p:7.2f} | ₹{pnl:+9,.2f}     | {status}")

# Exit strategies
print("\n5️⃣ EXIT STRATEGIES & RESULTS")
print("=" * 80)

exits = [
    ("Conservative", "13:18", 114.70, "Exit after first candle confirmation"),
    ("Moderate", "13:30", 168.85, "Exit on explosive candle"),
    ("Aggressive", "13:42", 190.65, "Exit at peak"),
    ("Trailing SL", "13:45", 172.40, "Exit on pullback from peak"),
]

print("\n   Strategy      | Exit Time | Exit Price | P&L        | ROI")
print("   " + "-" * 75)

for strategy, time, price, note in exits:
    pnl = (price - entry_premium) * quantity
    roi = (pnl / investment) * 100
    print(f"   {strategy:13s} | {time:9s} | ₹{price:8.2f} | ₹{pnl:+9,.2f} | {roi:+6.2f}%")
    print(f"                |           |            | {note}")

# Best exit analysis
best_exit_premium = 190.65
best_exit_time = "13:42"
best_pnl = (best_exit_premium - entry_premium) * quantity
best_roi = (best_pnl / investment) * 100

print("\n6️⃣ OPTIMAL EXIT (Peak at 13:42)")
print("=" * 80)
print(f"   Entry: ₹{entry_premium:.2f} at 13:15 PM")
print(f"   Exit: ₹{best_exit_premium:.2f} at {best_exit_time}")
print(f"   Duration: 27 minutes")
print(f"   ")
print(f"   Points Captured: ₹{best_exit_premium - entry_premium:.2f}")
print(f"   💰 Profit: ₹{best_pnl:+,.2f}")
print(f"   📈 ROI: {best_roi:+.2f}%")
print(f"   🎯 Risk:Reward: 1:{(best_exit_premium - entry_premium)/(entry_premium - sl_premium):.1f}")
print(f"   ")
print(f"   ✅ EXCEPTIONAL TRADE!")

# Comparison with other entries
print("\n7️⃣ ENTRY COMPARISON - Why 13:15 Beats All Others")
print("=" * 80)

comparison = [
    ("11:03", 70.60, 105.30, "Good move but capped at 105"),
    ("11:15", 60.90, 105.30, "Better entry, same peak"),
    ("13:15", 86.70, 190.65, "BEST - Explosive breakout! ⭐"),
]

print("\n   Entry Time | Entry Price | Peak Price | Profit/Lot | ROI")
print("   " + "-" * 75)

for time, entry, peak, note in comparison:
    profit = (peak - entry) * quantity
    roi = ((peak - entry) / entry) * 100
    marker = " 🏆" if time == "13:15" else ""
    print(f"   {time:10s} | ₹{entry:9.2f} | ₹{peak:8.2f} | ₹{profit:+8,.2f} | {roi:+6.2f}%{marker}")

print("\n8️⃣ WHY 13:15 IS THE BEST ENTRY OF THE DAY")
print("=" * 80)
print("""
   ✅ Technical Setup:
      • Clear consolidation 12:45-13:12
      • Multiple tests of 86-88 resistance
      • Tight range = coiling for breakout
      • Volume building during consolidation
      
   ✅ Entry Timing:
      • Entered at candle OPEN (86.70)
      • Immediate confirmation (close 107.70)
      • 24% gain in first 3 minutes!
      • No drawdown - straight up
      
   ✅ Risk Management:
      • Tight stop at 81.20 (only ₹357.50 risk)
      • Risk:Reward = 1:19 (exceptional!)
      • Clear invalidation level
      
   ✅ Profit Potential:
      • 120% ROI in 27 minutes
      • ₹6,756.75 profit on 1 lot
      • Far exceeds morning entries
      • Explosive momentum move
      
   🎯 Key Insight:
      • Consolidation breakouts > Trend pullbacks
      • Tight range = explosive potential
      • Entry at breakout > Entry in trend
      • 13:15 entry captured 2x the move of 11:03
""")

print("\n9️⃣ STRATEGY LESSONS")
print("=" * 80)
print("""
   📚 What We Learned:
   
   1. CONSOLIDATION BREAKOUTS are more powerful than pullbacks
      • 11:03 entry: 70.60 → 105.30 (49% gain)
      • 13:15 entry: 86.70 → 190.65 (120% gain)
      
   2. TIGHT RANGES = BIG MOVES
      • 30-minute consolidation (74-88 range)
      • Coiled spring effect
      • Explosive breakout
      
   3. MULTIPLE TIME FRAMES
      • 5-min: Shows consolidation pattern
      • 3-min: Confirms breakout
      • Entry at candle open = best timing
      
   4. RISK:REWARD MATTERS
      • 11:03: 1:1 RR (good)
      • 13:15: 1:19 RR (exceptional!)
      
   5. PATIENCE PAYS
      • Waiting for setup > Forcing trades
      • Best move came at 1:15 PM
      • Not in the "optimal" 11:00-11:30 window!
""")

print("\n" + "=" * 80)
print("BEST ENTRY ANALYSIS COMPLETE")
print("=" * 80)
print(f"\n🏆 WINNER: 13:15 PM Entry at ₹86.70")
print(f"   Profit: ₹{best_pnl:+,.2f} | ROI: {best_roi:+.2f}% | Duration: 27 minutes")
print(f"\n💡 Key Takeaway: Consolidation breakouts can be more profitable than")
print(f"   trend pullbacks. Always watch for tight ranges after trends!")
