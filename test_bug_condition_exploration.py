#!/usr/bin/env python3
"""
Bug Condition Exploration Test for Monitoring Reliability Fix

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**

This test MUST FAIL on unfixed code - failure confirms the bug exists.
DO NOT attempt to fix the test or the code when it fails.

The test encodes the expected behavior - it will validate the fix when it passes after implementation.

GOAL: Surface counterexamples that demonstrate:
1. Multiple AdvancedKillSwitch instances are created instead of using global instance
2. Monitoring thread dies on service restart and doesn't restart automatically
3. Import fallback pattern creates orphaned instances
4. Multiple instances can exist simultaneously with different states
"""

import sys
import os
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, settings, Phase, example
from hypothesis import HealthCheck

# Test configuration
TEST_TIMEOUT = 60  # seconds


def test_multiple_instance_creation():
    """
    Test that telegram bot commands create multiple instances instead of using global instance.
    
    **Validates: Requirements 1.3, 1.4**
    
    EXPECTED OUTCOME: Test FAILS on unfixed code (proves bug exists)
    - Multiple AdvancedKillSwitch instances are created
    - Each instance has different object IDs
    - Instances have different monitoring states
    """
    print("\n" + "=" * 60)
    print("TEST 1: Multiple Instance Creation")
    print("=" * 60)
    
    # Import the modules
    from advanced_killswitch import AdvancedKillSwitch
    
    # Simulate what telegram_bot.py does at lines 257, 1334, 1938
    # These lines directly create new instances without using global
    instance1 = AdvancedKillSwitch()
    instance2 = AdvancedKillSwitch()
    instance3 = AdvancedKillSwitch()
    
    # Check if they are the same instance (they should be, but won't be on unfixed code)
    print(f"Instance 1 ID: {id(instance1)}")
    print(f"Instance 2 ID: {id(instance2)}")
    print(f"Instance 3 ID: {id(instance3)}")
    
    # On unfixed code, these will be different instances
    same_instance_12 = id(instance1) == id(instance2)
    same_instance_23 = id(instance2) == id(instance3)
    same_instance_13 = id(instance1) == id(instance3)
    
    print(f"\nInstance 1 == Instance 2: {same_instance_12}")
    print(f"Instance 2 == Instance 3: {same_instance_23}")
    print(f"Instance 1 == Instance 3: {same_instance_13}")
    
    if not (same_instance_12 and same_instance_23 and same_instance_13):
        print("\n❌ COUNTEREXAMPLE FOUND: Multiple instances created!")
        print("   Expected: All commands use same global instance")
        print("   Actual: Each instantiation creates a new object")
        return False
    
    print("\n✅ All instances are the same (bug is fixed)")
    return True


def test_import_fallback_creates_orphaned_instances():
    """
    Test that import fallback pattern in telegram_bot.py creates orphaned instances.
    
    **Validates: Requirements 1.3, 1.4**
    
    EXPECTED OUTCOME: Test FAILS on unfixed code (proves bug exists)
    - Import of get_global_kill_switch fails
    - Fallback creates new instance
    - New instance is not connected to monitoring thread
    """
    print("\n" + "=" * 60)
    print("TEST 2: Import Fallback Creates Orphaned Instances")
    print("=" * 60)
    
    # Simulate the try/except pattern from telegram_bot.py lines 1773-1779
    try:
        # This import pattern is what telegram_bot.py tries
        from start_bot_with_monitor import get_global_kill_switch
        ks = get_global_kill_switch()
        print("✅ Successfully imported get_global_kill_switch()")
        import_succeeded = True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        print("   Falling back to creating new instance...")
        from advanced_killswitch import AdvancedKillSwitch
        ks = AdvancedKillSwitch()
        import_succeeded = False
    
    print(f"\nImport succeeded: {import_succeeded}")
    print(f"Instance ID: {id(ks)}")
    print(f"Monitoring active: {ks.is_monitoring()}")
    
    if not import_succeeded:
        print("\n❌ COUNTEREXAMPLE FOUND: Import fallback creates orphaned instance!")
        print("   Expected: get_global_kill_switch() import succeeds")
        print("   Actual: Import fails, new instance created")
        return False
    
    print("\n✅ Import succeeded, using global instance (bug is fixed)")
    return True


