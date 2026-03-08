# Monitoring State Fix

## Problem
The Telegram bot was showing contradictory kill switch states:
- `/monitor` said "Kill switch is already active"
- `/reactivate` said "Kill switch is NOT active"
- `/monitor` again said "Kill switch is already active"

## Root Cause
The monitoring state (`self.monitoring`) was only stored in memory, not persisted to a file. When the Telegram bot created a new `AdvancedKillSwitch` instance to check status, it couldn't see the monitoring state from the actual monitor process running in `start_bot_with_monitor.py`.

## Solution
Added persistent monitoring state storage similar to kill switch status:

1. Created `monitoring_status.json` file to persist monitoring state
2. Added `load_monitoring_status()` method to read state on initialization
3. Added `save_monitoring_status()` method to persist state changes
4. Updated `start_monitoring()` to save state when starting
5. Updated `stop_monitoring()` to save state when stopping
6. Updated `_monitor_loop()` to clear state when exiting

## Files Modified
- `advanced_killswitch.py`: Added monitoring state persistence

## Testing
Run the test script to verify state persistence:
```bash
source .venv/bin/activate
python3 test_monitoring_state.py
```

## How It Works Now
1. When monitoring starts, `monitoring_status.json` is created with `{"monitoring": true}`
2. When monitoring stops (manually or automatically), the file is updated to `{"monitoring": false}`
3. Any new `AdvancedKillSwitch` instance reads this file and knows the actual monitoring state
4. Telegram bot commands now show consistent state across all instances

## Telegram Commands
- `/monitor` - Start monitoring (creates monitoring_status.json)
- `/stopmonitor` - Stop monitoring (updates monitoring_status.json)
- `/status` - Check current state (reads from both status files)
