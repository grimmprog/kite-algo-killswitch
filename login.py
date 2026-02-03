import logging
from kiteconnect import KiteConnect
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_access_token():
    print("--- Kite Login Tool ---")
    
    if not config.API_KEY or not config.API_SECRET:
        print("❌ Error: API_KEY or API_SECRET is missing in .env file.")
        print("Please check config.py and .env")
        return

    kite = KiteConnect(api_key=config.API_KEY)

    print(f"1. Login URL: {kite.login_url()}")
    print("2. Open this URL in your browser, login, and copy the 'request_token' from the redirected URL.")
    
    request_token = input("Paste request_token here: ").strip()
    
    if not request_token:
        print("❌ Error: Request Token cannot be empty.")
        return

    try:
        print("Generating Session...")
        data = kite.generate_session(request_token, api_secret=config.API_SECRET)
        access_token = data["access_token"]
        
        # Save to file
        with open(config.ACCESS_TOKEN_PATH, "w") as f:
            f.write(access_token)
            
        print(f"✅ Success! Access Token saved to: {config.ACCESS_TOKEN_PATH}")
        print("You can now run the main bot.")
        
    except Exception as e:
        print(f"❌ Login Failed: {e}")

if __name__ == "__main__":
    generate_access_token()
