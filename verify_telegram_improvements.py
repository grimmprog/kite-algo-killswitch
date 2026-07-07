"""
Verify Telegram Bot Improvements
Checks that all improvements are in place without requiring dependencies
"""
import re

def check_file_content(filename, patterns, description):
    """Check if file contains expected patterns"""
    print(f"\n{'='*70}")
    print(f"Checking: {description}")
    print(f"File: {filename}")
    print(f"{'='*70}")
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        results = []
        for pattern_name, pattern in patterns.items():
            if re.search(pattern, content, re.MULTILINE | re.DOTALL):
                print(f"✅ {pattern_name}")
                results.append(True)
            else:
                print(f"❌ {pattern_name} - NOT FOUND")
                results.append(False)
        
        success_rate = sum(results) / len(results) * 100
        print(f"\nSuccess Rate: {success_rate:.0f}% ({sum(results)}/{len(results)})")
        
        return all(results)
        
    except FileNotFoundError:
        print(f"❌ File not found: {filename}")
        return False
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False

def main():
    print("="*70)
    print("TELEGRAM BOT IMPROVEMENTS VERIFICATION")
    print("="*70)
    
    all_checks_passed = True
    
    # Check telegram_bot.py improvements
    telegram_patterns = {
        "Import pandas": r"import pandas as pd",
        "scan_command implementation": r"def scan_command\(self.*?\):\s*.*?from scanner import market_scanner",
        "consolidation_command implementation": r"def consolidation_command\(self.*?\):\s*.*?from consolidation_breakout_scanner import ConsolidationBreakoutScanner",
        "execute_consolidation_setup method": r"def execute_consolidation_setup\(self.*?\):",
        "show_consolidation_details method": r"def show_consolidation_details\(self.*?\):",
        "cons_execute callback handler": r"elif query\.data\.startswith\('cons_execute_'\):",
        "cons_details callback handler": r"elif query\.data\.startswith\('cons_details_'\):",
        "cons_cancel callback handler": r"elif query\.data\.startswith\('cons_cancel_'\):",
    }
    
    result1 = check_file_content('telegram_bot.py', telegram_patterns, 
                                 "Telegram Bot Improvements")
    all_checks_passed = all_checks_passed and result1
    
    # Check consolidation_breakout_scanner.py improvements
    consolidation_patterns = {
        "auto_approve parameter": r"def execute_trade\(self.*?auto_approve=False\)",
        "auto_approve logic": r"if not auto_approve:",
        "Auto-approve notification": r"Use /consolidation command for interactive approval",
    }
    
    result2 = check_file_content('consolidation_breakout_scanner.py', 
                                 consolidation_patterns,
                                 "Consolidation Scanner Improvements")
    all_checks_passed = all_checks_passed and result2
    
    # Check scanner.py improvements
    scanner_patterns = {
        "Error handling in scan loop": r"try:.*?logger\.info\(f\"Checking \{symbol\}",
        "Continue on error": r"except Exception as e:.*?continue",
    }
    
    result3 = check_file_content('scanner.py', scanner_patterns,
                                "Scanner Error Handling")
    all_checks_passed = all_checks_passed and result3
    
    # Summary
    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)
    
    if all_checks_passed:
        print("\n✅ ALL IMPROVEMENTS VERIFIED!")
        print("\n🎉 Your telegram bot is ready with:")
        print("   • Interactive consolidation scanner")
        print("   • Working button handlers")
        print("   • Enhanced scan command")
        print("   • Better error handling")
        print("\n💡 Next steps:")
        print("   1. Start bot: python telegram_bot.py")
        print("   2. Test in Telegram: /consolidation")
        print("   3. Click buttons to verify responses")
    else:
        print("\n⚠️ SOME CHECKS FAILED")
        print("\nPlease review the failed checks above.")
        print("The improvements may not be fully applied.")
    
    print("\n" + "="*70)
    
    return all_checks_passed

if __name__ == "__main__":
    import os
    os.chdir('kite-algo') if os.path.exists('kite-algo') else None
    success = main()
    exit(0 if success else 1)
