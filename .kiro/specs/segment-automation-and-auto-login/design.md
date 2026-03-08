# Segment Automation and Auto-Login Design

## Architecture Overview

The system consists of three main components:
1. **Auto-Login Module** (`auto_login.py`) - Handles daily authentication
2. **Segment Automation Module** (`segment_automation.py`) - Manages segment toggling
3. **Advanced Kill Switch** (`advanced_killswitch.py`) - Monitors P&L and triggers protection
4. **Telegram Bot** (`telegram_bot.py`) - Provides user interface
5. **Notifier** (`notifier.py`) - Sends simple notifications

## Component Design

### 1. Auto-Login Module

#### Class: `AutoLogin`

**Purpose:** Automates daily login to Zerodha Kite using Selenium and TOTP

**Key Methods:**
- `generate_totp()` - Generates 6-digit TOTP code from secret
- `login()` - Executes complete login flow
- `_setup_driver()` - Configures Chrome WebDriver
- `_handle_totp_field()` - Finds and fills TOTP input

**Login Flow:**
```
1. Navigate to kite.zerodha.com
2. Enter user_id from env
3. Enter password from env
4. Click login button
5. Wait for TOTP page
6. Generate TOTP code
7. Find TOTP field (type='number', id='userid')
8. Enter TOTP code
9. Handle auto-submit (Enter key + JS fallback)
10. Wait for redirect to console
11. Navigate to console.zerodha.com/account
12. Extract and save access token
13. Send success notification
```

**TOTP Field Selectors (in priority order):**
1. `input[type='number'][id='userid']`
2. `input[type='tel']`
3. `input[placeholder*='code' i]`
4. `input[id='totp']`

**Error Handling:**
- Takes screenshot on any failure
- Logs detailed error messages
- Sends Telegram notification with error details
- Cleans up browser resources

### 2. Segment Automation Module

#### Class: `ZerodhaSegmentAutomation`

**Purpose:** Automates segment activation/deactivation on Zerodha Console

**Key Methods:**
- `login_via_selenium()` - Logs in using Selenium (reuses auto-login logic)
- `activate_all_segments()` - Activates NSE_EQ, BSE_EQ, NSE_FO, BSE_FO
- `deactivate_all_segments()` - Deactivates all segments
- `deactivate_fo_only()` - Deactivates only F&O segments
- `get_segment_status()` - Returns current segment states
- `_toggle_segments()` - Core logic for toggling checkboxes
- `_handle_confirmation_modal()` - Clicks Continue in modal

**Segment Toggle Flow:**
```
1. Login via Selenium
2. Navigate to console.zerodha.com/account/segment-activation
3. Determine current tab (activate vs kill switch)
4. Click appropriate tab if needed
5. Wait for checkboxes to load
6. Toggle checkboxes: NSE_EQ, BSE_EQ, NSE_FO, BSE_FO
7. Click Continue button
8. Wait for confirmation modal
9. Click Continue in modal
10. Wait for success message
11. Verify segment status
12. Close browser
```

**Checkbox IDs:**
- `NSE_EQ` - NSE Equity
- `BSE_EQ` - BSE Equity
- `NSE_FO` - NSE Futures & Options
- `BSE_FO` - BSE Futures & Options

**Tab Navigation:**
- "Activate segment" tab - for activating segments
- "Kill switch" tab - for deactivating segments
- Detects current tab by checking active class
- Clicks tab and waits for content to load

**Modal Handling:**
- Waits for modal with class `modal-container`
- Finds Continue button: `button[type='submit'].btn-blue`
- Clicks and waits for modal to close
- Verifies success message

### 3. Advanced Kill Switch

#### Class: `AdvancedKillSwitch`

**Purpose:** Monitors P&L and automatically protects against losses

**Key Attributes:**
- `loss_threshold` - Maximum allowed loss (₹4,000)
- `profit_threshold` - Profit level to start tracking (₹5,000)
- `drawdown_threshold` - Allowed drawdown from peak (₹2,000)
- `peak_profit` - Tracks highest profit reached
- `monitoring_active` - Flag for background monitoring
- `monitoring_thread` - Daemon thread for continuous checks

**Key Methods:**
- `start_monitoring()` - Starts background P&L monitoring
- `stop_monitoring()` - Stops monitoring thread
- `is_monitoring()` - Returns monitoring status
- `_monitoring_loop()` - Main monitoring logic (runs in thread)
- `check_and_trigger()` - Evaluates trigger conditions
- `trigger()` - Executes kill switch actions

**Monitoring Logic:**
```python
while monitoring_active:
    current_pnl = get_total_pnl()
    
    # Check loss threshold
    if current_pnl < -loss_threshold:
        send_warning()
        if warning_cooldown_expired():
            trigger()
    
    # Check profit drawdown
    if current_pnl > profit_threshold:
        peak_profit = max(peak_profit, current_pnl)
    
    if peak_profit > 0:
        drawdown = peak_profit - current_pnl
        if drawdown > drawdown_threshold:
            send_warning()
            if warning_cooldown_expired():
                trigger()
    
    sleep(5)
```

**Trigger Actions:**
1. Close all open positions
2. Deactivate F&O segment via `segment_automation`
3. Send Telegram notification
4. Log trigger event
5. Stop monitoring

**Warning System:**
- Sends warning 30 seconds before trigger
- 5-minute cooldown between warnings
- Prevents notification spam

### 4. Telegram Bot

#### Main Bot (`telegram_bot.py`)

**Purpose:** Provides interactive interface for all features