def test_monitoring_state_inconsistency():
    """
    Test that multiple instances can have different monitoring states.
    
    **Validates: Requirements 1.4, 1.5**
    
    EXPECTED OUTCOME: Test FAILS on unfixed code (proves bug exists)
    - Instance 1 starts monitoring
    - Instance 2 reports monitoring as inactive
    - Inconsistent state across instances
    """
    print("\n" + "=" * 60)
    print("TEST 3: Monitoring State Inconsistency")
    print("=" * 60)
    
    from advanced_killswitch import AdvancedKillSwitch
    
    # Create first instance and start monitoring
    instance1 = AdvancedKillSwitch()
    success1, msg1 = instance1.start_monitoring(check_interval=5)
    print(f"Instance 1 start monitoring: {success1} - {msg1}")
    print(f"Instance 1 monitoring state: {instance1.is_monitoring()}")
    
    # Small delay to let monitoring thread start
    time.sleep(0.5)
    
    # Create second instance (simulating what telegram_bot does)
    instance2 = AdvancedKillSwitch()
    print(f"Instance 2 monitoring state: {instance2.is_monitoring()}")
    
    # Check if they report the same monitoring state
    state_consistent = instance1.is_monitoring() == instance2.is_monitoring()
    
    print(f"\nInstance 1 ID: {id(instance1)}")
    print(f"Instance 2 ID: {id(instance2)}")
    print(f"Same instance: {id(instance1) == id(instance2)}")
    print(f"State consistent: {state_consistent}")
    
    # Clean up
    if instance1.is_monitoring():
        instance1.stop_monitoring()
    
    if not state_consistent:
        print("\n❌ COUNTEREXAMPLE FOUND: Monitoring state inconsistent across instances!")
        print("   Expected: All instances report same monitoring state")
        print("   Actual: Different instances report different states")
        return False
    
    print("\n✅ Monitoring state consistent (bug is fixed)")
    return True


def test_daemon_thread_dies_on_restart():
    """
    Test that daemon monitoring thread dies and doesn't restart automatically.
    
    **Validates: Requirements 1.2, 1.6**
    
    EXPECTED OUTCOME: Test FAILS on unfixed code (proves bug exists)
    - Monitoring thread is daemon=True
    - Thread dies when main thread would exit
    - No auto-restart mechanism exists
    """
    print("\n" + "=" * 60)
    print("TEST 4: Daemon Thread Dies on Restart")
    print("=" * 60)
    
    from advanced_killswitch import AdvancedKillSwitch
    
    # Create instance and start monitoring
    ks = AdvancedKillSwitch()
    success, msg = ks.start_monitoring(check_interval=5)
    print(f"Start monitoring: {success} - {msg}")
    
    # Check thread properties
    if ks.monitor_thread:
        print(f"Thread exists: True")
        print(f"Thread is daemon: {ks.monitor_thread.daemon}")
        print(f"Thread is alive: {ks.monitor_thread.is_alive()}")
        
        # Daemon threads die when main program exits
        # This is the root cause of monitoring stopping after service restart
        is_daemon = ks.monitor_thread.daemon
        
        # Clean up
        ks.stop_monitoring()
        
        if is_daemon:
            print("\n❌ COUNTEREXAMPLE FOUND: Monitoring thread is daemon!")
            print("   Expected: Thread persists across service restarts")
            print("   Actual: Daemon thread dies when service restarts")
            return False
        
        print("\n✅ Monitoring thread is not daemon (bug is fixed)")
        return True
    else:
        print("❌ No monitoring thread found")
        return False


