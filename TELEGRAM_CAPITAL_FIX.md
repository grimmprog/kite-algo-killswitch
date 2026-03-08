# Telegram Bot Capital & Kill Switch Fix

## Changes Made

### 1. Fixed Hardcoded Kill Switch Thresholds
The telegram bot was using hardcoded values (₹4,000) instead of reading from `.env` configuration.

**Fixed in telegram_bot.py:**
- `__init__`: Now calculates ALL thresholds from config on startup (loss, profit, drawdown)
- `pnl_command`: Uses dynamic `self.max_loss_threshold` instead of hardcoded 4000
- `killswitch_command`: Uses dynamic thresholds with proper display
- `risk_command`: Uses dynamic thresholds for calculations

### 2. Added Drawdown Threshold Support
The telegram bot now properly initializes and displays the drawdown threshold.

**Drawdown Threshold:**
- Percentage-based: 40% of peak profit (from `.env`)
- Example: If you reach ₹10,000 profit, kill switch triggers if profit drops to ₹6,000
- This protects your profits from giving back too much

### 3. Added Capital Management Features

**New Command: `/setcapital <amount>`**
- Allows updating capital via Telegram
- Automatically recalculates all thresholds based on percentages
- Example: `/setcapital 30000`

**Enhanced `/capital` Command:**
- Shows both Kite account balance and configured capital
- Displays current loss, profit, and drawdown thresholds
- Includes "Sync from Kite Account" button to auto-fetch available balance

**New Callback: `sync_capital_callback`**
- Syncs capital from Kite account with one click
- Recalculates all percentage-based thresholds

### 4. Current Configuration (.env)
```
CAPITAL=25000
LOSS_THRESHOLD_PERCENT=3
PROFIT_THRESHOLD_PERCENT=12.5
DRAWDOWN_THRESHOLD_PERCENT=40
```

**Calculated Thresholds:**
- Loss Threshold: 3% of ₹25,000 = ₹750
- Profit Threshold: 12.5% of ₹25,000 = ₹3,125
- Drawdown Threshold: 40% of peak profit

**How Drawdown Works:**
1. You start trading with ₹25,000
2. You make profit and reach ₹28,125 (₹3,125 profit = 12.5%)
3. This becomes your "peak profit" - kill switch starts tracking
4. If profit drops by 40% from peak (₹1,250), kill switch triggers
5. Kill switch activates at ₹26,875 (₹1,875 profit remaining)

## How to Use

### Update Capital via Telegram:
1. **Manual Entry:** `/setcapital 30000`
2. **Sync from Kite:** Use `/capital` then click "Sync from Kite Account" button

### View Current Settings:
- `/capital` - Shows Kite balance, configured capital, and all thresholds
- `/risk` - Shows risk metrics with current thresholds
- `/thresholds` - Shows all kill switch thresholds (uses AdvancedKillSwitch)

### Make Changes Permanent:
To persist capital changes across bot restarts, update `.env`:
```bash
CAPITAL=30000
```

## Testing
Restart the telegram bot to apply changes:
```bash
python3 telegram_bot.py
```

Then test:
1. `/capital` - Verify all thresholds are calculated correctly (loss, profit, drawdown)
2. `/risk` - Check risk metrics use new thresholds
3. `/killswitch` - Confirm kill switch uses dynamic values
4. `/thresholds` - View all thresholds including drawdown
5. `/setcapital 20000` - Test capital update
6. Click "Sync from Kite" button - Test auto-sync

## Notes
- Capital changes via Telegram are temporary (until bot restart)
- To make permanent, update `CAPITAL` in `.env` file
- Percentage-based thresholds automatically recalculate when capital changes
- Fixed amount thresholds (commented out in .env) remain constant
- Drawdown threshold is percentage of PEAK PROFIT, not capital
- Drawdown only activates after reaching profit threshold
