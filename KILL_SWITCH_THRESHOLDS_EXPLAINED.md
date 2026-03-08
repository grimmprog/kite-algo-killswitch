# Kill Switch Thresholds Explained

## Your Current Configuration

```env
CAPITAL=25000
LOSS_THRESHOLD_PERCENT=3
PROFIT_THRESHOLD_PERCENT=12.5
DRAWDOWN_THRESHOLD_PERCENT=40
```

## Three Types of Thresholds

### 1. Loss Threshold (Downside Protection)
**Purpose:** Stops trading when losses exceed acceptable limit

**Your Setting:** 3% of capital = ₹750

**How it works:**
```
Starting Capital: ₹25,000
Maximum Loss: ₹750 (3%)
Kill Switch Triggers at: ₹24,250

Day P&L: -₹750 or worse → 🚨 KILL SWITCH ACTIVATED
```

**Example Scenario:**
- 9:30 AM - Start trading with ₹25,000
- 10:15 AM - Loss reaches ₹750
- 🚨 Kill switch activates automatically
- All positions closed
- Trading stopped for the day

---

### 2. Profit Threshold (Profit Protection Activation)
**Purpose:** Starts tracking peak profit to protect gains

**Your Setting:** 12.5% of capital = ₹3,125

**How it works:**
```
Starting Capital: ₹25,000
Profit Threshold: ₹3,125 (12.5%)
Profit Protection Starts at: ₹28,125 total

Day P&L: +₹3,125 or better → 🟢 PROFIT PROTECTION ACTIVE
```

**Example Scenario:**
- 9:30 AM - Start trading with ₹25,000
- 11:00 AM - Profit reaches ₹3,125
- 🟢 Profit protection activates
- System now tracks peak profit
- Drawdown monitoring begins

---

### 3. Drawdown Threshold (Profit Protection)
**Purpose:** Prevents giving back too much profit after reaching peak

**Your Setting:** 40% of peak profit

**How it works:**
```
Peak Profit: ₹5,000 (example)
Drawdown Limit: ₹2,000 (40% of ₹5,000)
Kill Switch Triggers at: ₹3,000 profit

Current Profit drops from ₹5,000 to ₹3,000 → 🚨 KILL SWITCH ACTIVATED
```

**Example Scenario:**
- 11:00 AM - Profit reaches ₹3,125 (protection starts)
- 11:30 AM - Profit grows to ₹5,000 (new peak)
- 12:00 PM - Profit drops to ₹4,000 (₹1,000 drawdown = 20%)
- ✅ Still safe (under 40% limit)
- 12:30 PM - Profit drops to ₹2,900 (₹2,100 drawdown = 42%)
- 🚨 Kill switch activates (exceeded 40% limit)
- All positions closed
- You keep ₹2,900 profit

---

## Complete Trading Day Example

### Scenario: Successful Day with Profit Protection

```
Time    | P&L      | Capital  | Status
--------|----------|----------|----------------------------------
9:30 AM | ₹0       | ₹25,000  | 🟢 Trading started
10:00   | +₹1,000  | ₹26,000  | 🟢 Building profit
10:30   | +₹2,500  | ₹27,500  | 🟢 Approaching profit threshold
11:00   | +₹3,500  | ₹28,500  | 🟢 PROFIT PROTECTION ACTIVATED (peak: ₹3,500)
11:30   | +₹5,000  | ₹30,000  | 🟢 New peak profit (peak: ₹5,000)
12:00   | +₹4,200  | ₹29,200  | 🟡 Drawdown: ₹800 (16% - still safe)
12:30   | +₹3,500  | ₹28,500  | 🟡 Drawdown: ₹1,500 (30% - still safe)
13:00   | +₹2,900  | ₹27,900  | 🚨 Drawdown: ₹2,100 (42% - TRIGGERED!)
13:01   | +₹2,900  | ₹27,900  | 🔴 All positions closed
                                 🔴 Trading stopped
                                 ✅ Profit secured: ₹2,900
```

### Scenario: Loss Protection

```
Time    | P&L      | Capital  | Status
--------|----------|----------|----------------------------------
9:30 AM | ₹0       | ₹25,000  | 🟢 Trading started
10:00   | -₹200    | ₹24,800  | 🟡 Small loss
10:30   | -₹500    | ₹24,500  | 🟡 Loss increasing
11:00   | -₹750    | ₹24,250  | 🚨 LOSS THRESHOLD REACHED!
11:01   | -₹750    | ₹24,250  | 🔴 All positions closed
                                 🔴 Trading stopped
                                 🔴 Loss limited to ₹750
```

---

## Key Points

### Loss Threshold
- ✅ Always active from start of day
- ✅ Protects your capital from excessive losses
- ✅ Based on percentage of total capital
- ✅ Your setting: 3% = ₹750 maximum loss

### Profit Threshold
- ✅ Activates profit protection mode
- ✅ Starts tracking peak profit
- ✅ Based on percentage of capital
- ✅ Your setting: 12.5% = ₹3,125 to activate

### Drawdown Threshold
- ✅ Only active after profit threshold reached
- ✅ Protects profits from giving back too much
- ✅ Based on percentage of PEAK profit (not capital)
- ✅ Your setting: 40% of peak profit
- ✅ Example: Peak ₹10,000 → Triggers at ₹6,000

---

## Why These Settings?

### Conservative Loss Protection (3%)
- Limits daily loss to ₹750
- Preserves capital for future trading
- Prevents emotional revenge trading
- 33 days of max losses = total capital

### Reasonable Profit Target (12.5%)
- ₹3,125 profit is a solid daily target
- Activates protection at meaningful profit level
- Not too aggressive, not too conservative

### Balanced Drawdown (40%)
- Allows for normal market fluctuations
- Protects 60% of peak profit
- Example: ₹10,000 peak → Keep at least ₹6,000
- Prevents "round trip" (profit → breakeven)

---

## Telegram Commands

- `/capital` - View all thresholds
- `/risk` - Current risk metrics
- `/thresholds` - Detailed threshold info
- `/killswitch` - Manual kill switch status
- `/setcapital <amount>` - Update capital (recalculates thresholds)

---

## Making Changes

### To change capital:
```bash
# In .env file
CAPITAL=30000
```

### To change thresholds:
```bash
# In .env file
LOSS_THRESHOLD_PERCENT=5        # 5% loss limit
PROFIT_THRESHOLD_PERCENT=15     # 15% profit target
DRAWDOWN_THRESHOLD_PERCENT=30   # 30% drawdown limit
```

### Or use fixed amounts:
```bash
# In .env file (comment out percentages)
# LOSS_THRESHOLD_PERCENT=3
LOSS_THRESHOLD=1000             # Fixed ₹1,000 loss limit

# PROFIT_THRESHOLD_PERCENT=12.5
PROFIT_THRESHOLD=5000           # Fixed ₹5,000 profit target

# DRAWDOWN_THRESHOLD_PERCENT=40
DRAWDOWN_THRESHOLD=2000         # Fixed ₹2,000 drawdown limit
```

**Note:** Percentage-based is recommended as it scales with your capital!
