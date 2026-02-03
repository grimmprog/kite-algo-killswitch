import requests
import config

# Get updates from your bot
url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"

try:
    response = requests.get(url)
    data = response.json()
    
    print("=" * 50)
    print("TELEGRAM BOT UPDATES")
    print("=" * 50)
    
    if data.get('result'):
        for update in data['result']:
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                username = update['message']['chat'].get('username', 'N/A')
                first_name = update['message']['chat'].get('first_name', 'N/A')
                
                print(f"\n✅ Found Chat!")
                print(f"Chat ID: {chat_id}")
                print(f"Username: @{username}")
                print(f"Name: {first_name}")
                print(f"\nUse this in your .env file:")
                print(f"TELEGRAM_CHAT_ID={chat_id}")
                print("=" * 50)
                break
        else:
            print("\n❌ No messages found.")
            print("Please send a message to your bot first, then run this script again.")
    else:
        print("\n❌ No updates found.")
        print("Please send a message to your bot first, then run this script again.")
        
except Exception as e:
    print(f"Error: {e}")
