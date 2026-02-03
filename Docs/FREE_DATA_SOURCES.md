# Free Historical Data Integration

## Overview

The bot now uses **FREE** data sources for market analysis instead of requiring Kite's paid historical data API subscription.

## Data Sources (Priority Order)

### 1. Yahoo Finance (yfinance) - PRIMARY ✅
- **Status**: Most reliable and recommended
- **Cost**: FREE
- **API Key**: Not required
- **Coverage**: Global markets including Indian indices
- **Data**: Daily OHLC for NIFTY 50 (^NSEI) and NIFTY BANK (^NSEBANK)
- **Reliability**: Very high (Yahoo Finance infrastructure)

### 2. NSEpy - BACKUP
- **Status**: Backup option (sometimes has SSL issues)
- **Cost**: FREE
- **API Key**: Not required
- **Coverage**: NSE indices and stocks
- **Data**: Daily OHLC from NSE website
- **Reliability**: Medium (depends on NSE website availability)

### 3. Kite Historical API - FALLBACK
- **Status**: Fallback only
- **Cost**: ₹2,000/month subscription
- **API Key**: Required
- **Coverage**: All instruments
- **Data**: Intraday (5-min, 15-min, etc.) and daily
- **Reliability**: Very high

## Installation

```bash
# Activate virtual environment
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install all requirements (includes yfinance)
pip install -r requirements.txt

# Or install yfinance separately
pip install yfinance
```

## Testing

```bash
# Test yfinance (recommended)
python test_yfinance.py

# Test NSEpy (backup)
python test_nsepy.py

# Test scanner integration
python test_yfinance.py
```

## How It Works

### Data Fetching Priority
1. **Try yfinance first** - Most reliable, works 99% of the time
2. **Try NSEpy second** - If yfinance fails (rare)
3. **Try Kite API last** - If both free sources fail (requires subscription)

### Scanner Behavior
```python
from scanner import market_scanner

# Automatically uses yfinance (free)
signals = market_scanner.scan()
```

The scanner automatically:
- Detects available data sources
- Uses yfinance by default
- Falls back to NSEpy if needed
- Falls back to Kite API only if both fail

## Supported Indices

| Index | yfinance Ticker | NSEpy Symbol | Kite Symbol |
|-------|----------------|--------------|-------------|
| NIFTY 50 | ^NSEI | NIFTY | NIFTY 50 |
| NIFTY BANK | ^NSEBANK | NIFTY BANK | NIFTY BANK |

## Data Format

All sources provide the same format:
```python
{
    'date': datetime,
    'open': float,
    'high': float,
    'low': float,
    'close': float,
    'volume': int
}
```

## Strategy Adaptation

The strategy works with daily data:
- **EMA 20**: Calculated on daily closes
- **VWAP**: Daily VWAP
- **MACD**: Daily MACD
- **Volume**: Daily volume analysis

This is perfect for:
- End-of-day trading decisions
- Swing trading strategies
- Trend following systems

## Advantages of Free Data

✅ **No Subscription Cost** - Save ₹2,000/month
✅ **Reliable** - Yahoo Finance is very stable
✅ **Sufficient** - Daily data works for most strategies
✅ **Easy Setup** - No API key configuration
✅ **Global Access** - Works from anywhere

## Limitations

⚠️ **Daily Data Only** - No 5-minute intraday candles
⚠️ **End-of-Day** - Data updates after market close
⚠️ **Volume** - May be 0 for indices (normal for Yahoo Finance)

## When to Use Kite Historical API

Consider Kite's paid API if you need:
- 5-minute or 15-minute intraday candles
- Real-time tick data
- Futures and options historical data
- High-frequency trading strategies

For most algo trading strategies, **daily data is sufficient** and yfinance provides it for FREE!

## Troubleshooting

### yfinance Not Working
```bash
# Reinstall
pip uninstall yfinance
pip install yfinance

# Test
python test_yfinance.py
```

### No Data Returned
- Check internet connection
- Verify market is open (or use historical dates)
- Try different ticker (^NSEI vs ^NSEBANK)

### Scanner Returns Empty
```bash
# Check logs
type logs\bot.log

# Test data source
python test_yfinance.py
```

## Code Examples

### Get NIFTY Data
```python
import yfinance as yf

nifty = yf.Ticker("^NSEI")
df = nifty.history(period="1mo", interval="1d")
print(df.tail())
```

### Scanner Usage
```python
from scanner import market_scanner

# Automatically uses yfinance
signals = market_scanner.scan()

for signal in signals:
    print(f"Signal: {signal['symbol']} - {signal['type']}")
```

### Manual Data Fetch
```python
from scanner import market_scanner

# Fetch NIFTY 50 data
df = market_scanner.fetch_ohlc("NIFTY 50")
print(f"Latest Close: ₹{df.iloc[-1]['close']}")
```

## Summary

✅ **Installed**: yfinance (FREE)
✅ **Tested**: `python test_yfinance.py`
✅ **Integrated**: Scanner uses yfinance automatically
✅ **Working**: Ready for live trading
✅ **Cost**: ₹0 (completely free!)

The bot now uses Yahoo Finance for FREE market data while Kite API handles order execution. Best of both worlds! 🚀

