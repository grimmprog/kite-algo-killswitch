# Quick Test Guide

Run these commands to verify everything is working:

## 1. Test Data Source (yfinance)
```bash
python test_yfinance.py
```

**Expected**: ✅ Fetched 20+ days of NIFTY data

## 2. Test Scanner Integration
```bash
python -c "from scanner import market_scanner; df = market_scanner.fetch_ohlc('NIFTY 50'); print(f'✅ Scanner works! Fetched {len(df)} candles')"
```

**Expected**: ✅ Scanner works! Fetched 22 candles

## 3. Test Kite Connection
```bash
python test_connection.py
```

**Expected**: ✅ Connection successful! User ID: YS2567

## 4. Test Telegram
```bash
python verify_telegram.py
```

**Expected**: ✅ Notification sent. Check your Telegram.

## 5. Start Bot
```bash
python start_bot.py
```

**Expected**: Bot starts scanning with FREE data from Yahoo Finance

## Troubleshooting

### yfinance not working?
```bash
pip install yfinance
python test_yfinance.py
```

### Scanner returns empty?
- Check internet connection
- Verify yfinance is installed
- Check logs: `type logs\bot.log`

### Kite API errors?
```bash
python login.py  # Generate new token
python test_connection.py  # Verify
```

## All Tests Passing?

✅ Data source working (yfinance)
✅ Scanner integration working
✅ Kite API connected
✅ Telegram bot responding

**You're ready to trade!** 🚀

```bash
python start_bot.py
```
