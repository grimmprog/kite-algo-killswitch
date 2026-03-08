# Monitoring Reliability Fix - Bugfix Design

## Overview

The kill switch monitoring system fails after service restarts because the telegram_bot creates new AdvancedKillSwitch instances instead of consistently using the global instance initialized in start_bot_with_monitor.py. Additionally, the monitoring thread is a daemon thread that dies when the service restarts, leaving gaps in monitoring coverage. This bug caused a critical failure where a loss of ₹14,698 (86.46%) occurred without triggering the kill switch because monitoring had stopped after a service restart.

The fix ensures a single global AdvancedKillSwitch instance is shared across all components, makes the monitoring thread more resilient, and automatically restarts monitoring on service startup.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when telegram bot commands create new AdvancedKillSwitch instances instead of using the global instance, or when monitoring thread dies on service restart
- **Property (P)**: The desired behavior - all components use the same global AdvancedKillSwitch instance, and monitoring persists across service restarts
- **Preservation**: Existing kill switch functionality (threshold checking, position closing, segment deactivation) that must remain unchanged by the fix
- **Global Instance**: The single AdvancedKillSwitch instance created in start_bot_with_monitor.py that should be shared across all components
- **Monitoring Thread**: The background daemon thread that continuously checks P&L conditions and triggers the kill switch
- **Orphaned Instance**: A new AdvancedKillSwitch instance created by telegram_bot that is not connected to any monitoring thread
- **Service Restart**: When the systemd service or cron job restarts the bot, causing daemon threads to die

## Bug Details

### Fault Condition

The bug manifests when telegram bot commands (/monitor, /stopmonitor, /status) create new AdvancedKillSwitch instances instead of using the global instance, or when the service restarts and the daemon monitoring thread dies. The telegram_bot.py file has inconsistent patterns: some commands attempt to import get_global_kill_switch() but fall back to creating new instances if the import fails, while other commands directly create new instances without attempting to use the global one.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type TelegramCommand OR ServiceEvent
  OUTPUT: boolean
  
  RETURN (input.type == "TelegramCommand" 
         AND input.command IN ['/monitor', '/stopmonitor', '/status', '/killswitch']
         AND createsNewInstance(input))
         OR (input.type == "ServiceRestart" 
         AND monitoringThreadDies())
