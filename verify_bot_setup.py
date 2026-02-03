"""
Verify Telegram Bot Setup
Checks if everything is configured correctly
"""
import os
import sys

def check_file_exists(filepath, description):
    """Check if a file exists"""
    if os.path.exists(filepath):
        print(f"  ✅ {description}")
        return True
    else:
        print(f"  ❌ {description} - NOT FOUND")
        return False

def check_env_variables():
    """Check .env file"""
    print("\n2. Checking .env configuration...")
    
    if not os.path.exists('.env'):
        print("  ❌ .env file not found!")
        return False
    
    with open('.env', 'r') as f:
        content = f.read()
    
    checks = {
        'TELEGRAM_BOT_TOKEN': 'Telegram Bot Token',
        'TELEGRAM_CHAT_ID': 'Telegram Chat ID',
        'USER_ID': 'Zerodha User ID',
        'PASSWORD': 'Zerodha Password',
        'TOTP_KEY': 'TOTP Key'
    }
    
    all_good = True
    for key, desc in checks.items():
        if key in content and not content.split(key)[1].split('\n')[0].strip() in ['', '=', '=""', "=''", '=your_', '=<']:
            print(f"  ✅ {desc} configured")
        else:
            print(f"  ❌ {desc} not configured")
            all_good = False
    
    return all_good

def check_telegram_bot_code():
    """Check if telegram_bot.py has segments command"""
    print("\n3. Checking telegram_bot.py code...")
    
    if not os.path.exists('telegram_bot.py'):
        print("  ❌ telegram_bot.py not found!")
        return False
    
    with open('telegram_bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = [
        ('def segments_command', 'segments_command method'),
        ('CommandHandler("segments"', 'segments command handler'),
        ('def show_segment_selector', 'show_segment_selector method'),
        ('def toggle_segment', 'toggle_segment method'),
        ('InlineKeyboardButton', 'Inline keyboard support'),
    ]
    
    all_good = True
    for check_str, desc in checks:
        if check_str in content:
            print(f"  ✅ {desc} found")
        else:
            print(f"  ❌ {desc} NOT FOUND")
            all_good = False
    
    return all_good

def check_dependencies():
    """Check if required packages are installed"""
    print("\n4. Checking Python dependencies...")
    
    packages = [
        ('telegram', 'python-telegram-bot'),
        ('selenium', 'selenium'),
        ('pyotp', 'pyotp'),
        ('requests', 'requests'),
    ]
    
    all_good = True
    for package, pip_name in packages:
        try:
            __import__(package)
            print(f"  ✅ {pip_name} installed")
        except ImportError:
            print(f"  ❌ {pip_name} NOT installed")
            print(f"     Install with: pip install {pip_name}")
            all_good = False
    
    return all_good

def main():
    """Run all checks"""
    print("=" * 60)
    print("TELEGRAM BOT SETUP VERIFICATION")
    print("=" * 60)
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Check 1: Files
    print("\n1. Checking required files...")
    files_ok = all([
        check_file_exists('telegram_bot.py', 'telegram_bot.py'),
        check_file_exists('segment_automation.py', 'segment_automation.py'),
        check_file_exists('deactivate_all_segments.py', 'deactivate_all_segments.py'),
        check_file_exists('config.py', 'config.py'),
        check_file_exists('.env', '.env file'),
    ])
    
    # Check 2: Environment
    env_ok = check_env_variables()
    
    # Check 3: Code
    code_ok = check_telegram_bot_code()
    
    # Check 4: Dependencies
    deps_ok = check_dependencies()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_checks = [
        ('Required Files', files_ok),
        ('Environment Variables', env_ok),
        ('Bot Code', code_ok),
        ('Dependencies', deps_ok),
    ]
    
    for check_name, result in all_checks:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{check_name}: {status}")
    
    print("\n" + "=" * 60)
    
    if all(result for _, result in all_checks):
        print("✅ ALL CHECKS PASSED!")
        print("\nYour bot is ready to use!")
        print("\nNext steps:")
        print("  1. Run: restart_telegram_bot.bat")
        print("  2. In Telegram, send: /start")
        print("  3. Then try: /segments")
    else:
        print("❌ SOME CHECKS FAILED")
        print("\nPlease fix the issues above before running the bot.")
        print("\nCommon fixes:")
        print("  - Missing files: Make sure you're in the kite-algo directory")
        print("  - Missing .env: Copy .env.example to .env and fill in values")
        print("  - Missing dependencies: Run 'pip install -r requirements.txt'")
        print("  - Wrong bot code: Make sure telegram_bot.py is the latest version")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
