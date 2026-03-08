# Correct Lot Sizes (Kite Platform 2026)

## Index Options Lot Sizes

### NSE (National Stock Exchange)

**NIFTY 50**
- Lot Size: 65
- Strike Step: 50
- Example: NIFTY 25600 CE = 65 units

**BANK NIFTY**
- Lot Size: 30
- Strike Step: 100
- Example: BANKNIFTY 61100 CE = 30 units

### BSE (Bombay Stock Exchange)

**SENSEX**
- Lot Size: 20
- Strike Step: 100
- Example: SENSEX 82500 PE = 20 units

## Updated Files
✅ config.py - INDICES dictionary
✅ index_analyzer.py - All lot sizes updated

## Position Sizing Example

### NIFTY 50 Trade
- Spot: ₹25,600
- Strike: 25600 CE
- Premium: ₹150
- Lot Size: 65
- **Investment: ₹150 × 65 = ₹9,750 per lot**

### BANK NIFTY Trade
- Spot: ₹61,100
- Strike: 61100 CE
- Premium: ₹200
- Lot Size: 30
- **Investment: ₹200 × 30 = ₹6,000 per lot**

### SENSEX Trade
- Spot: ₹82,500
- Strike: 82500 PE
- Premium: ₹180
- Lot Size: 20
- **Investment: ₹180 × 20 = ₹3,600 per lot**

## Capital Allocation

With ₹40,000 capital:
- NIFTY: Can trade 4 lots (₹39,000)
- BANK NIFTY: Can trade 6 lots (₹36,000)
- SENSEX: Can trade 11 lots (₹39,600)

## Important Notes

1. Lot sizes verified from Kite platform
2. NIFTY 50: 65 (not 25 or 50)
3. BANK NIFTY: 30 (not 15)
4. SENSEX: 20 (not 10)
5. Always verify before trading as exchanges can change lot sizes

## Verification

To verify current lot sizes:
```python
from kiteconnect import KiteConnect
kite = KiteConnect(api_key="your_key")
kite.set_access_token("your_token")

# Get instrument details
instruments = kite.instruments("NFO")
nifty = [i for i in instruments if i['tradingsymbol'].startswith('NIFTY') and i['instrument_type'] == 'CE']
print(f"NIFTY Lot Size: {nifty[0]['lot_size']}")
```

## Last Updated
February 25, 2026
