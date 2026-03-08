#!/usr/bin/env python3
"""Test script to verify monitoring state persistence"""

import json
import os
from advanced_killswitch import AdvancedKillSwitch

def check_status():
    """Check current status"""
    print("\n=== Current Status ===")
    
    # Check kill switch status
    if os.path.exists("killswitch_status.json"):
        with open("killswitch_status.json", 'r') as f:
            ks_data = json.load(f)
            print(f"Kill Switch: {'ACTIVE' if ks_data.get('active') else 'INACTIVE'}")
            print(f"  Reason: {ks_data.get('reason', 'N/A')}")
    else:
        print("Kill Switch: No status file")
    
    # Check monitoring status
    if os.path.exists("monitoring_status.json"):
        with open("monitoring_status.json", 'r') as f:
            mon_data = json.load(f)
            print(f"Monitoring: {'ACTIVE' if mon_data.get('monitoring') else 'INACTIVE'}")
    else:
        print("Monitoring: No status file")
    
    # Check via AdvancedKillSwitch instance
    ks = AdvancedKillSwitch()
    print(f"\nAdvancedKillSwitch instance:")
    print(f"  is_active: {ks.is_active}")
    print(f"  is_monitoring(): {ks.is_monitoring()}")

if __name__ == "__main__":
    check_status()
