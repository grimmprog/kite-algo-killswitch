# Segment Automation - Fixed Issues

## What Was Fixed

### 1. **Selenium Element Locators** ✅
**Problem**: The Selenium automation couldn't find segment toggle elements on Zerodha Console page.

**Solution**: Updated `segment_automation.py` with correct selectors based on actual Zerodha HTML:
- Uses specific checkbox IDs: `NSE_EQ`, `BSE_EQ`, `NSE_FO`, `BSE_FO`
- Clicks the label element (not checkbox directly) for Zerodha's custom switch
- Added verification after toggle
- Added screenshot and page source capture for debugging failures

### 2. **Notifier Import Errors** ✅
**Problem**: Code was using `send_telegram_message()` which doesn't exist.

**Solution**: Fixed all imports in `telegram_bot.py`:
```python
# OLD (wrong):
from notifier import send_telegram_message
send_telegram_message("message")

# NEW (correct):
from notifier import notifier
notifier.send_message("message")
```

### 3. **Continue Button** ✅
**Problem**: Segment changes weren't being saved because the "Continue" button wasn't clicked.

**Solution**: Added `click_continue_button()` method that:
- Finds and clicks the Continue button after toggling segments
- Waits for confirmation
- Handles errors gracefully

## Zerodha Console Segment Structure

The actual HTML structure uses:

```html
<input id="NSE_EQ" type="checkbox" class="su-switch">
<label for="NSE_EQ" class="su-switch-control"></label>
```

**Segment IDs:**
- `NSE_EQ` - NSE Equity
- `BSE_EQ` - BSE Equity  
- `NSE_FO` - NSE F&O (Futures & Options)
- `BSE_FO` - BSE F&O

## How to Test

### Test 1: Single Segment Toggle via Telegram

1. Start the Telegram bot:
```bash
python telegram_bot.py
```

2. In Telegram, send:
```
/segments
```

3. Click "Deactivate Segments" or "Activate Segments"

4. Select a specific segment (e.g., NSE F&O)

5. Check the response - should show success with ✅

### Test 2: Deactivate All Segments

1. In Telegram, send:
```
/segments
```

2. Click "Deactivate ALL"

3. Confirm the action

4. Should deactivate all 4 segments and show results

### Test 3: Kill Switch with Segment Deactivation

1. In Telegram, send:
```
/status
```

2. Click "⚡ Kill Switch" button

3. Confirm activation

4. Should:
   - Close any open positions
   - Deactivate F&O segment
   - Show success message

### Test 4: Standalone Script

Run the deactivate script directly:

```bash
python deactivate_all_segments.py
```

Type `yes` to confirm, then `y` for headless mode.

## Debugging

If segment toggle fails, check these files created in the `kite-algo/` directory:

1. **Screenshots**: `segment_error_*.png` or `segment_not_found_*.png`
2. **Page Source**: `segment_page_source_*.html`

These will help identify if:
- Login failed
- Page structure changed
- Element IDs changed

## Important Notes

⚠️ **12-Hour Lock**: Once a segment is deactivated on Zerodha, it cannot be reactivated for 12 hours. Test carefully!

⚠️ **Multiple Bot Instances**: Make sure only ONE Telegram bot instance is running. Multiple instances will cause conflicts.

To check for running bots:
```bash
# Windows
tasklist | findstr python

# Kill specific process
taskkill /PID <process_id> /F
```

## Files Modified

1. `segment_automation.py` - Fixed element locators, added Continue button
2. `telegram_bot.py` - Fixed notifier imports, added Continue button clicks
3. `deactivate_all_segments.py` - Added Continue button click

## Next Steps

1. **Test the fixes** - Try toggling segments via Telegram
2. **Monitor logs** - Check for any errors in console output
3. **Verify on Zerodha** - Manually check segment status at:
   https://console.zerodha.com/account/segment-activation

## Troubleshooting

### "Login failed"
- Check `.env` file has correct credentials
- Verify TOTP key is synced with Google Authenticator
- Run `python test_totp.py` to verify TOTP

### "Could not find checkbox"
- Zerodha may have changed their page structure
- Check the screenshot and page source files
- Update checkbox IDs in `segment_automation.py` if needed

### "Continue button not found"
- Page may not have loaded completely
- Increase wait time in `click_continue_button()` method
- Check if Zerodha added a confirmation dialog

### Multiple bot instances
```bash
# Windows - Find all Python processes
tasklist | findstr python

# Kill all Python processes (careful!)
taskkill /IM python.exe /F

# Or kill specific PID
taskkill /PID 12345 /F
```

## Success Indicators

✅ Telegram shows: "✅ NSE F&O DEACTIVATED"
✅ Console logs: "✅ Found checkbox: NSE_FO"
✅ Console logs: "✅ Continue button clicked"
✅ Zerodha Console shows segment as inactive

---

**Status**: All fixes applied and ready for testing
**Date**: 2026-01-31
