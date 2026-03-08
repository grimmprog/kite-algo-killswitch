#!/usr/bin/env python3
"""
Check the actual state of the kill switch
"""
import os
import json

print("=== Current Kill Switch State ===")

# Check kill switch status file
if os.path.exists("killswitch_status.json"):
    with open("killswitch_status.json", "r") as f:
        data = json.load(f)
        print(f"killswitch_status.json: {data}")
else:
    print("killswitch_status.json not found")

# Check kill switch status
if os.path.exists("killswitch_status.json"):
    with open("killswitch_status.json", "r") as f:
        data = json.load(f)
        print(f"\nkillswitch_status.json: {data}")
else:
    print("\nkillswitch_status.json not found")

# Check monitoring status
if os.path.exists("monitoring_status.json"):
    with open("monitoring_status.json", "r") as f:
        data = json.load(f)
        print(f"\nmonitoring_status.json: {data}")
else:
    print("\nmonitoring_status.json not found")

# Check if there are any other status files
print("\n=== Checking for other status files ===")
for f in os.listdir("."):
    if "status" in f.lower() or "kill" in f.lower() or "monitor" in f.lower():
        print(f"Found: {f}")