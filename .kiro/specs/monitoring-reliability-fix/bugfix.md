# Bugfix Requirements Document

## Introduction

The kill switch monitoring thread stops working after service restarts, creating gaps in monitoring where losses aren't detected. This occurs because the telegram_bot creates new instances of AdvancedKillSwitch instead of using the global instance that was initialized with the monitoring thread in start_bot_with_monitor.py. When the service restarts, the daemon monitoring thread dies, and subsequent telegram bot commands create orphaned instances without active monitoring threads.

This bug caused a critical failure on the production system where a loss of ₹14,698 (86.46%) occurred between 14:41 and 17:50 without triggering the kill switch, because monitoring had stopped after a service restart at 14:41.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the service starts via start_bot_with_monitor.py THEN the system creates a global AdvancedKillSwitch instance and starts a daemon monitoring thread

1.2 WHEN the service restarts (e.g., via cron job) THEN the daemon monitoring thread dies and is not automatically restarted

1.3 WHEN telegram bot commands (/monitor, /stopmonitor, /status, /killswitch) are executed THEN the system attempts to import get_global_kill_switch() but falls back to creating a new AdvancedKillSwitch instance if the import fails

1.4 WHEN a new AdvancedKillSwitch instance is created by telegram bot commands THEN the system creates an orphaned instance that is not connected to any monitoring thread

1.5 WHEN monitoring status is checked via telegram bot THEN the system reports "monitoring: false" even though monitoring should be running

1.6 WHEN losses exceed thresholds during monitoring gaps THEN the kill switch does not trigger because no monitoring thread is actively checking conditions

### Expected Behavior (Correct)

2.1 WHEN the service starts via start_bot_with_monitor.py THEN the system SHALL create a single global AdvancedKillSwitch instance and start monitoring that persists across telegram bot operations

2.2 WHEN the service restarts THEN the system SHALL automatically restart the monitoring thread as part of the startup sequence

2.3 WHEN telegram bot commands (/monitor, /stopmonitor, /status, /killswitch) are executed THEN the system SHALL always use the same global AdvancedKillSwitch instance that was created at startup

2.4 WHEN monitoring is started at service startup THEN the system SHALL ensure the monitoring thread remains active and connected to the global instance

2.5 WHEN monitoring status is checked via telegram bot THEN the system SHALL accurately report the monitoring state of the global instance

2.6 WHEN losses exceed thresholds at any time after service start THEN the kill switch SHALL trigger immediately because monitoring is continuously active

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the /monitor command is sent and monitoring is not active THEN the system SHALL CONTINUE TO start monitoring with a 5-second check interval

3.2 WHEN the /stopmonitor command is sent and monitoring is active THEN the system SHALL CONTINUE TO stop the monitoring thread gracefully

3.3 WHEN the kill switch is already active THEN the system SHALL CONTINUE TO prevent monitoring from starting

3.4 WHEN monitoring detects a threshold breach THEN the system SHALL CONTINUE TO close all positions, deactivate F&O segments, and stop monitoring

3.5 WHEN monitoring status is persisted to disk THEN the system SHALL CONTINUE TO save and load the monitoring state correctly

3.6 WHEN the monitoring thread encounters an error THEN the system SHALL CONTINUE TO log the error and stop monitoring gracefully
