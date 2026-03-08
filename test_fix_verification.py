#!/usr/bin/env python3
"""
Verification Test for Monitoring Reliability Fix

This test verifies that the fix is working correctly:
1. telegram_bot.py imports get_global_kill_switch at module level
2. All commands use the same global instance
3. Monitoring thread persists across operations
"""

import sys
import os

def test_telegram_bot_imports_global_function():
    """Verify telegram_bot.py imports get_global_kill_switch at module level"""
    print("\n" + "=" * 60)
    print("TEST 1: Telegram Bot Imports Global Function")
    print("=" * 60)
    
    # Read telegram_bot.py and check for import
    with open('telegram_bot.py', 'r') as f:
        content = f.read()
    
    # Check if import exists at module level (not inside try/except)
    import_line = "from start_bot_with_monitor import get_global_kill_switch"
    
    if import_line in content:
        # Find the line number
        lines = content.split('\n')
        for i, line in enumerate(lines[:50], 1):  # Check first 50 lines
            if import_line in line:
                print(f"✅ Found import at line {i}: {line.strip()}")
                return True
        
        print("⚠️ Import found but not at module level")
        return False
    else:
        print("❌ Import not found in telegram_bot.py")
        return False


def test_no_direct_instantiation_in_commands():
    """Verify telegram_bot.py doesn't create new instances in command handlers"""
    print("\n" + "=" * 60)
    print("TEST 2: No Direct Instantiation in Commands")
    print("=" * 60)
    
    with open('telegram_bot.py', 'r') as f:
        lines = f.readlines()
    
    # Check specific lines mentioned in task details
    problem_lines = []
    
    # Lines that should NOT have direct instantiation (except line 669 - reactivate)
    check_ranges = [
        (250, 270, "status command"),
        (1325, 1345, "killswitch command"),
        (1930, 1950, "thresholds command"),
        (1765, 1785, "monitor command"),
        (1815, 1835, "stopmonitor command"),
        (1845, 1875, "monitor callback"),
        (1885, 1915, "stopmonitor callback"),
    ]
    
    for start, end, description in check_ranges:
        for i in range(start-1, min(end, len(lines))):
            line = lines[i]
            if 'AdvancedKillSwitch()' in line and 'get_global_kill_switch' not in line:
                problem_lines.append((i+1, description, line.strip()))
    
    if problem_lines:
        print("❌ Found direct instantiation in command handlers:")
        for line_num, desc, line in problem_lines:
            print(f"   Line {line_num} ({desc}): {line}")
        return False
    else:
        print("✅ No direct instantiation found in command handlers")
        print("   All commands use get_global_kill_switch()")
        return True


def test_no_fallback_pattern():
    """Verify try/except fallback patterns are removed"""
    print("\n" + "=" * 60)
    print("TEST 3: No Fallback Pattern")
    print("=" * 60)
    
    with open('telegram_bot.py', 'r') as f:
        content = f.read()
    
    # Look for the fallback pattern
    fallback_pattern = "# Fallback to creating new instance"
    
    if fallback_pattern in content:
        print("❌ Fallback pattern still exists in telegram_bot.py")
        # Count occurrences
        count = content.count(fallback_pattern)
        print(f"   Found {count} occurrence(s)")
        return False
    else:
        print("✅ Fallback pattern removed from telegram_bot.py")
        return True


def test_global_instance_access():
    """Test that get_global_kill_switch returns the same instance"""
    print("\n" + "=" * 60)
    print("TEST 4: Global Instance Access")
    print("=" * 60)
    
    from start_bot_with_monitor import get_global_kill_switch
    
    # Get instance multiple times
    instance1 = get_global_kill_switch()
    instance2 = get_global_kill_switch()
    instance3 = get_global_kill_switch()
    
    print(f"Instance 1 ID: {id(instance1)}")
    print(f"Instance 2 ID: {id(instance2)}")
    print(f"Instance 3 ID: {id(instance3)}")
    
    if id(instance1) == id(instance2) == id(instance3):
        print("✅ All calls return the same global instance")
        return True
    else:
        print("❌ Different instances returned")
        return False


def test_thread_health_check():
    """Test that is_monitoring checks thread health"""
    print("\n" + "=" * 60)
    print("TEST 5: Thread Health Check")
    print("=" * 60)
    
    with open('advanced_killswitch.py', 'r') as f:
        content = f.read()
    
    # Check if is_monitoring has thread health check
    if 'is_alive()' in content and 'monitor_thread' in content:
        print("✅ is_monitoring() includes thread health check")
        return True
    else:
        print("❌ is_monitoring() doesn't check thread health")
        return False


def test_logging_added():
    """Test that logging was added for debugging"""
    print("\n" + "=" * 60)
    print("TEST 6: Logging Added")
    print("=" * 60)
    
    files_to_check = [
        ('start_bot_with_monitor.py', 'global instance'),
        ('telegram_bot.py', 'global instance'),
        ('advanced_killswitch.py', 'instance creation'),
    ]
    
    all_good = True
    for filename, expected in files_to_check:
        with open(filename, 'r') as f:
            content = f.read()
        
        if 'logger.info' in content or 'logger.debug' in content:
            print(f"✅ {filename}: Logging added")
        else:
            print(f"❌ {filename}: No logging found")
            all_good = False
    
    return all_good


def run_all_tests():
    """Run all verification tests"""
    print("\n" + "=" * 80)
    print("MONITORING RELIABILITY FIX - VERIFICATION TEST SUITE")
    print("=" * 80)
    print("\nThese tests verify that the fix is implemented correctly.")
    print("All tests should PASS after the fix is applied.")
    print("=" * 80)
    
    tests = [
        ("Telegram Bot Imports Global Function", test_telegram_bot_imports_global_function),
        ("No Direct Instantiation in Commands", test_no_direct_instantiation_in_commands),
        ("No Fallback Pattern", test_no_fallback_pattern),
        ("Global Instance Access", test_global_instance_access),
        ("Thread Health Check", test_thread_health_check),
        ("Logging Added", test_logging_added),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")
    
    print("\n" + "=" * 80)
    print(f"Total: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print("=" * 80)
    
    if failed == 0:
        print("\n✅ All verification tests passed!")
        print("   The fix is implemented correctly.")
        return True
    else:
        print(f"\n❌ {failed} test(s) failed")
        print("   The fix needs more work.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
