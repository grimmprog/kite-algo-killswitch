# 🏗️ Deployment Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AWS EC2 Ubuntu Server                     │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Systemd Service Manager                    │ │
│  │                                                         │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │     kite-trading-bot.service                     │  │ │
│  │  │     (Auto-restart on failure)                    │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────┘ │
│                           │                                  │
│                           ▼                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │         start_bot_with_monitor.py                      │ │
│  │         (Main Application)                             │ │
│  │                                                         │ │
│  │  ┌─────────────────┐    ┌──────────────────────────┐  │ │
│  │  │  Telegram Bot   │    │  Advanced Kill Switch    │  │ │
│  │  │  (telegram_bot) │◄───┤  (Background Thread)    │  │ │
│  │  │                 │    │                          │  │ │
│  │  │  Commands:      │    │  • Check P&L every 5s   │  │ │
│  │  │  /status        │    │  • Track peak profit    │  │ │
│  │  │  /monitor       │    │  • Detect triggers      │  │ │
│  │  │  /stopmonitor   │    │  • Send warnings        │  │ │
│  │  │  /segments      │    │                          │  │ │
│  │  └─────────────────┘    └──────────────────────────┘  │ │
│  │           │                        │                    │ │
│  │           │                        │ (On Trigger)       │ │
│  │           │                        ▼                    │ │
│  │           │              ┌──────────────────────────┐  │ │
│  │           │              │  Segment Automation      │  │ │
│  │           │              │  (segment_automation)    │  │ │
│  │           │              │                          │  │ │
│  │           │              │  • Login via Selenium   │  │ │
│  │           │              │  • Navigate to Console  │  │ │
│  │           │              │  • Deactivate F&O       │  │ │
│  │           │              └──────────────────────────┘  │ │
│  │           │                        │                    │ │
│  └───────────┼────────────────────────┼────────────────────┘ │
│              │                        │                      │
│  ┌───────────▼────────────────────────▼────────────────────┐ │
│  │                  Kite Connect API                        │ │
│  │  • Get positions                                         │ │
│  │  • Get P&L                                               │ │
│  │  • Close positions                                       │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Cron Jobs (Scheduled Tasks)                │ │
│  │                                                         │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │  Auto-Login (8:45 AM Mon-Fri)                    │  │ │
│  │  │  • Login to Kite                                 │  │ │
│  │  │  • Save access token                             │  │ │
│  │  │  • Send notification                             │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    Logs Directory                       │ │
│  │  • bot_monitor.log                                     │ │
│  │  • bot_service.log                                     │ │
│  │  • bot_service_error.log                               │ │
│  │  • auto_login.log                                      │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ (Notifications)
                           ▼
                  ┌─────────────────┐
                  │  Telegram API   │
                  │                 │
                  │  • Notifications│
                  │  • Commands     │
                  │  • Status       │
                  └─────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Your Phone │
                    │  (Telegram) │
                    └─────────────┘
```

---

## Data Flow

### 1. Startup Flow
```
System Boot
    │
    ▼
Systemd starts kite-trading-bot.service
    │
    ▼
start_bot_with_monitor.py executes
    │
    ├─► Initialize Telegram Bot
    │
    ├─► Initialize Kill Switch
    │
    └─► Start Monitoring (background thread)
         │
         └─► Check P&L every 5 seconds
```

### 2. Daily Auto-Login Flow
```
8:45 AM (Mon-Fri)
    │
    ▼
Cron triggers auto_login.py
    │
    ├─► Navigate to Kite login
    │
    ├─► Enter credentials
    │
    ├─► Generate & enter TOTP
    │
    ├─► Save access token
    │
    └─► Send Telegram notification
```

### 3. Monitoring Flow
```
Every 5 seconds:
    │
    ▼
Get current P&L from Kite API
    │
    ├─► Check loss threshold (₹4,000)
    │   └─► If exceeded → Trigger warning
    │
    └─► Check profit drawdown
        │
        ├─► Track peak profit
        │
        └─► Calculate drawdown
            └─► If > ₹2,000 from peak → Trigger warning
```

### 4. Kill Switch Trigger Flow
```
Trigger Condition Met
    │
    ▼
Send Warning (30s before)
    │
    ▼
Wait 30 seconds
    │
    ▼
Close All Positions (via Kite API)
    │
    ▼
Launch Selenium Browser
    │
    ├─► Login to Console
    │
    ├─► Navigate to segment page
    │
    ├─► Click Kill Switch tab
    │
    ├─► Toggle F&O checkbox
    │
    ├─► Click Continue
    │
    └─► Confirm in modal
        │
        ▼
