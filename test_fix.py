#!/usr/bin/env python3
"""
Test the kill switch fix
"""
import sys
import os

# Activate virtual environment
activate_script = os.path.join(os.path.dirname(__file__), '.venv', 'bin', 'activate_this.py')
if os.path.exists(activate_script):
    with open(activate_script) as f:
        exec(f.read(), {'__file__': activate_script})

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from start_bot_with_monitor import get_global_kill_switch
    
    print("Testing kill switch fix...")
    
    # Get global instance
    ks1 = get_global_kill_switch()
    print(f"Instance 1 ID: {id(ks1)}")
    print(f"is_active: {ks1.is_active}")
    print(f"is_monitoring: {ks1.is_monitoring()}")
    
    # Get global instance again
    ks2 = get_global_kill_switch()
    print(f"Instance 2 ID: {id(ks2)}")
    print(f"Same instance: {ks1 is ks2}")
    
    # Check if they're the same instance
    if ks1 is ks2:
        print("✓ Same instance returned by get_global_kill_switch()")
    else:
        print("✗ Different instances!")
        
    # Check state
    print(f"\nInitial state:")
    print(f"  is_active: {ks1.is_active}")
    print(f"  is_monitoring: {ks1.is_monitoring()}")
    
    # Try to start monitoring
    print("\nTrying to start monitoring...")
    if ks1.is_active:
        print("Kill switch is active, cannot start monitoring")
    elif ks1.is_monitoring():
        print("Already monitoring")
    else:
        success, msg = ks1.start_monitoring(check_interval=5)
        print(f"Start monitoring: {success}, {msg}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()