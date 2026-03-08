#!/usr/bin/env python3
"""
Check the current kill switch state
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from start_bot_with_monitor import get_global_kill_switch
    
    print("Getting global kill switch instance...")
    ks = get_global_kill_switch()
    
    print(f"Instance ID: {id(ks)}")
    print(f"is_active: {ks.is_active}")
    print(f"is_monitoring(): {ks.is_monitoring()}")
    
    # Check file status
    if os.path.exists("killswitch_status.json"):
        import json
        with open("killswitch_status.json", 'r') as f:
            data = json.load(f)
            print(f"\nFile status - active: {data.get('active', 'not found')}")
            print(f"File reason: {data.get('reason', 'not found')}")
    
    if os.path.exists("monitoring_status.json"):
        import json
        with open("monitoring_status.json", 'r') as f:
            data = json.load(f)
            print(f"\nMonitoring file - monitoring: {data.get('monitoring', 'not found')}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()