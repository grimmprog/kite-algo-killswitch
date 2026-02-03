import os
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Credentials ---
API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
REDIRECT_URL = os.getenv("KITE_REDIRECT_URL", "http://127.0.0.1:5000/")
USER_ID = os.getenv("KITE_USER_ID")
PASSWORD = os.getenv("KITE_PASSWORD")
TOTP_KEY = os.getenv("KITE_TOTP_KEY")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCESS_TOKEN_PATH = os.path.join(BASE_DIR, "access_token.txt")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# --- Strategy Constants ---
STRATEGY_NAME = "Trend Pullback Continuation"
WATCHLIST = ["NIFTY 50", "NIFTY BANK"]  # Correct trading symbols
# Note: For execution, we need the underlying index (e.g. "NIFTY 50") and the option segment symbols.

# Time Window
START_TIME = datetime.time(9, 25)
END_TIME = datetime.time(11, 15)
AUTO_SQUARE_OFF_TIME = datetime.time(15, 15)

# Risk Management
CAPITAL = int(os.getenv("CAPITAL", 40000))
MAX_DAILY_LOSS = 3000
MAX_TRADES_PER_DAY = 2
MAX_ACTIVE_TRADES = 1
CONFIDENCE_THRESHOLD = 70

# Kill Switch Thresholds (Percentage-based or Fixed)
# Percentage takes priority if set
LOSS_THRESHOLD_PERCENT = float(os.getenv("LOSS_THRESHOLD_PERCENT", 0))
LOSS_THRESHOLD = float(os.getenv("LOSS_THRESHOLD", 4000))

PROFIT_THRESHOLD_PERCENT = float(os.getenv("PROFIT_THRESHOLD_PERCENT", 0))
PROFIT_THRESHOLD = float(os.getenv("PROFIT_THRESHOLD", 5000))

DRAWDOWN_THRESHOLD_PERCENT = float(os.getenv("DRAWDOWN_THRESHOLD_PERCENT", 0))
DRAWDOWN_THRESHOLD = float(os.getenv("DRAWDOWN_THRESHOLD", 2000))

# Instrument Mapping
# You typically trade options on these indices
INDICES = {
    "NIFTY": {"symbol": "NIFTY 50", "lot_size": 65, "strike_step": 50},
    "BANKNIFTY": {"symbol": "NIFTY BANK", "lot_size": 15, "strike_step": 100}
}
