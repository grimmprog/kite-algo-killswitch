#!/usr/bin/env python3
"""
Test the Telegram bot state consistency
"""
import sys
import os

# Activate virtual environment
activate_script = os.path.join(os.path.dirname(__file__), '.venv', 'bin', 'activate_this.py')
if os.path.exists(activate_script):
    with open(activate_script) as f:
        exec(f.read(), {'__file__': activate_script})

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # Import and create a TradingBot instance
    from telegram_bot import TradingBot
    
    print("Creating TradingBot instance...")
    bot = TradingBot()
    
    # Mock update and context for testing
    class MockUpdate:
        class Message:
            def reply_text(self, text):
                print(f"Bot would reply: {text}")
                return text
        message = Message()
    
    class MockContext:
        pass
    
    update = MockUpdate()
    context = MockContext()
    
    print("\n=== Testing /status command ===")
    # Call status_command directly
    bot.status_command(update, context)
    
    print("\n=== Testing /monitor command ===")
    # Call monitor_command directly
    bot.monitor_command(update, context)
    
    print("\n=== Testing /reactivate command ===")
    # Call reactivate_command directly
    bot.reactivate_command(update, context)
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()