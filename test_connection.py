from connect import get_kite_session

print("Testing Kite API connection...")
kite = get_kite_session()

try:
    profile = kite.profile()
    print("\n✅ Connection successful!")
    print(f"User ID: {profile['user_id']}")
    print(f"User Name: {profile['user_name']}")
    print(f"Email: {profile['email']}")
    print(f"Broker: {profile['broker']}")
except Exception as e:
    print(f"\n❌ Connection failed: {e}")
    print("\nPlease run 'python login.py' to generate a new access token.")
