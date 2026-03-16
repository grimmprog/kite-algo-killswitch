#!/usr/bin/env python3
"""
Test to reproduce the kill switch state inconsistency issue
"""
import sys
import os
import json

# Mock the missing modules to avoid import errors
class MockKiteConnect:
    def __init__(self, *args, **kwargs):
        pass

class MockModule:
    pass

# Mock the modules that are missing
sys.modules['kiteconnect'] = MockModule()
sys.modules['kiteconnect'].KiteConnect = MockKiteConnect

# Now we can import our modules
try:
    # First, let's check the current state of the files
    print("=== Current File State ===")
    if os.path.exists("killswitch_status.json"):
        with open("killswitch_status.json", 'r') as f:
            data = json.load(f)
            print(f"killswitch_status.json: active={data.get('active')}, reason={data.get('reason')}")
    
    if os.path.exists("monitoring_status.json"):
        with open("monitoring_status.json", 'r') as f:
            data = json.load(f)
            print(f"monitoring_status.json: monitoring={data.get('monitoring')}")
    
    print("\n=== Simulating Telegram Commands ===")
    
    # Simulate what happens when /status is called
    print("\n1. Simulating /status command:")
    print("   - Calls get_global_kill_switch()")
    print("   - Checks ks.is_monitoring()")
    print("   - If ks.is_active is True, monitoring won't start")
    
    # Simulate what happens when /reactivate is called  
    print("\n2. Simulating /reactivate command:")
    print("   - Calls get_global_kill_switch()")
    print("   - Checks ks.is_active")
    print("   - If False: 'Kill switch is not active'")
    print("   - If True: deactivates and saves status")
    
    # Simulate what happens when /monitor is called
    print("\n3. Simulating /monitor command:")
    print("   - Calls get_global_kill_switch()")
    print("   - Checks ks.is_active")
    print("   - If True: 'Kill switch is already active. Cannot start monitoring.'")
    print("   - Checks ks.is_monitoring()")
    print("   - If False: starts monitoring")
    
    print("\n=== Issue Analysis ===")
    print("Based on the Telegram conversation:")
    print("1. /status → shows kill switch is already active")
    print("2. /reactivate → says kill switch is not active") 
    print("3. /monitor → says kill switch is already active")
    print("\nThis suggests:")
    print("- The global instance has is_active = True (in memory)")
    print("- The file says active = false (on disk)")
    print("- /reactivate checks is_active (True) and deactivates it")
    print("- But /monitor also checks is_active (True) and refuses to start")
    
    print("\n=== Possible Solutions ===")
    print("1. Check if the save_status() method is working correctly")
    print("2. Check if there are multiple instances being created")
    print("3. Check if the file corruption we fixed earlier was causing issues")
    print("4. Add more logging to track state changes")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()