Send Confirmation Notification
    │
    ▼
Stop Monitoring
```

### 5. Telegram Command Flow
```
User sends /status
    │
    ▼
Telegram Bot receives command
    │
    ▼
Query Kite API for:
    ├─► Positions
    ├─► P&L
    └─► Account status
        │
        ▼
Check monitoring status
    │
    ▼
Format response with buttons
    │
    ▼
Send to user
```

---

## Component Interactions

### Telegram Bot ↔ Kill Switch
```
Telegram Bot                Kill Switch
     │                           │
     │  start_monitoring()       │
     ├──────────────────────────►│
     │                           │
     │  is_monitoring()          │
     ├──────────────────────────►│
     │◄──────────────────────────┤
     │  True/False               │
     │                           │
     │  stop_monitoring()        │
     ├──────────────────────────►│
```

### Kill Switch ↔ Segment Automation
```
Kill Switch              Segment Automation
     │                           │
     │  Trigger detected         │
     ├──────────────────────────►│
     │                           │
     │  deactivate_fno_segment() │
     │                           ├─► Login via Selenium
     │                           │
     │                           ├─► Navigate to page
     │                           │
     │                           ├─► Toggle segments
     │                           │
     │                           └─► Confirm changes
     │◄──────────────────────────┤
     │  Success/Failure          │
```

---

## File Structure on AWS

```
/home/ubuntu/kite-algo/
│
├── .env                          # Credentials (secure)
├── .venv/                        # Python virtual environment
│
├── start_bot_with_monitor.py    # Main startup script
├── telegram_bot.py               # Telegram interface
├── advanced_killswitch.py        # Kill switch logic
├── segment_automation.py         # Selenium automation
├── auto_login.py                 # Daily login script
├── config.py                     # Configuration
├── notifier.py                   # Notification helper
│
├── logs/                         # Log files
│   ├── bot_monitor.log
│   ├── bot_service.log
│   ├── bot_service_error.log
│   └── auto_login.log
│
├── aws_deploy.sh                 # Deployment script
├── check_monitor_status.sh       # Status checker
├── pre_deploy_check.sh           # Pre-flight checker
│
└── kite-trading-bot.service      # Systemd service file
    (copied to /etc/systemd/system/)
```

---

## Network Communication

```
AWS EC2 Instance
    │
    ├─► Zerodha Kite API (HTTPS)
    │   └─► Get positions, P&L, close orders
    │
    ├─► Zerodha Console (HTTPS + Selenium)
    │   └─► Login, segment management
    │
    └─► Telegram API (HTTPS)
        └─► Send/receive messages
```

---

## Security Layers

```
┌─────────────────────────────────────┐
│  AWS Security Group                 │
│  • SSH from specific IP only        │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  Ubuntu Firewall (UFW)              │
│  • Port 22 (SSH) only               │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  File Permissions                   │
│  • .env: 600 (owner only)           │
│  • Scripts: 755 (executable)        │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  Application Security               │
│  • TOTP 2FA                         │
│  • HTTPS only                       │
│  • No credentials in logs           │
└─────────────────────────────────────┘
```

---

## Monitoring & Logging

```
Application Events
    │
    ├─► bot_monitor.log
    │   • Monitoring status
    │   • P&L checks
    │   • Trigger events
    │
    ├─► bot_service.log
    │   • Service output
    │   • Startup messages
    │   • General info
    │
    ├─► bot_service_error.log
    │   • Error messages
    │   • Stack traces
    │   • Warnings
    │
    └─► auto_login.log
        • Login attempts
        • TOTP generation
        • Success/failure
```

---

## Failure Recovery

```
Application Crash
    │
    ▼
Systemd detects failure
    │
    ▼
Wait 10 seconds
    │
    ▼
Restart service
    │
    ▼
start_bot_with_monitor.py
    │
    ├─► Reinitialize components
    │
    ├─► Restart monitoring
    │
    └─► Send notification
```

---

## Resource Usage

```
Component               CPU    Memory   Disk
─────────────────────────────────────────────
Python Process          5-10%  200MB    -
Chrome (when active)    10-20% 300MB    -
Logs (daily)            -      -        10MB
Total                   15-30% 500MB    ~1GB/month
```

---

This architecture ensures:
✅ High availability (auto-restart)
✅ Continuous monitoring (24/7)
✅ Automatic protection (kill switch)
✅ Complete audit trail (logs)
✅ Remote control (Telegram)