END FUNCTION
```

**Note**: The `/reactivate` command is excluded from this fix because it requires OTP verification from mobile/email which cannot be automated. If segments remain deactivated after a kill switch trigger, the system will notify the user to manually reactivate them.

### Examples

- **Example 1**: User sends /status command → telegram_bot creates new AdvancedKillSwitch() at line 257 → reports "monitoring: false" even though global instance has monitoring active
- **Example 2**: Service restarts at 14:41 via cron job → daemon monitoring thread dies → subsequent loss of ₹14,698 not detected because no monitoring thread is running
- **Example 3**: User sends /monitor command → telegram_bot attempts get_global_kill_switch() import at line 1773 → import fails → creates new AdvancedKillSwitch() → starts monitoring on orphaned instance
- **Example 4**: User sends /killswitch command → telegram_bot creates new AdvancedKillSwitch() at line 1334 → activates wrong instance → global instance remains inactive

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Kill switch threshold checking (loss, profit, drawdown) must continue to work exactly as before
- Position closing logic must remain unchanged
- Segment deactivation automation must remain unchanged
- Monitoring status persistence to disk must remain unchanged
- Telegram bot command responses and notifications must remain unchanged
- Manual kill switch activation/deactivation must remain unchanged

**Scope:**
All functionality that does NOT involve instance creation or monitoring thread management should be completely unaffected by this fix. This includes:
- Threshold calculation and checking logic
- Order placement for closing positions
- Segment automation integration
- Telegram notification formatting
- Status file read/write operations
- P&L calculation methods

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **Inconsistent Instance Access Pattern**: The telegram_bot.py has mixed patterns for accessing the kill switch:
   - Lines 257, 1334, 1938: Directly create new AdvancedKillSwitch() without attempting global access
   - Lines 1773, 1824, 1858, 1904: Attempt get_global_kill_switch() import but fall back to new instance
   - The import fallback pattern fails because start_bot_with_monitor is a script, not a proper module
   - Note: Line 669 (/reactivate) is excluded from this fix as reactivation requires manual OTP verification

2. **Module Import Issues**: The try/except pattern for importing get_global_kill_switch() fails silently:
   - start_bot_with_monitor.py is executed as a script (__name__ == "__main__")
   - When telegram_bot tries to import from it, the module may not be properly initialized
   - The fallback creates orphaned instances that are not connected to the monitoring thread

3. **Daemon Thread Lifecycle**: The monitoring thread is marked as daemon=True:
   - Daemon threads automatically die when the main program exits
   - Service restarts cause the daemon thread to terminate
   - No mechanism exists to automatically restart monitoring on service startup

4. **No Shared State Mechanism**: There is no proper singleton pattern or shared state mechanism:
   - Each new instance reads monitoring_status.json but creates its own thread
   - Multiple instances can exist simultaneously with different states
   - No way to ensure all components reference the same instance

## Correctness Properties

Property 1: Fault Condition - Single Global Instance Usage

_For any_ telegram bot command or service operation that needs to access the kill switch, the system SHALL use the same global AdvancedKillSwitch instance that was created at service startup, ensuring consistent monitoring state and preventing orphaned instances.

**Validates: Requirements 2.1, 2.3, 2.4, 2.5**

Property 2: Preservation - Existing Kill Switch Functionality

_For any_ kill switch operation that does NOT involve instance creation or monitoring thread management (threshold checking, position closing, segment deactivation, status persistence), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `start_bot_with_monitor.py`

**Function**: Module-level initialization

**Specific Changes**:
1. **Export Global Instance**: Make the kill_switch variable accessible as a module-level export
   - Ensure the global instance is properly initialized before telegram_bot imports it
   - Add logging to track when the global instance is created and accessed

2. **Ensure Monitoring Persistence**: Verify monitoring auto-restart logic works correctly
   - The AdvancedKillSwitch.__init__ already has auto-restart logic
   - Ensure this executes when the global instance is created

**File**: `telegram_bot.py`

**Function**: Multiple command handlers

**Specific Changes**:
1. **Standardize Instance Access**: Replace all AdvancedKillSwitch() instantiations with get_global_kill_switch() calls
   - Lines 257, 1334, 1938: Replace direct instantiation
   - Lines 1773-1779, 1824-1830, 1858-1864, 1904-1910: Remove try/except fallback pattern
   - Note: Line 669 (/reactivate) is excluded - reactivation requires manual OTP verification and cannot be automated

2. **Import Global Function at Module Level**: Add import at top of telegram_bot.py
   - Import get_global_kill_switch from start_bot_with_monitor
   - This ensures the import happens once when telegram_bot is loaded by start_bot_with_monitor

3. **Remove Fallback Instance Creation**: Eliminate all try/except patterns that create new instances
   - If get_global_kill_switch() fails, it indicates a critical initialization error
   - Should log error and fail gracefully rather than creating orphaned instances

**File**: `advanced_killswitch.py`

**Function**: `__init__` and monitoring thread management

**Specific Changes**:
1. **Improve Thread Resilience**: Add health check mechanism for monitoring thread
   - Verify thread is alive when is_monitoring() is called
   - Restart thread if it died unexpectedly

2. **Enhanced Logging**: Add detailed logging for monitoring state changes
   - Log when monitoring starts/stops
   - Log when thread dies or is restarted
   - Log instance creation with unique ID for debugging

3. **Thread Status Verification**: Improve is_monitoring() to check actual thread state
   - Current implementation only checks self.monitoring flag
   - Should also verify monitor_thread is alive
   - Return False if flag is True but thread is dead

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate service restarts and telegram bot commands, checking whether multiple instances are created and whether monitoring persists. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Multiple Instance Test**: Start bot, send /status command, verify same instance is used (will fail on unfixed code - creates new instance)
2. **Service Restart Test**: Start monitoring, simulate service restart, verify monitoring restarts automatically (will fail on unfixed code - daemon thread dies)
3. **Import Fallback Test**: Send /monitor command, verify it uses global instance not fallback (will fail on unfixed code - import fails, creates new instance)
4. **Orphaned Instance Test**: Send multiple commands, verify only one instance exists in memory (will fail on unfixed code - multiple instances created)

**Expected Counterexamples**:
- Multiple AdvancedKillSwitch instances exist simultaneously with different states
- Monitoring status reports "false" even though monitoring was started
- Service restart causes monitoring to stop permanently
- Possible causes: import failures, daemon thread lifecycle, no singleton pattern

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := handleTelegramCommand_fixed(input) OR handleServiceRestart_fixed(input)
  ASSERT usesGlobalInstance(result)
  ASSERT monitoringPersists(result)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT killSwitchBehavior_original(input) = killSwitchBehavior_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for threshold checking, position closing, and segment deactivation, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Threshold Checking Preservation**: Verify loss/profit/drawdown thresholds trigger correctly after fix
2. **Position Closing Preservation**: Verify all positions are closed correctly when kill switch activates
3. **Segment Deactivation Preservation**: Verify segments are deactivated correctly after fix
4. **Status Persistence Preservation**: Verify status files are read/written correctly after fix

### Unit Tests

- Test get_global_kill_switch() returns same instance on multiple calls
- Test telegram bot commands use global instance not new instances
- Test monitoring thread restarts automatically on service startup
- Test is_monitoring() accurately reflects thread state
- Test multiple commands in sequence use same instance

### Property-Based Tests

- Generate random sequences of telegram commands and verify single instance is used throughout
- Generate random service restart scenarios and verify monitoring always restarts
- Test that all threshold checking logic produces identical results across instances
- Test that position closing behavior is identical regardless of which instance is used

### Integration Tests

- Test full service lifecycle: start → monitor → restart → verify monitoring continues
- Test telegram bot command flow: /monitor → /status → /stopmonitor with single instance
- Test kill switch activation flow: threshold breach → close positions → deactivate segments
- Test that monitoring state persists correctly across service restarts
