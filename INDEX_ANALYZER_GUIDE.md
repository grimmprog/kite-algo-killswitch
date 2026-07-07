# Index Analyzer Guide

## 🎯 Overview

The Index Analyzer helps you determine which index (SENSEX, NIFTY 50, or BANK NIFTY) offers the best trading opportunity and suggests the optimal option type (CE/PE) and strike price.

## 🚀 Features

### 1. Multi-Index Analysis
- Analyzes SENSEX, NIFTY 50, and BANK NIFTY simultaneously
- Compares momentum, volatility, volume, and trend
- Ranks indices by trading opportunity score (0-100)

### 2. Smart Recommendations
- Suggests best index to trade
- Recommends CE or PE based on trend analysis
- Calculates optimal strike price (ATM/OTM/ITM)
- Provides confidence score for each setup

### 3. Comprehensive Metrics
- **Momentum**: 1-hour and 1-day price changes
- **Volatility**: ATR-based volatility percentage
- **Volume**: Current vs average volume ratio
- **Trend**: Bullish, Bearish, or Neutral
- **Range Position**: Where price sits in daily range

## 📱 Telegram Commands

### `/analyze` or `/indices`
Analyzes all three indices and shows detailed comparison

**Example:**
```
User: /analyze

Bot: 📊 INDEX ANALYSIS REPORT

Analyzed: 3 indices
Time: 14:23:45

🏆 BANK NIFTY (Score: 75/100)
   Price: ₹60,250.00 (+0.85% 1H)
   Trend: BULLISH (STRONG_BULLISH)
   Suggested: CE 60300
   Lot Size: 15 | Vol: 1.45x
   ✅ Strong opportunity - High momentum & volatility

🥈 NIFTY 50 (Score: 55/100)
   Price: ₹25,800.00 (+0.45% 1H)
   Trend: BULLISH (BULLISH)
   Suggested: CE 25850
   Lot Size: 50 | Vol: 1.20x
   🟡 Moderate opportunity - Decent setup

🥉 SENSEX (Score: 40/100)
   Price: ₹83,900.00 (+0.25% 1H)
   Trend: NEUTRAL (NEUTRAL)
   Suggested: PE 83900
   Lot Size: 10 | Vol: 1.05x
   ⚠️ Weak opportunity - Low conviction

🎯 RECOMMENDATION
Trade: BANKNIFTY CE 60300
Reason: STRONG_BULLISH trend with 75/100 score

[✅ Trade BANKNIFTY CE 60300] [🔄 Refresh Analysis]
```

### `/best`
Shows only the single best trading opportunity

**Example:**
```
User: /best

Bot: 🔥 BEST TRADING OPPORTUNITY

Index: BANK NIFTY
Trade: BANKNIFTY CE 60300
Score: 75/100

Analysis:
• Current Price: ₹60,250.00
• 1H Change: +0.85%
• 1D Change: +1.25%
• Trend: BULLISH (STRONG_BULLISH)
• Volatility: 1.85%
• Volume: 1.45x average
• Range Position: 75%

Trade Details:
• Lot Size: 15
• Strike: 60300
• Type: CE

✅ Strong Setup - High conviction trade

[✅ Execute Trade] [📊 Compare All Indices] [🔄 Refresh]
```

## 🧮 Scoring System

### Total Score: 0-100 points

**Momentum (30 points)**
- 1H change > 1.0%: 30 points
- 1H change > 0.5%: 20 points
- 1H change > 0.25%: 10 points

**Volatility (20 points)**
- ATR > 1.5%: 20 points
- ATR > 1.0%: 15 points
- ATR > 0.5%: 10 points

**Volume (20 points)**
- Volume > 1.5x avg: 20 points
- Volume > 1.2x avg: 15 points
- Volume > 1.0x avg: 10 points

**Trend Clarity (20 points)**
- Clear Bullish/Bearish: 20 points
- Neutral: 5 points

**Range Position (10 points)**
- At extremes (>80% or <20%): 10 points
- Near extremes (>70% or <30%): 5 points

### Score Interpretation

| Score | Rating | Action |
|-------|--------|--------|
| 70-100 | 🔥 Strong | High conviction - Execute trade |
| 50-69 | ✅ Moderate | Decent setup - Trade with caution |
| 0-49 | ⚠️ Weak | Low conviction - Avoid or wait |

## 🎯 Option Type Selection

### CE (Call Option) Suggested When:
- **Strong Bullish**: Trend is bullish + 1H change > +0.3% + Range position < 70%
- **Bullish**: 1H change > +0.2% OR (Bullish trend + Range position < 60%)

### PE (Put Option) Suggested When:
- **Strong Bearish**: Trend is bearish + 1H change < -0.3% + Range position > 30%
- **Bearish**: 1H change < -0.2% OR (Bearish trend + Range position > 40%)

