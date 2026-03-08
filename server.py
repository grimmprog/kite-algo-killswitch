import logging
import threading
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os

# Import our bot components
import config
from main import main_loop
from scanner import market_scanner
from notifier import notifier

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

app = FastAPI(title="Kite Algo Dashboard")

# Setup Templates (we will create a simple dashboard.html)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if not os.path.exists(TEMPLATES_DIR):
    os.makedirs(TEMPLATES_DIR)

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Bot State
bot_thread = None
bot_running = False

def run_bot_wrapper():
    global bot_running
    bot_running = True
    try:
        main_loop() # This is the while True loop
    except Exception as e:
        logger.error(f"Bot execution failed: {e}")
    finally:
        bot_running = False
        logger.info("Bot Stopped.")

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "bot_running": bot_running})

@app.get("/api/status")
async def get_status():
    return {
        "running": bot_running,
        "strategy": config.STRATEGY_NAME,
        "watchlist": config.WATCHLIST,
        # We could expose more like last signal, logs, etc.
    }

@app.post("/api/start")
async def start_bot():
    global bot_thread, bot_running
    if bot_running:
        return {"status": "Already Running"}
    
    bot_thread = threading.Thread(target=run_bot_wrapper, daemon=True)
    bot_thread.start()
    return {"status": "Started"}

@app.post("/api/stop")
async def stop_bot():
    global bot_running
    # main.py loop needs to check this flag or we just let it finish current iter.
    # Currently main.py is aggressive while True. 
    # We might need to modify main.py to check a global or shared stop event.
    # For now, we can only stop if main.py handles KeyboardInterrupt or we use an Event.
    # Let's rely on notifier.stop() or similar implementation details.
    
    # Ideally we inject a stop signal.
    # Let's assume we restart the server to kill it for now, 
    # or implement a 'running' flag in main.py.
    return {"status": "Stop Signal Sent (Implementation Pending in main.py)"}

# HTML Template Creation (if file doesn't exist)
# We handle this via tool calls next.

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
