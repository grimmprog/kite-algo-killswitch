# Segment Automation and Auto-Login Feature Requirements

## Overview
This spec documents the segment automation and auto-login features for the Kite Algo Trading Bot. The system enables automated login to Zerodha Kite, segment management via Telegram bot, and advanced kill switch monitoring with automatic segment deactivation.

## 1. Auto-Login Feature

### 1.1 TOTP-Based Authentication
**As a** trader  
**I want** the system to automatically log in to Zerodha Kite using TOTP  
**So that** I don't have to manually authenticate every day

**Acceptance Criteria:**
- System reads TOTP secret from `.env` file
- Generates valid 6-digit TOTP codes synchronized with Google Authenticator
- Handles the Zerodha login flow including TOTP submission
- Saves access token for API usage
- Sends Telegram notification on successful/failed login

### 1.2 Selenium-Based Login Flow
**As a** system administrator  
**I want** the auto-login to use Selenium for browser automation  
**So that** it can handle the complete web-based login flow

**Acceptance Criteria:**
- Navigates to Kite login page
- Enters user ID and password from environment variables
- Detects and fills TOTP field (type='number', id='userid')
- Handles auto-submit when 6th digit is entered
- Navigates to console.zerodha.com after login
- Takes screenshots on errors for debugging
- Closes browser cleanly after completion

### 1.3 Scheduled Daily Execution
**As a** trader  
**I want** auto-login to run automatically every trading day  
**So that** my bot is ready before market opens

**Acceptance Criteria:**
- Runs via cron job at 8:45 AM on weekdays
- Works on Ubuntu server environment
- Logs execution results
- Handles failures gracefully with notifications

## 2. Segment Management via Telegram

### 2.1 Interactive Segment Control
**As a** trader  
**I want** to manage trading segments via Telegram commands  
**So that** I can quickly activate/deactivate segments remotely

**Acceptance Criteria:**
- `/segments` command shows interactive buttons
- Buttons for: Activate All, Deactivate All, Deactivate F&O, Status
- Real-time feedback on segment operations
- Confirmation modals handled automatically

### 2.2 Segment Automation Backend
**As a** system  
**I want** to automate segment toggling on Zerodha Console  
**So that** segments can be controlled programmatically

**Acceptance Criteria:**
- Logs in to console.zerodha.com via Selenium
- Navigates to segment-activation page
- Toggles checkboxes: NSE_EQ, BSE_EQ, NSE_FO, BSE_FO
- Clicks Continue button and handles confirmation modal
- Verifies segment status after changes
- Returns success/failure status

### 2.3 Kill Switch Tab Navigation
**As a** system  
**I want** to navigate between "Activate segment" and "Kill switch" tabs  
**So that** I can both activate and deactivate segments

**Acceptance Criteria:**
- Detects current tab (activate vs kill switch)
- Clicks appropriate tab based on desired action
- Waits for page to load after tab switch
- Handles dynamic content loading

## 3. Advanced Kill Switch with Monitoring

### 3.1 Background P&L Monitoring
**As a** trader  
**I want** continuous monitoring of my P&L  
**So that** the system can protect me from excessive losses

**Acceptance Criteria:**
- Runs in background daemon thread
- Checks P&L every 5 seconds
- Tracks peak profit for drawdown calculation
- Does not interfere with main bot operations

### 3.2 Automatic Trigger Conditions
**As a** trader  
**I want** the kill switch to trigger automatically on specific conditions  
**So that** my losses are limited without manual intervention

**Acceptance Criteria:**
- Triggers when loss exceeds ₹4,000
- Triggers when profit drawdown occurs (peak ₹5,000 → drop ₹2,000)
- Sends warning notifications before triggering
- Implements 5-minute cooldown on warnings to prevent spam

### 3.3 Automatic Segment Deactivation
**As a** trader  
**I want** F&O segment to be automatically deactivated when kill switch triggers  
**So that** no new positions can be opened after the trigger

**Acceptance Criteria:**
- Closes all open positions first
- Deactivates F&O segment via segment automation
- Sends confirmation notification
- Logs all actions for audit trail

### 3.4 Telegram Monitor Controls
**As a** trader  
**I want** to start/stop monitoring via Telegram  
**So that** I can control the kill switch remotely

**Acceptance Criteria:**
- `/monitor` command starts background monitoring
- `/stopmonitor` command stops monitoring
- `/status` command shows monitoring state (🟢 ON / 🔴 OFF)
- Interactive buttons for Start/Stop Monitor
- Real-time status updates

## 4. Ubuntu Server Deployment

### 4.1 Automated Setup Script
**As a** system administrator  
**I want** an automated setup script for Ubuntu  
**So that** deployment is quick and error-free

**Acceptance Criteria:**
- Installs all system dependencies (Chrome, Python, etc.)
- Creates and configures virtual environment
- Sets up cron jobs for auto-login and bot startup
- Configures log rotation
- Creates backup scripts
- Provides verification steps

### 4.2 Cron Job Configuration
**As a** system administrator  
**I want** cron jobs configured for daily operations  
**So that** the system runs automatically

**Acceptance Criteria:**
- Auto-login runs at 8:45 AM weekdays
- Telegram bot starts at 8:50 AM weekdays
- Logs are rotated weekly
- Backups run daily
- All jobs log to appropriate files

## 5. Notification System

### 5.1 Lightweight Notifier
**As a** system  
**I want** a simple notification sender  
**So that** auto-login can send messages without conflicts

**Acceptance Criteria:**
- `notifier.py` only sends messages (no polling)
- Uses same bot token as main bot
- Does not interfere with `telegram_bot.py`
- Handles errors gracefully

### 5.2 Full-Featured Bot
**As a** trader  
**I want** a separate full-featured Telegram bot  
**So that** I can interact with all trading features

**Acceptance Criteria:**
- Runs independently from notifier
- Handles all commands: /status, /segments, /monitor, etc.
- Provides interactive buttons
- Maintains session state
- Can be stopped/restarted without affecting notifications

## Non-Functional Requirements

### Performance
- Login completes within 30 seconds
- Segment operations complete within 45 seconds
- P&L monitoring checks every 5 seconds with minimal CPU usage

### Reliability
- Handles network failures gracefully
- Retries failed operations (max 3 attempts)
- Takes screenshots on errors for debugging
- Logs all operations for troubleshooting

### Security
- TOTP secret stored in `.env` file (not in code)
- Credentials never logged or exposed
- Browser runs in headless mode on server
- Access tokens stored securely

### Maintainability
- Clear error messages and logging
- Comprehensive documentation
- Diagnostic scripts for troubleshooting
- Modular code structure