### Default:
- **Neutral**: PE (safer in uncertain conditions)

## 📊 Strike Price Selection

### Strong Bullish (CE)
- Slightly OTM: Current price + 1 strike gap
- Example: NIFTY at 25,750 → CE 25,800

### Strong Bearish (PE)
- Slightly OTM: Current price - 1 strike gap
- Example: NIFTY at 25,750 → PE 25,700

### Moderate Trend
- ATM: Nearest strike to current price
- Example: NIFTY at 25,750 → 25,750 or 25,800

### Neutral/Weak
- Slightly ITM for safety
- CE: Current price - 1 strike gap
- PE: Current price + 1 strike gap

## 🔧 Configuration

### Strike Gaps
```python
# In index_analyzer.py
self.indices = {
    'NIFTY 50': {
        'strike_gap': 50  # ₹50 gap between strikes
    },
    'BANK NIFTY': {
        'strike_gap': 100  # ₹100 gap
    },
    'SENSEX': {
        'strike_gap': 100  # ₹100 gap
    }
}
```

### Lot Sizes
```python
'NIFTY 50': {'lot_size': 50},
'BANK NIFTY': {'lot_size': 15},
'SENSEX': {'lot_size': 10}
```

## 📈 Usage Examples

### Example 1: Strong Bullish Setup
```
Market Conditions:
- BANK NIFTY: +1.2% in 1H
- High volume (1.8x average)
- Clear uptrend
- Price at 65% of daily range

Analysis Result:
✅ Score: 85/100
✅ Trend: STRONG_BULLISH
✅ Suggested: BANKNIFTY CE 60300 (slightly OTM)
✅ Action: Execute with high conviction
```

### Example 2: Moderate Bearish Setup
```
Market Conditions:
- NIFTY 50: -0.6% in 1H
- Normal volume (1.1x average)
- Bearish trend forming
- Price at 45% of daily range

Analysis Result:
🟡 Score: 58/100
🟡 Trend: BEARISH
🟡 Suggested: NIFTY PE 25750 (ATM)
🟡 Action: Trade with caution
```

### Example 3: Weak/Neutral Setup
```
Market Conditions:
- SENSEX: +0.15% in 1H
- Low volume (0.9x average)
- No clear trend
- Price at 50% of daily range

Analysis Result:
⚠️ Score: 35/100
⚠️ Trend: NEUTRAL
⚠️ Suggested: SENSEX PE 83900 (ATM)
⚠️ Action: Avoid or wait for better setup
```

## 🎮 Interactive Features

### Button Actions

**✅ Execute Trade**
- Places market order for suggested option
- Calculates quantity based on risk (₹2000 per trade)
- Sends confirmation with order ID

**📊 Compare All Indices**
- Shows side-by-side comparison
- Highlights best opportunity
- Quick refresh option

**🔄 Refresh Analysis**
- Re-analyzes all indices
- Updates scores and recommendations
- Useful for fast-moving markets

## 🧪 Testing

### Test Standalone
```bash
cd kite-algo
python index_analyzer.py
```

**Expected Output:**
```
======================================================================
INDEX ANALYZER - FIND BEST TRADING OPPORTUNITY
======================================================================

Analyzing indices...
✅ NIFTY 50: Score=65, CE 25800
✅ BANK NIFTY: Score=75, CE 60300
✅ SENSEX: Score=45, PE 83900

📊 INDEX ANALYSIS REPORT
...

🏆 Best opportunity: BANK NIFTY CE 60300
   Score: 75/100
   Trend: STRONG_BULLISH
```

### Test in Telegram
```
1. Start bot: python telegram_bot.py
2. Send: /analyze
3. Verify: All 3 indices analyzed
4. Click: "Trade BANKNIFTY CE 60300"
5. Verify: Order placed successfully
```

## 🔍 Understanding the Metrics

### Momentum (Change %)
- **Positive**: Bullish momentum, consider CE
- **Negative**: Bearish momentum, consider PE
- **Near zero**: Neutral, wait for direction

### Volatility (ATR %)
- **High (>1.5%)**: Great for options, higher premiums
- **Medium (0.5-1.5%)**: Decent for trading
- **Low (<0.5%)**: Poor for options, low movement

### Volume Ratio
- **>1.5x**: Strong participation, reliable moves
- **1.0-1.5x**: Normal activity
- **<1.0x**: Low participation, be cautious

### Range Position
- **>80%**: Near high, potential reversal or breakout
- **50-80%**: Mid-to-high range, bullish bias
- **20-50%**: Mid-to-low range, bearish bias
- **<20%**: Near low, potential reversal or breakdown

## 💡 Pro Tips

