"""
TOTP Setup Wizard
Interactive guide to set up TOTP for automation
"""
import os
import sys
import time
from datetime import datetime

def print_header(text):
    """Print formatted header"""
    print()
    print("=" * 70)
    print(text.center(70))
    print("=" * 70)
    print()

def print_step(number, text):
    """Print step number"""
    print(f"\n{'='*70}")
    print(f"STEP {number}: {text}")
    print('='*70)

def check_env_file():
    """Check if .env file exists"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    return os.path.exists(env_path)

def read_current_totp():
    """Read current TOTP key from .env"""
    try:
        import config
        if hasattr(config, 'TOTP_KEY'):
            return config.TOTP_KEY
        return None
    except:
        return None

def main():
    """Main wizard"""
    print_header("TOTP SETUP WIZARD")
    
    print("This wizard will help you set up TOTP for automated trading.")
    print()
    print("What you'll need:")
    print("  📱 Your phone with authenticator app")
    print("  🔑 Access to Zerodha Console")
    print("  ⏱️  About 5 minutes")
    print()
    
    input("Press Enter to start...")
    
    # Step 1: Check .env file
    print_step(1, "Checking Configuration")
    
    if not check_env_file():
        print("❌ .env file not found!")
        print()
        print("Please create .env file first:")
        print("  1. Copy .env.example to .env")
        print("  2. Fill in your credentials")
        print("  3. Run this wizard again")
        print()
        return
    
    print("✅ .env file found")
    
    current_totp = read_current_totp()
    if current_totp and current_totp != "your_totp_key_if_automating_login":
        print(f"✅ TOTP key already configured: {current_totp[:4]}...{current_totp[-4:]}")
        print()
        print("Do you want to:")
        print("  1. Test current TOTP key")
        print("  2. Replace with new TOTP key")
        print("  3. Exit")
        print()
        choice = input("Select option (1/2/3): ").strip()
        
        if choice == "1":
            print()
            print("Testing current TOTP key...")
            os.system("python test_totp.py")
            return
        elif choice == "3":
            return
        # Continue to step 2 if choice is 2
    else:
        print("⚠️  TOTP key not configured yet")
    
    print()
    input("Press Enter to continue...")
    
    # Step 2: Get TOTP key from Zerodha
    print_step(2, "Get TOTP Secret Key from Zerodha")
    
    print("You need to get your TOTP secret key from Zerodha Console.")
    print()
    print("Follow these steps:")
    print()
    print("1. Open browser and go to:")
    print("   https://console.zerodha.com/")
    print()
    print("2. Login with your credentials")
    print()
    print("3. Navigate to:")
    print("   Settings → Security → Two-factor authentication")
    print()
    print("4. If 2FA is already enabled:")
    print("   - Click 'Disable' (enter current TOTP)")
    print("   - Then click 'Enable' again")
    print()
    print("5. You'll see a QR code. Click:")
    print("   'Can't scan? Enter this code manually'")
    print()
    print("6. Copy the secret key (looks like: JBSWY3DPEHPK3PXP)")
    print()
    print("7. Scan the QR code with your phone authenticator app")
    print()
    print("8. Verify it works by entering the 6-digit code")
    print()
    
    input("Press Enter when you have the secret key...")
    
    # Step 3: Enter TOTP key
    print_step(3, "Enter TOTP Secret Key")
    
    print("Paste your TOTP secret key below.")
    print()
    print("Example: JBSWY3DPEHPK3PXP")
    print()
    print("⚠️  Make sure:")
    print("  - No spaces")
    print("  - All uppercase")
    print("  - Only letters A-Z and numbers 2-7")
    print()
    
    totp_key = input("TOTP Secret Key: ").strip().upper().replace(" ", "")
    
    if not totp_key:
        print()
        print("❌ No key entered. Exiting.")
        return
    
    # Validate key format
    print()
    print("Validating key format...")
    
    try:
        import base64
        base64.b32decode(totp_key)
        print("✅ Key format is valid")
    except Exception as e:
        print(f"❌ Invalid key format: {e}")
        print()
        print("Please make sure the key is correct and try again.")
        return
    
    # Step 4: Update .env file
    print_step(4, "Updating Configuration")
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    try:
        # Read current .env
        with open(env_path, 'r') as f:
            lines = f.readlines()
        
        # Update TOTP key
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('KITE_TOTP_KEY='):
                lines[i] = f'KITE_TOTP_KEY={totp_key}\n'
                updated = True
                break
        
        # Add if not found
        if not updated:
            lines.append(f'\nKITE_TOTP_KEY={totp_key}\n')
        
        # Write back
        with open(env_path, 'w') as f:
            f.writelines(lines)
        
        print("✅ .env file updated successfully")
        print()
        
    except Exception as e:
        print(f"❌ Failed to update .env: {e}")
        print()
        print("Please manually add this line to .env:")
        print(f"KITE_TOTP_KEY={totp_key}")
        print()
        return
    
    # Step 5: Test TOTP
    print_step(5, "Testing TOTP")
    
    print("Now let's test if the TOTP key works...")
    print()
    input("Press Enter to test...")
    print()
    
    try:
        import pyotp
        totp = pyotp.TOTP(totp_key)
        
        print("Generating TOTP code...")
        print()
        
        code = totp.now()
        remaining = 30 - (int(time.time()) % 30)
        
        print(f"📱 TOTP Code: {code}")
        print(f"   Valid for: {remaining}s")
        print(f"   Time: {datetime.now().strftime('%H:%M:%S')}")
        print()
        print("👉 Check your authenticator app NOW!")
        print()
        
        user_code = input("Enter code from your authenticator app: ").strip()
        
        if user_code == code:
            print()
            print("✅ CODES MATCH! TOTP is working correctly!")
            print()
        else:
            print()
            print("❌ Codes don't match!")
            print(f"   Expected: {code}")
            print(f"   You entered: {user_code}")
            print()
            print("Possible issues:")
            print("  1. System time is wrong")
            print("  2. Wrong TOTP key")
            print("  3. Looking at wrong account in app")
            print()
            print("Try running: python fix_totp_time_sync.py")
            print()
            return
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        print()
        return
    
    # Step 6: Success!
    print_step(6, "Setup Complete!")
    
    print("🎉 TOTP is configured and working!")
    print()
    print("What you can do now:")
    print()
    print("1. Test auto-login:")
    print("   python auto_login.py")
    print()
    print("2. Test segment automation:")
    print("   python segment_automation.py")
    print()
    print("3. Enable kill switch:")
    print("   python advanced_killswitch.py")
    print()
    print("4. Add TOTP to other devices:")
    print("   Use the same key: " + totp_key)
    print("   All devices will generate matching codes!")
    print()
    print("📖 For more info, read:")
    print("   - TOTP_COMPLETE_SOLUTION.md")
    print("   - TOTP_MULTI_DEVICE_GUIDE.md")
    print()
    
    print("=" * 70)
    print("SETUP COMPLETE!".center(70))
    print("=" * 70)
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print("Setup cancelled by user")
        print()
    except Exception as e:
        print()
        print(f"❌ Error: {e}")
        print()
        print("Please report this issue or try manual setup:")
        print("Read: TOTP_COMPLETE_SOLUTION.md")
        print()
