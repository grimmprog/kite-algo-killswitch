# Enhanced Scanner Guide

## Overview
The enhanced scanner now detects BOTH bullish (CE/Call) and bearish (PE/Put) setups for:
- NSE: NIFTY 50
- BSE: SENSEX  
- NSE: NIFTY BANK

## Features

### 1. Bidirectional Scanning
- **BULLISH Signals** → Buy CE (Call) options
- **BEARISH Signals** → Buy PE (Put) options

### 2. Strike Selection
For each signal, the scanner provides:
- **ATM Strike** (At The Money) - Balanced risk/reward
- **ITM Strike** (In The Money) - Higher probability, lower returns

### 3. Confidence Scoring
Signals are scored 0-100% based on:
- Volume strength
- Proximity to EMA
- Time of day (early morning = higher score)
- Trend strength

## How to Use

### Via Telegram Bot
```
/scan - Run enhanced scanner
```

### Via Command Line
```bash
# Test the scanner
python test_enhanced_scanner_demo.py

# Run actual scan (during trading hours)
python test_enhanced_scanner.py
```

## Signal Interpretation

### BULLISH Signal Example
```
📈 NIFTY 50 (NSE)
Direction: BULLISH
Option: CE
Spot: ₹25,612.95
ATM Strike: 25600
ITM Strike: 25550
Confidence: 70%
Stop Loss: ₹25,507.90
```

**Action:** Buy NIFTY 25600 CE or 25550 CE

### BEARISH Signal Example
```
📉 SENSEX (BSE)
Direction: BEARISH
Option: PE
Spot: ₹82,500
ATM Strike: 82500
ITM Strike: 82600
Confidence: 75%
Stop Loss: ₹82,650
```

**Action:** Buy SENSEX 82500 PE or 82600 PE

## Strike Selection Guide

### ATM (At The Money)
- Strike price closest to spot price
- **Pros:** Higher returns, balanced Greeks
- **Cons:** More sensitive to price movement
- **Use when:** High confidence, trending market

### ITM (In The Money)
- Strike price already profitable
- **Pros:** Higher probability, less decay
- **Cons:** Lower returns, higher premium
- **Use when:** Moderate confidence, want safety

## Trend Detection

### Bullish Trend (CE)
Requires 3 out of 4:
- ✅ Price above VWAP
- ✅ EMA trending up
- ✅ MACD positive
- ✅ Price above EMA

### Bearish Trend (PE)
Requires 3 out of 4:
- ✅ Price below VWAP
- ✅ EMA trending down
- ✅ MACD negative
- ✅ Price below EMA

## Trading Hours
- Scan runs: 9:25 AM - 11:15 AM IST
- Auto-scan via Telegram bot during trading hours
- Manual test anytime with demo script

## Files
- `enhanced_scanner.py` - Main scanner logic
- `test_enhanced_scanner.py` - Live test (trading hours only)
- `test_enhanced_scanner_demo.py` - Demo test (anytime)
- `telegram_bot.py` - Integrated with /scan command

## Next Steps
1. Test during trading hours tomorrow (9:25 AM - 11:15 AM IST)
2. Use `/scan` in Telegram to get signals
3. Review ATM vs ITM strikes based on your risk appetite
4. Set stop loss at the provided level
5. Book profits at 1:2 or 1:3 risk-reward ratio

## Notes
- Scanner uses free Yahoo Finance data
- No subscription required
- Works for both NSE and BSE indices
- Confidence threshold: 70% (configurable in config.py)
