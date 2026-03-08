#!/usr/bin/env python3
"""
Simulate the kill switch state issue
"""
import sys
import os

# Activate virtual environment
activate_script = os.path.join(os.path.dirname(__file__), '.venv', 'bin', 'activate_this.py')
if os.path.exists(activate_script):
    with open(activate_script) as f:
        exec(f.read(), {'__file__': activate_script})

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("=== Simulating the kill switch state issue ===\n")
    
    # Get global instance
    from start_bot_with_monitor import get_global_kill_switch
    
    print("1. Getting global kill switch instance...")
    ks1 = get_global_kill_switch()
    print(f"   Instance ID: {id(ks1)}")
    print(f"   is_active: {ks1.is_active}")
    print(f"   is_monitoring(): {ks1.is_monitoring()}")
    
    print("\n2. Simulating /monitor command...")
    # Check if kill switch is active
    if ks1.is_active:
        print("   ❌ Kill switch is already active. Cannot start monitoring.")
    else:
        print("   ✅ Kill switch is not active. Can start monitoring.")
    
    print("\n3. Simulating /reactivate command...")
    # Check if kill switch is active
    if not ks1.is_active:
        print("   ℹ️ Kill switch is not active. Trading is already enabled.")
    else:
        print("   ✅ Kill switch is active. Would deactivate it.")
    
    print("\n4. Getting global instance again...")
    ks2 = get_global_kill_switch()
    print(f"   Instance ID: {id(ks2)}")
    print(f"   Same instance as before: {id(ks1) == id(ks2)}")
    
    print("\n=== Summary ===")
    print(f"Global instance ID: {id(ks1)}")
    print(f"is_active: {ks1.is_active}")
    print(f"is_monitoring(): {ks1.is_monitoring()}")
    
    # Check file state
    import json
    if os.path.exists("killswitch_status.json"):
        with open("killswitch_status.json", "r") as f:
            data = json.load(f)
            print(f"\nFile state - active: {data.get('active')}")
            print(f"Memory state - is_active: {ks1.is_active}")
            print(f"Match: {data.get('active') == ks1.is_active}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()