#!/usr/bin/env python3
"""
Debug the kill switch state issue
"""
import os
import json
import sys

print("=== Debugging Kill Switch State Issue ===")

# Check the current state of the files
print("\n1. Current file states:")
if os.path.exists("killswitch_status.json"):
    with open("killswitch_status.json", 'r') as f:
        content = f.read()
        print(f"killswitch_status.json content:\n{content}")
        try:
            data = json.loads(content)
            print(f"Parsed: active={data.get('active')}, reason={data.get('reason')}")
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print("File might be corrupted!")

if os.path.exists("monitoring_status.json"):
    with open("monitoring_status.json", 'r') as f:
        content = f.read()
        print(f"\nmonitoring_status.json content:\n{content}")
        try:
            data = json.loads(content)
            print(f"Parsed: monitoring={data.get('monitoring')}")
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")

print("\n2. Simulating what happens:")
print("   - When AdvancedKillSwitch is created, it calls load_status()")
print("   - load_status() reads killswitch_status.json")
print("   - If file says active=true, is_active is set to True")
print("   - If file says active=false, is_active is set to False")

print("\n3. The issue:")
print("   File shows active=true (kill switch is active)")
print("   But /reactivate said 'Kill switch is not active'")
print("\n   Possible reasons:")
print("   a) The file was corrupted when /reactivate was called")
print("   b) There's a bug in load_status() or save_status()")
print("   c) Multiple instances with different states")
print("   d) Race condition or timing issue")

print("\n4. Let's check if the file is valid JSON:")
try:
    with open("killswitch_status.json", 'r') as f:
        data = json.load(f)
    print("   ✅ killswitch_status.json is valid JSON")
except Exception as e:
    print(f"   ❌ killswitch_status.json is NOT valid JSON: {e}")

print("\n5. Recommendation:")
print("   Since the file shows active=true, the kill switch IS active.")
print("   To fix the issue:")
print("   a) Run /reactivate command again to deactivate it")
print("   b) Or manually set active=false in the file")
print("   c) Then try /monitor again")