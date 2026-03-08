"""
Test TOTP Configuration
Verifies your TOTP key is configured correctly
"""
import pyotp
import config
import time
from datetime import datetime

print("=" * 60)
print("TOTP CONFIGURATION TEST")
print("=" * 60)
print()

# Check if TOTP key is configured
if not config.TOTP_KEY or config.TOTP_KEY == "your_totp_key_if_automating_login":
    print("❌ TOTP KEY NOT CONFIGURED")
    print()
    print("Please follow these steps:")
    print("1. Read TOTP_MULTI_DEVICE_GUIDE.md")
    print("2. Get your TOTP secret key from Zerodha")
    print("3. Add it to .env file:")
    print("   KITE_TOTP_KEY=YOUR_SECRET_KEY_HERE")
    print()
    print("For detailed diagnostics, run:")
    print("   python diagnose_totp.py")
    print()
    exit(1)

print(f"✅ TOTP Key found in config")
print(f"   Key: {config.TOTP_KEY}")
print(f"   Length: {len(config.TOTP_KEY)} characters")
print()

# Check system time
print(f"System time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Unix timestamp: {int(time.time())}")
print()

try:
    # Generate TOTP
    totp = pyotp.TOTP(config.TOTP_KEY)
    
    print("Generating TOTP codes...")
    print()
    
    for i in range(3):
        code = totp.now()
        remaining = 30 - (int(time.time()) % 30)
        
        print(f"Code #{i+1}: {code} (valid for {remaining}s) - {datetime.now().strftime('%H:%M:%S')}")
        
        if i < 2:
            print(f"Waiting for next code...")
            time.sleep(remaining + 1)
            print()
    
    print()
    print("=" * 60)
    print("✅ TOTP GENERATION SUCCESSFUL!")
    print("=" * 60)
    print()
    print("👉 Compare the codes above with your authenticator app.")
    print("   They should match!")
    print()
    print("If codes DON'T match:")
    print("   Run: python diagnose_totp.py")
    print("   Read: TOTP_MULTI_DEVICE_GUIDE.md")
    print()
    print("If codes DO match:")
    print("   1. Test auto-login: python auto_login.py")
    print("   2. Test segment automation: python segment_automation.py")
    print()

except Exception as e:
    print()
    print("❌ TOTP GENERATION FAILED")
    print(f"Error: {e}")
    print()
    print("Possible issues:")
    print("- Invalid TOTP key format")
    print("- Key contains spaces or special characters")
    print("- Key is not base32 encoded")
    print()
    print("Solutions:")
    print("1. Run diagnostic: python diagnose_totp.py")
    print("2. Read guide: TOTP_MULTI_DEVICE_GUIDE.md")
    print("3. Get a new key from Zerodha")
    print()
    exit(1)