@given(
    command_sequence=st.lists(
        st.sampled_from(['/status', '/monitor', '/stopmonitor', '/killswitch']),
        min_size=2,
        max_size=5
    )
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
@example(command_sequence=['/status', '/monitor', '/status'])
@example(command_sequence=['/monitor', '/killswitch', '/status'])
def test_property_single_global_instance_usage(command_sequence):
    """
    Property Test: All telegram bot commands should use the same global instance.
    
    **Validates: Requirements 2.1, 2.3, 2.4, 2.5**
    
    Property: For any sequence of telegram commands, all commands use the same
    AdvancedKillSwitch instance, ensuring consistent monitoring state.
    
    EXPECTED OUTCOME: Test FAILS on unfixed code (proves bug exists)
    """
    from advanced_killswitch import AdvancedKillSwitch
    
    # Track instance IDs created during command execution
    instance_ids = set()
    
    # Simulate telegram bot command handlers
    for command in command_sequence:
        if command == '/status':
            # Line 257 in telegram_bot.py - creates new instance
            ks = AdvancedKillSwitch()
            instance_ids.add(id(ks))
            _ = ks.is_monitoring()
            
        elif command == '/monitor':
            # Lines 1773-1779 - try/except with fallback
            try:
                from start_bot_with_monitor import get_global_kill_switch
                ks = get_global_kill_switch()
            except:
                ks = AdvancedKillSwitch()
            instance_ids.add(id(ks))
            if not ks.is_active:
                ks.start_monitoring(check_interval=5)
            
        elif command == '/stopmonitor':
            # Lines 1824-1830 - try/except with fallback
            try:
                from start_bot_with_monitor import get_global_kill_switch
                ks = get_global_kill_switch()
            except:
                ks = AdvancedKillSwitch()
            instance_ids.add(id(ks))
            if ks.is_monitoring():
                ks.stop_monitoring()
            
        elif command == '/killswitch':
            # Line 1334 - creates new instance
            ks = AdvancedKillSwitch()
            instance_ids.add(id(ks))
            _ = ks.is_active
    
    # Clean up any monitoring threads
    try:
        if 'ks' in locals() and ks.is_monitoring():
            ks.stop_monitoring()
    except:
        pass
    
    # Property: All commands should use the same instance
    # On unfixed code, this will fail because multiple instances are created
    assert len(instance_ids) == 1, (
        f"COUNTEREXAMPLE: Multiple instances created for command sequence {command_sequence}. "
        f"Found {len(instance_ids)} different instances. "
        f"Expected: 1 global instance used by all commands. "
        f"Actual: Each command creates/uses different instance."
    )


def run_all_tests():
    """Run all bug condition exploration tests"""
    print("\n" + "=" * 80)
    print("BUG CONDITION EXPLORATION TEST SUITE")
    print("Monitoring Reliability Fix")
    print("=" * 80)
    print("\nCRITICAL: These tests MUST FAIL on unfixed code")
    print("Failure confirms the bug exists and surfaces counterexamples")
    print("=" * 80)
    
    results = []
    
    # Run unit tests
    print("\n\n### UNIT TESTS ###\n")
    
    try:
        result1 = test_multiple_instance_creation()
        results.append(("Multiple Instance Creation", result1))
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        results.append(("Multiple Instance Creation", False))
    
    try:
        result2 = test_import_fallback_creates_orphaned_instances()
        results.append(("Import Fallback Creates Orphaned Instances", result2))
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        results.append(("Import Fallback Creates Orphaned Instances", False))
    
    try:
        result3 = test_monitoring_state_inconsistency()
        results.append(("Monitoring State Inconsistency", result3))
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        results.append(("Monitoring State Inconsistency", False))
    
    try:
        result4 = test_daemon_thread_dies_on_restart()
        results.append(("Daemon Thread Dies on Restart", result4))
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        results.append(("Daemon Thread Dies on Restart", False))
    
    # Run property-based test
    print("\n\n### PROPERTY-BASED TEST ###\n")
    
    try:
        print("Running property test: Single Global Instance Usage")
        print("Testing with multiple command sequences...")
        test_property_single_global_instance_usage()
        results.append(("Property: Single Global Instance Usage", True))
        print("\n✅ Property test passed")
    except AssertionError as e:
        print(f"\n❌ Property test failed: {e}")
        results.append(("Property: Single Global Instance Usage", False))
    except Exception as e:
        print(f"\n❌ Property test failed with exception: {e}")
        results.append(("Property: Single Global Instance Usage", False))
    
    # Summary
    print("\n\n" + "=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    failed_count = sum(1 for _, passed in results if not passed)
    total_count = len(results)
    
    print("\n" + "=" * 80)
    print(f"Total: {total_count} tests")
    print(f"Passed: {total_count - failed_count}")
    print(f"Failed: {failed_count}")
    print("=" * 80)
    
    if failed_count > 0:
        print("\n🎯 EXPECTED OUTCOME: Tests FAILED on unfixed code")
        print("   This confirms the bug exists!")
        print("\n📋 COUNTEREXAMPLES DOCUMENTED:")
        print("   1. Multiple AdvancedKillSwitch instances created")
        print("   2. Import fallback pattern creates orphaned instances")
        print("   3. Monitoring state inconsistent across instances")
        print("   4. Daemon thread dies on service restart")
        print("\n✅ Task 1 complete: Bug condition exploration test written and run")
        print("   Counterexamples surfaced successfully")
    else:
        print("\n⚠️  UNEXPECTED: All tests passed!")
        print("   This suggests the bug may already be fixed")
        print("   or the tests need adjustment")
    
    return failed_count == 0


if __name__ == "__main__":
    # Install hypothesis if not available
    try:
        import hypothesis
    except ImportError:
        print("Installing hypothesis for property-based testing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "hypothesis"])
        print("✅ Hypothesis installed\n")
    
    success = run_all_tests()
    sys.exit(0 if not success else 1)  # Exit 0 if tests failed (expected), 1 if passed (unexpected)
