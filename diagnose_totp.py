"""
TOTP Diagnostic Tool
Compares pyotp output with your authenticator app to identify issues
"""
import pyotp
import time
import config
from datetime import datetime

def format_time_remaining(seconds):
    """Format remaining time"""
    return f"{seconds}s"

def diagnose_totp():
    """Comprehensive TOTP diagnostics"""
    print("=" * 70)
    print("TOTP DIAGNOSTIC TOOL")
    print("=" * 70)
    print()
    
    # Check if TOTP key is configured
    if not config.TOTP_KEY or config.TOTP_KEY == "your_totp_key_if_automating_login":
        print("❌ TOTP KEY NOT CONFIGURED")
        print()
        print("Please add your TOTP key to .env file:")
        print("KITE_TOTP_KEY=YOUR_SECRET_KEY_HERE")
        print()
        return False
    
    print("✅ TOTP Key found in config")
    print(f"   Key: {config.TOTP_KEY}")
    print(f"   Length: {len(config.TOTP_KEY)} characters")
    print()
    
    # Validate key format
    print("Validating key format...")
    try:
        # Check if it's valid base32
        import base64
        base64.b32decode(config.TOTP_KEY)
        print("✅ Key is valid base32 format")
    except Exception as e:
        print(f"❌ Invalid key format: {e}")
        print()
        print("TOTP keys must be base32 encoded (A-Z, 2-7)")
        print("Common issues:")
        print("  - Contains lowercase letters (should be uppercase)")
        print("  - Contains spaces or special characters")
        print("  - Contains 0, 1, 8, 9 (not valid in base32)")
        print()
        return False
    
    print()
    
    # Check system time
    print("Checking system time...")
    current_time = datetime.now()
    print(f"   System time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Unix timestamp: {int(time.time())}")
    print()
    print("⚠️  IMPORTANT: TOTP is time-based!")
    print("   If your system time is wrong, codes won't match.")
    print("   Make sure your system time is synchronized.")
    print()
    
    # Generate TOTP codes
    print("=" * 70)
    print("GENERATING TOTP CODES")
    print("=" * 70)
    print()
    print("Compare these codes with your authenticator app:")
    print()
    
    try:
        totp = pyotp.TOTP(config.TOTP_KEY)
        
        # Show current code and next 2 codes
        for i in range(3):
            code = totp.now()
            remaining = 30 - (int(time.time()) % 30)
            
            if i == 0:
                print(f"📱 CURRENT CODE: {code}")
                print(f"   Valid for: {format_time_remaining(remaining)}")
                print(f"   Time: {datetime.now().strftime('%H:%M:%S')}")
                print()
                print("👉 Open your authenticator app NOW and compare!")
                print()
                
                # Ask user to verify
                user_code = input("Enter the code from your authenticator app: ").strip()
                
                if user_code == code:
                    print()
                    print("✅ CODES MATCH! Your TOTP is working correctly!")
                    print()
                else:
                    print()
                    print("❌ CODES DON'T MATCH!")
                    print(f"   Expected: {code}")
                    print(f"   You entered: {user_code}")
                    print()
                    print("Possible issues:")
                    print("1. Wrong TOTP key in .env file")
                    print("2. System time is incorrect")
                    print("3. Authenticator app is using a different key")
                    print()
                    print("Solutions:")
                    print("1. Reset 2FA on Zerodha and get a new key")
                    print("2. Sync your system time")
                    print("3. Make sure you're looking at the right account in your app")
                    print()
                    return False
            
            if i < 2:
                print(f"Waiting for next code (in {remaining}s)...")
                time.sleep(remaining + 1)
                print()
        
        print()
        print("=" * 70)
        print("ADDITIONAL TESTS")
        print("=" * 70)
        print()
        
        # Test code generation at specific times
        print("Testing code generation consistency...")
        codes = []
        for _ in range(5):
            codes.append(totp.now())
            time.sleep(1)
        
        if len(set(codes)) == 1:
            print("✅ Code generation is consistent within 30s window")
        else:
            print("⚠️  Code changed during test (normal if crossing 30s boundary)")
        
        print()
        
        # Show provisioning URI (for QR code generation)
        print("Your TOTP provisioning URI:")
        print("(Use this to add to other devices)")
        print()
        uri = totp.provisioning_uri(
            name=config.USER_ID,
            issuer_name="Zerodha Kite"
        )
        print(uri)
        print()
        print("You can:")
        print("1. Generate QR code from this URI")
        print("2. Scan it with any authenticator app")
        print("3. Or manually enter the key:", config.TOTP_KEY)
        print()
        
        return True
        
    except Exception as e:
        print()
        print("❌ TOTP GENERATION FAILED")
        print(f"Error: {e}")
        print()
        return False

def generate_qr_code():
    """Generate QR code for easy setup on other devices"""
    try:
        import qrcode
        
        totp = pyotp.TOTP(config.TOTP_KEY)
        uri = totp.provisioning_uri(
            name=config.USER_ID,
            issuer_name="Zerodha Kite"
        )
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        
        print()
        print("QR CODE (scan with authenticator app):")
        print()
        qr.print_ascii()
        print()
        
    except ImportError:
        print()
        print("⚠️  qrcode library not installed")
        print("Install it to generate QR codes:")
        print("   pip install qrcode[pil]")
        print()

def main():
    """Main function"""
    success = diagnose_totp()
    
    if success:
        print()
        print("=" * 70)
        print("✅ DIAGNOSIS COMPLETE - TOTP IS WORKING!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Test auto-login: python auto_login.py")
        print("2. Test segment automation: python segment_automation.py")
        print("3. Test kill switch: python test_killswitch.py")
        print()
        
        # Offer to generate QR code
        choice = input("Generate QR code for other devices? (y/n): ").strip().lower()
        if choice == 'y':
            generate_qr_code()
    else:
        print()
        print("=" * 70)
        print("❌ DIAGNOSIS FAILED - TOTP NOT WORKING")
        print("=" * 70)
        print()
        print("Please follow the TOTP setup guide:")
        print("   Read: TOTP_SETUP.md")
        print()

if __name__ == "__main__":
    main()
