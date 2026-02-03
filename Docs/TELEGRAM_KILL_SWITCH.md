# Telegram Kill Switch - Quick Reference

## Manual Kill Switch Button Added! ⚡

You now have **3 ways** to activate the kill switch via Telegram:

---

## Method 1: Quick Status Button (NEW! ⭐)

**Fastest way - 2 clicks!**

```
1. Send: /status
2. Click: ⚡ Kill Switch button
3. Confirm: ⚡ YES, ACTIVATE
```

**What you see:**
```
🟢 QUICK STATUS

Day P&L: ₹1,234.56 (+3.09%)
Open Positions: 2
Time: 14:23:45

[📊 Detailed P&L] [📍 Positions]
[🚨 Close All] [⚡ Kill Switch]  ← NEW BUTTON!
```

---

## Method 2: Kill Switch Command

**Direct command:**

```
1. Send: /killswitch (or /ks)
2. Click: ⚡ ACTIVATE KILL SWITCH
3. Confirm
```

**What you see:**
```
🚨 KILL SWITCH STATUS

🟢 SAFE
P&L: ₹1,234.56

Open Positions: 2

[⚡ ACTIVATE KILL SWITCH]
```

---

## Method 3: Close All Command

**Close positions only (no segment deactivation):**

```
1. Send: /close (or /closeall)
2. Confirm: ✅ YES, CLOSE ALL
```

---

## What Happens When Kill Switch Activates

### Step 1: Close All Positions ✅
```
⚡ Activating Kill Switch...

✅ Positions Closed: 2/2
```

### Step 2: Deactivate F&O Segment 🔒
```
🔄 Attempting to deactivate F&O segment...
✅ F&O segment deactivated successfully!
🔒 No new F&O trades can be placed.
```

### Step 3: Final Report 📊
```
⚡ KILL SWITCH ACTIVATED

✅ Positions Closed: 2/2

💰 Final Day P&L: ₹1,234.56
🕐 Time: 14:23:45

⚠️ All positions have been closed.
✅ F&O segment deactivated successfully!
🔒 No new F&O trades can be placed.
```

---

## Kill Switch vs Close All

### ⚡ Kill Switch (Full Protection)
- ✅ Closes all positions
- ✅ Deactivates F&O segment (if TOTP configured)
- ✅ Prevents new trades
- ✅ Sends notifications
- **Use when:** You want complete shutdown

### 🚨 Close All (Positions Only)
- ✅ Closes all positions
- ❌ Does NOT deactivate segment
- ❌ Bot can still trade
- ✅ Sends notifications
- **Use when:** You just want to exit current positions

---

## Requirements for Auto Segment Deactivation

For the kill switch to automatically deactivate F&O segment:

✅ **TOTP must be configured** in `.env`:
```env
KITE_TOTP_KEY=YOUR_SECRET_KEY_HERE
```

✅ **TOTP must be synced** with Google Authenticator

✅ **Test it works:**
```bash
python diagnose_totp.py
```

**If TOTP is NOT configured:**
- Kill switch will still close all positions ✅
- But you'll need to manually deactivate segment ⚠️
- You'll get a link to do it manually

---

## Confirmation Flow

### Kill Switch Confirmation
```
⚡ ACTIVATE KILL SWITCH?

⚠️ This will:
1. Close all 2 position(s)
2. Stop bot from trading
3. Deactivate F&O segment (if configured)

Current Day P&L: ₹1,234.56

⚠️ This action cannot be undone!

[⚡ YES, ACTIVATE] [❌ CANCEL]
```

**Safety features:**
- ✅ Shows current P&L
- ✅ Shows number of positions
- ✅ Requires explicit confirmation
- ✅ Cannot be undone warning
- ✅ Cancel option

---

## Status Button Layout

```
/status command shows:

┌─────────────────────────────────┐
│  🟢 QUICK STATUS                │
│                                 │
│  Day P&L: ₹1,234.56 (+3.09%)   │
│  Open Positions: 2              │
│  Time: 14:23:45                 │
│                                 │
│  [📊 Detailed] [📍 Positions]   │
│  [🚨 Close All] [⚡ Kill Switch] │
└─────────────────────────────────┘
```

