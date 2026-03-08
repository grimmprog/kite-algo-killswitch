# Quick Reference - Kill Switch Thresholds

## Current Settings (Capital: ₹25,000)

| Threshold | Setting | Amount | Triggers When |
|-----------|---------|--------|---------------|
| 🔴 Loss | 3% | ₹750 | Daily loss ≥ ₹750 |
| 🟢 Profit | 12.5% | ₹3,125 | Profit ≥ ₹3,125 (starts tracking) |
| 🟡 Drawdown | 40% | 40% of peak | Profit drops 40% from peak |

---

## Telegram Commands

| Command | What It Does |
|---------|--------------|
| `/capital` | View capital, thresholds, sync from Kite |
| `/setcapital 30000` | Update capital to ₹30,000 |
| `/risk` | Current risk metrics |
| `/killswitch` | Kill switch status |
| `/thresholds` | Detailed threshold info |
| `/pnl` | P&L with threshold warnings |

---

## Quick Examples

### Loss Threshold (₹750)
```
Start: ₹25,000
Loss:  ₹750
→ 🚨 KILL SWITCH ACTIVATED
```

### Profit Threshold (₹3,125)
```
Start:  ₹25,000
Profit: ₹3,125
→ 🟢 PROFIT PROTECTION ACTIVATED
→ System tracks peak profit
```

### Drawdown Threshold (40%)
```
Peak Profit: ₹10,000
Drops to:    ₹6,000 (40% drawdown)
→ 🚨 KILL SWITCH ACTIVATED
→ Profit secured: ₹6,000
```

---

## Service Commands

```bash
# Restart bot
sudo systemctl restart kite-trading-bot

# Check status
sudo systemctl status kite-trading-bot

# View logs
tail -f logs/bot_service.log
```

---

## Change Capital

### Via Telegram (Temporary)
```
/setcapital 30000
```

### Via .env (Permanent)
```bash
# Edit .env file
CAPITAL=30000

# Restart service
sudo systemctl restart kite-trading-bot
```

---

## Threshold Calculations

### With ₹25,000 Capital
- Loss: 3% = ₹750
- Profit: 12.5% = ₹3,125

### With ₹30,000 Capital
- Loss: 3% = ₹900
- Profit: 12.5% = ₹3,750

### With ₹40,000 Capital
- Loss: 3% = ₹1,200
- Profit: 12.5% = ₹5,000

---

## Files Updated

✅ `telegram_bot.py` - All thresholds now dynamic
✅ Service restarted - Changes active
✅ No more hardcoded ₹4,000

---

## Test Checklist

- [ ] Send `/capital` in Telegram
- [ ] Verify shows ₹750 loss threshold
- [ ] Verify shows ₹3,125 profit threshold
- [ ] Verify shows 40% drawdown threshold
- [ ] Test `/setcapital 30000`
- [ ] Verify thresholds recalculate
- [ ] Test "Sync from Kite" button

---

**Last Updated:** Feb 17, 2026
**Service Status:** ✅ Running
**Thresholds:** ✅ Configured
