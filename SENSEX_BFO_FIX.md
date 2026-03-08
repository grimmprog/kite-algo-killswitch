# SENSEX BFO Exchange Fix

## Issue
Bot was failing with "Option not found: SENSEX 82300 PE" because it was looking for SENSEX options on NFO (NSE F&O) instead of BFO (BSE F&O).

## Root Cause
SENSEX options trade on BSE (Bombay Stock Exchange) in the BFO segment, not on NSE.

## Exchange Mapping

### NFO (NSE F&O)
- NIFTY 50
- BANK NIFTY

### BFO (BSE F&O)
- SENSEX

## Changes Made

### 1. index_analyzer.py
Added `exchange` field to each index configuration:
```python
'NIFTY 50': {
    'exchange': 'NFO',  # NSE F&O
    ...
},
'BANK NIFTY': {
    'exchange': 'NFO',  # NSE F&O
    ...
},
'SENSEX': {
    'exchange': 'BFO',  # BSE F&O
    ...
}
```

### 2. telegram_bot.py
Updated `execute_index_trade()` to:
- Get exchange from analysis results
- Fallback to BFO for SENSEX if not in results
- Use correct exchange when fetching instruments

## Testing

### Before Fix
```
/analyze
❌ Option not found: SENSEX 82300 PE
```

### After Fix
```
/analyze
✅ SENSEX analysis works
✅ Correct exchange (BFO) used
✅ Options found successfully
```

## Lot Sizes (Corrected)
- NIFTY 50: 65 (NFO)
- BANK NIFTY: 30 (NFO)
- SENSEX: 20 (BFO)

## How to Verify

### Check SENSEX Options on Kite
1. Go to Kite web/app
2. Search for "SENSEX"
3. Options will show exchange as "BFO"
4. Example: SENSEX26FEB82500PE

### Via Code
```python
from kiteconnect import KiteConnect
kite = KiteConnect(api_key="your_key")
kite.set_access_token("your_token")

# Get BFO instruments
bfo_instruments = kite.instruments("BFO")
sensex_options = [i for i in bfo_instruments if i['name'] == 'SENSEX']
print(f"Found {len(sensex_options)} SENSEX options on BFO")
```

## Important Notes

1. Always use BFO for SENSEX options
2. Always use NFO for NIFTY and BANKNIFTY options
3. Exchange is now included in analysis results
4. Bot automatically selects correct exchange

## Files Updated
✅ index_analyzer.py - Added exchange field
✅ telegram_bot.py - Updated execute_index_trade()
✅ config.py - Lot sizes corrected
✅ LOT_SIZES_2026.md - Documentation updated

## Status
✅ Fixed and tested
✅ Ready for live trading
