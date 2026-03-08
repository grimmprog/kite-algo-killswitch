"""
Register all bot commands with Telegram
This makes commands appear in the Telegram menu
"""
import requests
import config

def register_commands():
    """Register commands with Telegram BotFather"""
    
    # List of all commands with descriptions
    commands = [
        {"command": "start", "description": "🏠 Welcome & command list"},
        {"command": "help", "description": "❓ Show all commands"},
        {"command": "status", "description": "📊 Quick P&L status (with buttons)"},
        {"command": "pnl", "description": "💰 Detailed P&L breakdown"},
        {"command": "positions", "description": "📍 View open positions"},
        {"command": "pos", "description": "📍 View positions (shortcut)"},
        {"command": "close", "description": "🚨 Close all positions"},
        {"command": "closeall", "description": "🚨 Close all (alias)"},
        {"command": "killswitch", "description": "⚠️ Kill switch status & control"},
        {"command": "ks", "description": "⚠️ Kill switch (shortcut)"},
        {"command": "capital", "description": "💵 Check available capital"},
        {"command": "risk", "description": "📉 View risk metrics"},
        {"command": "scan", "description": "🔍 Manual scan for setups"},
        {"command": "consolidation", "description": "📊 Check consolidation setups"},
        {"command": "cons", "description": "📊 Consolidation (shortcut)"},
        {"command": "paper", "description": "📝 Paper trading status"},
        {"command": "papertrades", "description": "📋 Paper trade history"},
        {"command": "orders", "description": "📋 Today's orders"},
        {"command": "history", "description": "📚 Trade history"},
        {"command": "bot", "description": "🤖 Bot system status"},
        {"command": "time", "description": "🕐 Current time & market status"},
    ]
    
    # Telegram API endpoint
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/setMyCommands"
    
    # Send request
    response = requests.post(url, json={"commands": commands})
    
    if response.status_code == 200:
        print("✅ Commands registered successfully!")
        print(f"\n📝 Registered {len(commands)} commands:")
        for cmd in commands:
            print(f"   /{cmd['command']:15s} - {cmd['description']}")
        print("\n💡 Commands will now appear in Telegram menu!")
        print("   (Tap the / button in chat to see them)")
    else:
        print(f"❌ Failed to register commands: {response.text}")
    
    return response.status_code == 200


def show_command_list():
    """Display formatted command list for BotFather"""
    print("\n" + "=" * 70)
    print("COMMAND LIST FOR BOTFATHER")
    print("=" * 70)
    print("\nIf automatic registration fails, manually set commands in BotFather:")
    print("\n1. Message @BotFather on Telegram")
    print("2. Send: /setcommands")
    print("3. Select your bot")
    print("4. Copy and paste this list:\n")
    
    commands = """start - 🏠 Welcome & command list
help - ❓ Show all commands
status - 📊 Quick P&L status (with buttons)
pnl - 💰 Detailed P&L breakdown
positions - 📍 View open positions
pos - 📍 View positions (shortcut)
close - 🚨 Close all positions
closeall - 🚨 Close all (alias)
killswitch - ⚠️ Kill switch status & control
ks - ⚠️ Kill switch (shortcut)
capital - 💵 Check available capital
risk - 📉 View risk metrics
scan - 🔍 Manual scan for setups
consolidation - 📊 Check consolidation setups
cons - 📊 Consolidation (shortcut)
paper - 📝 Paper trading status
papertrades - 📋 Paper trade history
orders - 📋 Today's orders
history - 📚 Trade history
bot - 🤖 Bot system status
time - 🕐 Current time & market status"""
    
    print(commands)
    print("\n" + "=" * 70)


if __name__ == "__main__":
    print("=" * 70)
    print("TELEGRAM BOT COMMAND REGISTRATION")
    print("=" * 70)
    
    print("\n🔄 Attempting automatic registration...")
    
    try:
        success = register_commands()
        
        if not success:
            print("\n⚠️ Automatic registration failed.")
            show_command_list()
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Use manual registration instead:")
        show_command_list()
    
    print("\n✅ Done! Your bot commands are ready to use.")
    print("   Open Telegram and type / to see the command menu.")
