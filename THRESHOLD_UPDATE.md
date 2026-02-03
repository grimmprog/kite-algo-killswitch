# Kill Switch Threshold Update - Percentage-Based

## What Changed?

The kill switch now supports **percentage-based thresholds** in addition to fixed amounts. This makes the system more flexible and scalable with your trading capital.

## Why Percentage-Based?

- **Scales automatically** with your capital
- **More intuitive** - "10% loss" vs "₹4,000 loss"
- **Easier to adjust** when capital changes
- **Better risk management** - consistent risk across different capital levels

## Configuration

### Option 1: Percentage-Based (Recommended)

Edit your `.env` file:

```bash
# Trading Capital (required for percentage calculations)
CAPITAL=40000

# Loss threshold: 10% of capital = ₹4,000
LOSS_THRESHOLD_PERCENT=10

# Profit threshold: 12.5% of capital = ₹5,000
PROFIT_THRESHOLD_PERCENT=12.5

# Drawdown: 40% drop from peak profit
DRAWDOWN_THRESHOLD_PERCENT=40
```

### Option 2: Fixed Amount (Legacy)

```bash
# Fixed rupee amounts
LOSS_THRESHOLD=4000
PROFIT_THRESHOLD=5000
DRAWDOWN_THRESHOLD=2000
```

**Note:** If percentage is set (> 0), it takes priority over fixed amount.

## Examples

### Example 1: Conservative Trader (₹40,000 capital)
```bash
CAPITAL=40000
LOSS_THRESHOLD_PERCENT=5           # ₹2,000 max loss
PROFIT_THRESHOLD_PERCENT=10        # Track from ₹4,000 profit
DRAWDOWN_THRESHOLD_PERCENT=30      # 30% drop triggers
```

### Example 2: Moderate Trader (₹40,000 capital)
```bash
CAPITAL=40000
LOSS_THRESHOLD_PERCENT=10          # ₹4,000 max loss (default)
PROFIT_THRESHOLD_PERCENT=12.5      # Track from ₹5,000 profit (default)
DRAWDOWN_THRESHOLD_PERCENT=40      # 40% drop triggers (default)
```

### Example 3: Aggressive Trader (₹40,000 capital)
```bash
CAPITAL=40000
LOSS_THRESHOLD_PERCENT=15          # ₹6,000 max loss
PROFIT_THRESHOLD_PERCENT=20        # Track from ₹8,000 profit
DRAWDOWN_THRESHOLD_PERCENT=50      # 50% drop triggers
```

### Example 4: Larger Capital (₹1,00,000)
```bash
CAPITAL=100000
LOSS_THRESHOLD_PERCENT=10          # ₹10,000 max loss (scales automatically!)
PROFIT_THRESHOLD_PERCENT=12.5      # Track from ₹12,500 profit
DRAWDOWN_THRESHOLD_PERCENT=40      # 40% drop triggers
```

## Telegram Commands

### View Current Thresholds
```
/thresholds
```

Shows:
- Current capital
- Loss threshold (with calculated amount)
- Profit threshold (with calculated amount)
- Drawdown threshold

### Get Update Instructions
```
/setthreshold
```

Shows usage and examples for updating thresholds.

## How It Works

### Loss Threshold
- **Percentage:** Triggers when loss exceeds X% of capital
- **Fixed:** Triggers when loss exceeds ₹X
- **Example:** 10% of ₹40,000 = ₹4,000 loss triggers kill switch

### Profit Threshold
- **Percentage:** Starts tracking drawdown when profit reaches X% of capital
- **Fixed:** Starts tracking drawdown when profit reaches ₹X
- **Example:** 12.5% of ₹40,000 = ₹5,000 profit starts tracking

### Drawdown Threshold
- **Percentage:** Triggers when profit drops X% from peak
- **Fixed:** Triggers when profit drops ₹X from peak
- **Example:** Peak ₹5,000, 40% drop = ₹2,000 drop triggers (at ₹3,000)

## Updating on AWS

1. **SSH to your server:**
   ```bash
   ssh -i your-key.pem ubuntu@your-ec2-ip
   ```

2. **Edit .env file:**
   ```bash
   cd ~/kite-algo
   nano .env
   ```

3. **Update thresholds:**
   ```bash
   # Add or modify these lines
   CAPITAL=40000
   LOSS_THRESHOLD_PERCENT=10
   PROFIT_THRESHOLD_PERCENT=12.5
   DRAWDOWN_THRESHOLD_PERCENT=40
   ```

4. **Save and exit:**
   - Press `Ctrl+X`
   - Press `Y` to confirm
   - Press `Enter`

5. **Restart the bot:**
   ```bash
   sudo systemctl restart kite-trading-bot
   ```

6. **Verify:**
   ```bash
   # Check logs
   tail -f logs/bot_monitor.log
   
   # Or use Telegram
   /thresholds
   ```

## Migration from Fixed to Percentage

If you're currently using fixed amounts and want to switch to percentages:

### Current Fixed Settings:
```bash
LOSS_THRESHOLD=4000
PROFIT_THRESHOLD=5000
DRAWDOWN_THRESHOLD=2000
```

### Equivalent Percentage Settings (₹40,000 capital):
```bash
CAPITAL=40000
LOSS_THRESHOLD_PERCENT=10          # 4000/40000 = 10%
PROFIT_THRESHOLD_PERCENT=12.5      # 5000/40000 = 12.5%
DRAWDOWN_THRESHOLD_PERCENT=40      # 2000/5000 = 40%
```

## Backward Compatibility

- **Old .env files still work** - Fixed amounts are used if percentages not set
- **No breaking changes** - Existing configurations continue to function
- **Gradual migration** - Switch to percentages when ready

## Testing

After updating thresholds:

1. **Check status:**
   ```
   /thresholds
   ```

2. **Verify calculations:**
   - Loss threshold should show both % and ₹ amount
   - Profit threshold should show both % and ₹ amount
   - Drawdown should show % or ₹ based on setting

3. **Test monitoring:**
   ```
   /monitor
   ```
   
   Check logs show correct thresholds:
   ```bash
   tail -f logs/bot_monitor.log
   ```

## Troubleshooting

### Thresholds not updating?
- Restart the bot: `sudo systemctl restart kite-trading-bot`
- Check .env file has correct values: `cat .env | grep THRESHOLD`

### Wrong calculations?
- Verify CAPITAL is set correctly
- Check percentage values are numbers (not strings)
- Ensure no typos in variable names

### Bot not starting?
- Check logs: `sudo journalctl -u kite-trading-bot -n 50`
- Verify .env syntax (no spaces around =)
- Test manually: `python start_bot_with_monitor.py`

## Support

- View thresholds: `/thresholds`
- Get help: `/help`
- Check status: `/status`
- GitHub Issues: https://github.com/grimmprog/kite-algo-killswitch/issues

---

**Updated:** February 3, 2026
**Version:** 2.0 - Percentage-based thresholds
