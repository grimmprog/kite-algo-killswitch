"""
Fix TOTP Time Synchronization Issues
Checks and fixes system time to ensure TOTP codes match
"""
import time
import platform
import subprocess
from datetime import datetime
import pyotp
import config

def check_system_time():
    """Check if system time is correct"""
    print("=" * 60)
    print("SYSTEM TIME CHECK")
    print("=" * 60)
    print()
    
    current_time = datetime.now()
    print(f"System time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Unix timestamp: {int(time.time())}")
    print()
    
    # Check time zone
    import time as time_module
    if time_module.daylight:
        print(f"Time zone: {time_module.tzname[1]} (DST)")
    else:
        print(f"Time zone: {time_module.tzname[0]}")
    print()
    
    return True

def sync_time_windows():
    """Sync time on Windows"""
    print("Syncing time on Windows...")
    print()
    
    try:
        # Stop Windows Time service
        print("Stopping Windows Time service...")
        subprocess.run(["net", "stop", "w32time"], capture_output=True)
        
        # Start Windows Time service
        print("Starting Windows Time service...")
        subprocess.run(["net", "start", "w32time"], capture_output=True)
        
        # Resync time
        print("Resyncing time...")
        result = subprocess.run(["w32tm", "/resync"], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Time synced successfully!")
            print(result.stdout)
        else:
            print("⚠️  Time sync may have failed")
            print(result.stderr)
        
        print()
        return True
        
    except Exception as e:
        print(f"❌ Failed to sync time: {e}")
        print()
        print("Manual steps:")
        print("1. Open Settings → Time & Language → Date & Time")
        print("2. Turn ON 'Set time automatically'")
        print("3. Click 'Sync now'")
        print()
        return False

def sync_time_linux():
    """Sync time on Linux"""
    print("Syncing time on Linux...")
    print()
    
    try:
        # Try using timedatectl (systemd)
        print("Checking timedatectl...")
        result = subprocess.run(["timedatectl", "status"], capture_output=True, text=True)
        print(result.stdout)
        print()
        
        # Enable NTP
        print("Enabling NTP synchronization...")
        subprocess.run(["sudo", "timedatectl", "set-ntp", "true"], capture_output=True)
        
        # Try ntpdate if available
        print("Syncing with NTP server...")
        result = subprocess.run(
            ["sudo", "ntpdate", "-s", "time.nist.gov"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Time synced successfully!")
        else:
            # Try with chrony
            print("Trying chrony...")
            subprocess.run(["sudo", "chronyc", "makestep"], capture_output=True)
            print("✅ Time sync attempted")
        
        print()
        return True
        
    except Exception as e:
        print(f"⚠️  Automatic sync failed: {e}")
        print()
        print("Manual steps:")
        print("1. Install NTP: sudo apt-get install ntp")
        print("2. Sync time: sudo ntpdate -s time.nist.gov")
        print("3. Or use: sudo timedatectl set-ntp true")
        print()
        return False

def test_totp_after_sync():
    """Test TOTP generation after time sync"""
    print("=" * 60)
    print("TESTING TOTP AFTER TIME SYNC")
    print("=" * 60)
    print()
    
    if not config.TOTP_KEY or config.TOTP_KEY == "your_totp_key_if_automating_login":
        print("❌ TOTP key not configured")
        return False
    
    try:
        totp = pyotp.TOTP(config.TOTP_KEY)
        
        print("Generating TOTP codes...")
        print()
        
        for i in range(2):
            code = totp.now()
            remaining = 30 - (int(time.time()) % 30)
            
            print(f"Code: {code} (valid for {remaining}s)")
            print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
            print()
            
            if i == 0:
                print("👉 Compare with your authenticator app NOW!")
                user_input = input("Does it match? (y/n): ").strip().lower()
                
                if user_input == 'y':
                    print()
                    print("✅ SUCCESS! TOTP is working correctly!")
                    print()
                    return True
                else:
                    print()
                    print("Waiting for next code...")
                    time.sleep(remaining + 1)
        
        print("If codes still don't match, the issue is not time-related.")
        print("Run: python diagnose_totp.py")
        print()
        return False
        
    except Exception as e:
        print(f"❌ TOTP test failed: {e}")
        return False

def main():
    """Main function"""
    print()
    print("=" * 60)
    print("TOTP TIME SYNCHRONIZATION FIX")
    print("=" * 60)
    print()
    print("This script will:")
    print("1. Check your system time")
    print("2. Sync time with internet time servers")
    print("3. Test TOTP generation")
    print()
    
    # Check system time
    check_system_time()
    
    # Detect OS and sync time
    os_type = platform.system()
    
    if os_type == "Windows":
        print("Detected: Windows")
        print()
        print("⚠️  This requires administrator privileges!")
        print()
        input("Press Enter to continue (or Ctrl+C to cancel)...")
        print()
        sync_time_windows()
        
    elif os_type == "Linux":
        print("Detected: Linux")
        print()
        print("⚠️  This requires sudo privileges!")
        print()
        input("Press Enter to continue (or Ctrl+C to cancel)...")
        print()
        sync_time_linux()
        
    else:
        print(f"Detected: {os_type}")
        print("Automatic time sync not supported for this OS")
        print("Please sync time manually")
        print()
    
    # Wait a moment for time to sync
    print("Waiting for time sync to complete...")
    time.sleep(3)
    print()
    
    # Check time again
    check_system_time()
    
    # Test TOTP
    success = test_totp_after_sync()
    
    if success:
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print()
        print("Your TOTP is now working correctly.")
        print()
        print("Next steps:")
        print("1. Test auto-login: python auto_login.py")
        print("2. Test segment automation: python segment_automation.py")
        print()
    else:
        print("=" * 60)
        print("❌ TOTP STILL NOT WORKING")
        print("=" * 60)
        print()
        print("The issue is not time-related.")
        print()
        print("Next steps:")
        print("1. Run full diagnostic: python diagnose_totp.py")
        print("2. Read guide: TOTP_MULTI_DEVICE_GUIDE.md")
        print("3. Consider resetting 2FA on Zerodha")
        print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("Cancelled by user")
        print()