### 1. Best Times to Use
- **Market Open (9:15-10:00)**: High volatility, clear trends
- **Mid-day (11:30-1:30)**: Consolidation breakouts
- **Last Hour (2:30-3:30)**: Strong directional moves

### 2. Combine with Other Signals
- Use `/analyze` to find best index
- Use `/consolidation` to find entry timing
- Use `/scan` for additional confirmation

### 3. Score Thresholds
- **>70**: Trade immediately
- **50-70**: Wait for confirmation
- **<50**: Skip or wait for better setup

### 4. Risk Management
- Higher score = Higher position size
- Lower score = Smaller position size or skip
- Always use stop losses

### 5. Market Conditions
- **Trending Market**: Trust the analysis
- **Choppy Market**: Require higher scores (>70)
- **Low Volume**: Avoid trading

## 🚨 Important Notes

### Data Source
- Uses Yahoo Finance (yfinance)
- Free and reliable
- 5-minute candle data
- Real-time during market hours

### Limitations
- Analysis based on technical indicators only
- Does not consider news/events
- Past performance ≠ future results
- Use as one input in decision making

### Refresh Frequency
- Refresh every 15-30 minutes
- More frequent in fast markets
- Less frequent in slow markets

## 🔄 Workflow

### Recommended Trading Flow

1. **Morning (9:15 AM)**
   ```
   /analyze → Check which index is strongest
   ```

2. **Entry Decision (9:30 AM)**
   ```
   /best → Get specific trade recommendation
   Click "Execute Trade" if score > 70
   ```

3. **Mid-day Check (12:00 PM)**
   ```
   /analyze → Re-evaluate all indices
   /consolidation → Look for breakout setups
   ```

4. **Afternoon (2:00 PM)**
   ```
   /best → Final opportunity check
   /positions → Monitor open trades
   ```

5. **Before Close (3:15 PM)**
   ```
   /status → Check P&L
   /close → Exit if needed
   ```

## 📊 Sample Analysis Scenarios

### Scenario 1: Strong BANK NIFTY Day
```
Time: 10:30 AM
Command: /analyze

Result:
🏆 BANK NIFTY (Score: 82/100)
   +1.5% in 1H, 2.1x volume
   STRONG_BULLISH
   Suggested: CE 60400

Action: Execute BANKNIFTY CE 60400
Reason: High score + strong trend + high volume
```

### Scenario 2: Mixed Signals
```
Time: 1:00 PM
Command: /best

Result:
🟡 NIFTY 50 (Score: 58/100)
   +0.4% in 1H, 1.1x volume
   BULLISH
   Suggested: CE 25850

Action: Wait or small position
Reason: Moderate score, needs confirmation
```

### Scenario 3: No Clear Opportunity
```
Time: 11:00 AM
Command: /analyze

Result:
All indices < 50 score
Low volume across board
Neutral trends

Action: Skip trading
Reason: No high-conviction setups
```

## 🎓 Learning from Analysis

### What Makes a Good Setup?

**High Score Setup (70+)**
- Clear trend direction
- High momentum (>0.8% 1H)
- Above-average volume (>1.3x)
- Good volatility (>1.2%)
- Price at favorable range position

**Poor Setup (<50)**
- No clear trend
- Low momentum (<0.3% 1H)
- Below-average volume (<1.0x)
- Low volatility (<0.5%)
- Price in middle of range

## 🆘 Troubleshooting

### No Data Available
```
Issue: "❌ Could not fetch data for indices"

Solutions:
1. Check internet connection
2. Verify yfinance is installed: pip install yfinance
3. Try again (Yahoo Finance may be temporarily down)
4. Check if market is open
```

### Low Scores Always
```
Issue: All indices showing scores < 30

Reasons:
1. Market is in consolidation
2. Low volatility period
3. Pre-market or post-market hours
4. Holiday/weekend

Action: Wait for market to pick up momentum
```

### Wrong Recommendations
```
Issue: Suggested trade doesn't match your view

Remember:
1. Analysis is technical only
2. Doesn't consider fundamentals/news
3. Use as one input, not sole decision
4. Combine with your own analysis
```

## 📝 Quick Reference

**Commands:**
- `/analyze` - Full analysis of all indices
- `/best` - Best single opportunity
- `/indices` - Alias for /analyze

**Score Ranges:**
- 70-100: Strong (🔥)
- 50-69: Moderate (✅)
- 0-49: Weak (⚠️)

**Option Types:**
- CE: Bullish view
- PE: Bearish view

**Strike Selection:**
- OTM: Strong trend
- ATM: Moderate trend
- ITM: Weak/Neutral

---

**Happy Trading! 🚀**

For more features, see: `TELEGRAM_BOT_IMPROVEMENTS.md`
