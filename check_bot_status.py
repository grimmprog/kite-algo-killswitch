"""
Check which Telegram bot is running
"""
import psutil
import os

def check_running_bots():
    """Check for running Python processes in kite-algo directory"""
    print("=" * 60)
    print("TELEGRAM BOT STATUS CHECK")
    print("=" * 60)
    print()
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    found_bots = []
    
    print(f"Checking for Python processes in: {current_dir}")
    print()
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and len(cmdline) > 1:
                    script_path = cmdline[1] if len(cmdline) > 1 else ''
                    
                    # Check if it's in our directory
                    if 'kite' in script_path.lower() or current_dir.lower() in script_path.lower():
                        script_name = os.path.basename(script_path)
                        found_bots.append({
                            'pid': proc.info['pid'],
                            'script': script_name,
                            'path': script_path
                        })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    if found_bots:
        print(f"✅ Found {len(found_bots)} Python process(es) in kite directory:")
        print()
        for bot in found_bots:
            print(f"  PID: {bot['pid']}")
            print(f"  Script: {bot['script']}")
            print(f"  Path: {bot['path']}")
            print()
            
            # Check if it's the right bot
            if 'telegram_bot.py' in bot['script']:
                print(f"  ✅ This is telegram_bot.py (CORRECT)")
            elif 'notifier.py' in bot['script']:
                print(f"  ⚠️  This is notifier.py (OLD - should use telegram_bot.py)")
            elif 'start_bot.py' in bot['script']:
                print(f"  ℹ️  This is start_bot.py")
            else:
                print(f"  ℹ️  Unknown bot script")
            print()
    else:
        print("❌ No Python processes found in kite directory")
        print()
        print("The Telegram bot is NOT running!")
        print()
        print("To start it:")
        print("  1. Run: restart_telegram_bot.bat")
        print("  2. Or run: python telegram_bot.py")
    
    print("=" * 60)
    print()
    
    # Check if telegram_bot.py exists
    telegram_bot_path = os.path.join(current_dir, 'telegram_bot.py')
    if os.path.exists(telegram_bot_path):
        print("✅ telegram_bot.py exists")
    else:
        print("❌ telegram_bot.py NOT FOUND!")
    
    # Check if notifier.py exists
    notifier_path = os.path.join(current_dir, 'notifier.py')
    if os.path.exists(notifier_path):
        print("✅ notifier.py exists (old bot)")
    
    print()
    print("=" * 60)
    print("RECOMMENDATIONS:")
    print("=" * 60)
    print()
    
    if not found_bots:
        print("1. Start the bot using: restart_telegram_bot.bat")
        print("2. Or manually: python telegram_bot.py")
    elif any('telegram_bot.py' in bot['script'] for bot in found_bots):
        print("✅ telegram_bot.py is running - bot should work correctly")
        print()
        print("If /segments command doesn't show buttons:")
        print("  1. Try sending /start to refresh commands")
        print("  2. Restart the bot: restart_telegram_bot.bat")
        print("  3. Check Telegram app is updated")
    else:
        print("⚠️  Wrong bot is running!")
        print()
        print("To fix:")
        print("  1. Stop current bot (Ctrl+C in terminal)")
        print("  2. Run: restart_telegram_bot.bat")
        print("  3. Or run: python telegram_bot.py")
    
    print()

if __name__ == "__main__":
    check_running_bots()
    input("\nPress Enter to exit...")