**4 quick action buttons:**
1. 📊 Detailed P&L - Full breakdown
2. 📍 Positions - List all positions
3. 🚨 Close All - Close positions only
4. ⚡ Kill Switch - Full shutdown (NEW!)

---

## Quick Commands Reference

```
/status         - Quick status with buttons (includes Kill Switch!)
/killswitch     - Kill switch status & activation
/ks             - Shortcut for /killswitch
/close          - Close all positions (no segment deactivation)
/closeall       - Alias for /close
/pnl            - Detailed P&L breakdown
/positions      - List open positions
/pos            - Shortcut for /positions
```

---

## Testing Kill Switch

### Test Without Real Positions

1. **Check status:**
   ```
   /status
   ```

2. **Click Kill Switch button**
   - Should show: "📭 No positions to close"

3. **Test with paper trading:**
   ```bash
   python paper_trading.py
   ```
   - Open a paper position
   - Try kill switch
   - Verify it works

### Test With Real Positions (Carefully!)

1. **Open 1 small position** (1 lot)

2. **Test kill switch:**
   ```
   /status → ⚡ Kill Switch → Confirm
   ```

3. **Verify:**
   - Position closed ✅
   - F&O segment deactivated ✅
   - Notification received ✅

---

## Troubleshooting

### "TOTP not configured"

**Problem:** Kill switch closes positions but can't deactivate segment

**Solution:**
```bash
python diagnose_totp.py
```
Follow the guide to configure TOTP.

### "Segment deactivation failed"

**Problem:** TOTP configured but segment deactivation fails

**Solutions:**
1. Check TOTP is working: `python test_totp.py`
2. Test segment automation: `python segment_automation.py`
3. Check credentials in `.env`
4. Try manual deactivation (link provided in message)

### "Failed to close position"

**Problem:** Some positions didn't close

**Solutions:**
1. Check position details: `/positions`
2. Try manual close on Kite
3. Check order status: `/orders`
4. Check logs for errors

---

## Manual Segment Deactivation

If auto-deactivation fails, you'll get this link:

```
https://console.zerodha.com/account/segment-activation
```

**Steps:**
1. Click the link
2. Login to Zerodha Console
3. Find "NFO" (F&O) segment
4. Toggle to deactivate
5. Confirm

**Takes 30 seconds manually.**

---

## Safety Features

✅ **Double confirmation** - Can't activate by accident  
✅ **Shows current P&L** - Know what you're closing  
✅ **Shows position count** - Verify before closing  
✅ **Cannot undo warning** - Clear consequences  
✅ **Cancel option** - Easy to back out  
✅ **Detailed logging** - Track all actions  
✅ **Notifications** - Get confirmation message  
✅ **Error handling** - Graceful failures  

---

## Best Practices

### When to Use Kill Switch

✅ **Max loss reached** (₹4,000)  
✅ **Profit protection** (₹5,000 → drops ₹2,000)  
✅ **Market volatility** - Unexpected moves  
✅ **Technical issues** - Bot malfunctioning  
✅ **End of day** - Close everything  
✅ **Emergency** - Need to stop immediately  

### When to Use Close All

✅ **Just exit positions** - Keep segment active  
✅ **Rebalance** - Close and re-enter  
✅ **Take profit** - Lock in gains  
✅ **Reduce exposure** - Lower risk  

---

## Summary

**New Feature:** ⚡ Kill Switch button on `/status` command

**How to use:**
1. `/status` → Click ⚡ Kill Switch
2. Confirm
3. Done!

**What it does:**
- Closes all positions
- Deactivates F&O segment (if TOTP configured)
- Sends notifications
- Provides detailed report

**Requirements:**
- TOTP configured for segment deactivation
- Otherwise, manual segment deactivation needed

**Safety:**
- Double confirmation required
- Shows current status before activation
- Cannot be undone warning
- Easy cancel option

---

**Try it now:**

```
/status
```

Then click the ⚡ Kill Switch button! 🚀