**Commands:**
- `/start` - Welcome message and command list
- `/status` - Shows bot status, positions, P&L, monitoring state
- `/segments` - Interactive segment management
- `/monitor` - Start P&L monitoring
- `/stopmonitor` - Stop P&L monitoring
- `/help` - Command reference

**Callback Handlers:**
- `activate_all` - Activates all segments
- `deactivate_all` - Deactivates all segments
- `deactivate_fo` - Deactivates F&O only
- `segment_status` - Shows current segment states
- `start_monitor` - Starts monitoring
- `stop_monitor` - Stops monitoring

**Status Display:**
```
📊 Trading Bot Status

🤖 Bot: Online
📈 Positions: 2 open
💰 P&L: +₹1,234.56
📊 Monitor: 🟢 ON

[Start Monitor] [Stop Monitor]
```

**Segment Management UI:**
```
🎛️ Segment Management

Choose an action:

[Activate All] [Deactivate All]
[Deactivate F&O] [Status]
```

#### Notifier (`notifier.py`)

**Purpose:** Simple message sender for auto-login and other scripts

**Key Function:**
- `send_message(message)` - Sends text message to configured chat

**Design:**
- No polling loop (doesn't run as bot)
- Uses same bot token as main bot
- Can be called from any script
- No state management

### 5. Ubuntu Deployment

#### Setup Script (`ubuntu_setup.sh`)

**Purpose:** Automates complete Ubuntu server setup

**Actions:**
1. Update system packages
2. Install Chrome and ChromeDriver
3. Install Python 3.10+
4. Create virtual environment
5. Install Python dependencies
6. Configure cron jobs
7. Set up log rotation
8. Create backup scripts
9. Set permissions
10. Verify installation

**Cron Jobs:**
```bash
# Auto-login at 8:45 AM weekdays
45 8 * * 1-5 /path/to/venv/bin/python /path/to/auto_login.py

# Start Telegram bot at 8:50 AM weekdays
50 8 * * 1-5 /path/to/venv/bin/python /path/to/telegram_bot.py

# Rotate logs weekly
0 0 * * 0 /path/to/rotate_logs.sh

# Daily backup
0 2 * * * /path/to/backup.sh
```

## Data Flow

### Auto-Login Flow
```
Cron Job → auto_login.py → Selenium → Kite Login
                ↓
         Generate TOTP → Enter credentials
                ↓
         Save token → notifier.py → Telegram
```

### Segment Management Flow
```
Telegram → telegram_bot.py → segment_automation.py
                                      ↓
                              Selenium → Console
                                      ↓
                              Toggle segments → Confirm
                                      ↓
                              Return status → Telegram
```

### Kill Switch Flow
```
telegram_bot.py → advanced_killswitch.py → start_monitoring()
                                                  ↓
                                          Background thread
                                                  ↓
                                          Check P&L every 5s
                                                  ↓
                                          Trigger condition met?
                                                  ↓
                                          Close positions
                                                  ↓
                                          segment_automation.py
                                                  ↓
                                          Deactivate F&O
                                                  ↓
                                          Notify via Telegram
```

## Configuration

### Environment Variables (`.env`)
```bash
# Zerodha Credentials
KITE_USER_ID=AB1234
KITE_PASSWORD=your_password
KITE_TOTP_SECRET=PBRCSRYIPJFPZDNLQXZHK6FUN7JQ6KAM

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Kill Switch Thresholds
LOSS_THRESHOLD=4000
PROFIT_THRESHOLD=5000
DRAWDOWN_THRESHOLD=2000
```

## Error Handling Strategy

### Selenium Errors
- **StaleElementReferenceException**: Re-find element and retry
- **TimeoutException**: Take screenshot, log error, notify user
- **NoSuchElementException**: Try alternative selectors, log error

### Network Errors
- Retry up to 3 times with exponential backoff
- Log each attempt
- Send notification on final failure

### TOTP Errors
- Verify time synchronization
- Check TOTP secret format
- Log generated codes for debugging

## Testing Strategy

### Manual Testing
- `test_totp.py` - Verifies TOTP generation
- `test_segment_automation.py` - Tests segment toggling
- `diagnose_segment_page.py` - Inspects page elements
- `verify_bot_setup.py` - Checks bot configuration

### Integration Testing
- Test complete login flow
- Test segment activation/deactivation
- Test kill switch trigger
- Test Telegram commands

## Security Considerations

1. **Credentials**: Stored in `.env`, never in code
2. **TOTP Secret**: Encrypted at rest, loaded at runtime
3. **Browser**: Headless mode on server, no GUI exposure
4. **Tokens**: Access tokens stored with restricted permissions
5. **Logs**: Sanitized to remove sensitive data

## Performance Optimization

1. **Selenium**: Reuse browser sessions when possible
2. **Monitoring**: 5-second interval balances responsiveness and CPU usage
3. **Caching**: Cache segment status to reduce API calls
4. **Threading**: Daemon threads for background tasks

## Deployment Checklist

- [ ] Install system dependencies
- [ ] Configure `.env` file
- [ ] Set up virtual environment
- [ ] Install Python packages
- [ ] Configure cron jobs
- [ ] Test auto-login manually
- [ ] Test segment automation
- [ ] Test Telegram bot
- [ ] Verify monitoring works
- [ ] Set up log rotation
- [ ] Configure backups
- [ ] Test complete workflow

## Maintenance

### Daily
- Check auto-login logs
- Verify bot is running
- Monitor P&L tracking

### Weekly
- Review error logs
- Check disk space
- Verify backups

### Monthly
- Update dependencies
- Review and optimize code
- Test disaster recovery

## Future Enhancements

1. Web dashboard for monitoring
2. Multi-user support
3. Advanced analytics
4. Machine learning for trigger optimization
5. Mobile app integration
