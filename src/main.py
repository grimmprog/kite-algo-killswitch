"""FastAPI application entry point for the Multi-User Web Trading Platform.

Initializes the app with:
- CORS middleware (Requirement 2.4.11)
- Request ID middleware (Requirement 4.2.10)
- Request logging middleware (Requirement 2.3.7)
- Exception handlers (Requirement 4.2.3)
- Admin router
- Redis PubSub → WebSocket relay (Requirement 11.2-11.5)

Run with: uvicorn src.main:app --reload
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env file before any other imports that use env vars
load_dotenv()

# --- 8.5.1: Configure logging (must run before app creation) ---
from src.api.logging_config import configure_logging

configure_logging()

from src.admin.router import admin_router
from src.api.error_handlers import register_error_handlers
from src.api.middleware import RequestIDMiddleware, RequestLoggingMiddleware
from src.api.routers.auth import router as auth_router
from src.api.routers.dashboard import router as dashboard_router
from src.api.routers.trading import router as trading_router
from src.api.routers.killswitch import router as killswitch_router
from src.api.routers.signals import router as signals_router
from src.api.routers.scanner import router as scanner_router
from src.api.routers.index_analyzer import router as index_analyzer_router
from src.api.routers.settings import router as settings_router
from src.api.routers.position_monitor import router as position_monitor_router
from src.api.routers.paper_trading import router as paper_trading_router
from src.api.routers.journal import router as journal_router
from src.api.routers.charts import router as charts_router
from src.api.routers.status import router as status_router
from src.api.routers.ai import router as ai_router
from src.api.routers.broker_settings import router as broker_settings_router
from src.api.routers.live_market import router as live_market_router
from src.api.routers.market_data_settings import router as market_data_settings_router
from src.api.routers.account import router as account_router
from src.api.routers.dhan_account import router as dhan_account_router
from src.api.routers.instruments import router as instruments_router
from src.api.routers.advanced_orders import router as advanced_orders_router
from src.api.websocket import socket_app
from src.api.websocket_relay import start_pubsub_relay, stop_pubsub_relay


# --- Lifespan: start/stop background tasks ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: start Redis PubSub relay on startup, stop on shutdown."""
    await start_pubsub_relay()
    yield
    await stop_pubsub_relay()


# --- 8.1.1: Initialize FastAPI app ---
app = FastAPI(
    title="Multi-User Web Trading Platform",
    description="Trading platform with admin testing UI and multi-user support",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# --- 8.1.2: Configure CORS ---
# CORS_ORIGINS env var accepts comma-separated origins.
# Defaults to localhost:3000 for local development.
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 8.1.3: Configure middleware ---
# Note: Middleware executes in reverse order of addition.
# RequestIDMiddleware runs first (outermost), then RequestLoggingMiddleware.
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestIDMiddleware)

# Note on request size limits:
# In production, request size limits should be enforced at the reverse proxy
# level (nginx: client_max_body_size). FastAPI does not have a built-in
# request body size limit middleware. For defense-in-depth, individual
# endpoints that accept file uploads should validate Content-Length.

# --- 8.1.4: Set up error handlers ---
register_error_handlers(app)

# --- Mount routers ---
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(trading_router)
app.include_router(killswitch_router)
app.include_router(signals_router)
app.include_router(scanner_router)
app.include_router(index_analyzer_router)
app.include_router(settings_router)
app.include_router(position_monitor_router)
app.include_router(paper_trading_router)
app.include_router(journal_router)
app.include_router(charts_router)
app.include_router(status_router)
app.include_router(ai_router)
app.include_router(broker_settings_router)
app.include_router(live_market_router)
app.include_router(market_data_settings_router)
app.include_router(account_router)
app.include_router(dhan_account_router)
app.include_router(instruments_router)
app.include_router(advanced_orders_router)

# --- Top-level OAuth callback redirect ---
# Zerodha redirects to /callback, but our API endpoint is at
# /api/v1/settings/brokers/kite/callback. This bridges the gap.
from fastapi.responses import RedirectResponse, HTMLResponse


@app.get("/callback")
async def oauth_callback_redirect(request_token: str = "", status_param: str = ""):
    """Handle Zerodha OAuth callback.

    If request_token is present, returns a simple HTML page that:
    1. Displays the request_token (for Selenium auto-login to extract)
    2. Auto-redirects to frontend for browser-based OAuth flow
    
    This serves both the Selenium auto-login (captures token from page)
    and the web app OAuth popup flow (redirects to frontend).
    """
    if not request_token:
        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
        return RedirectResponse(url=frontend_url)
    
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    
    # Return HTML that both Selenium can parse AND browser users see a redirect
    html_content = f"""<!DOCTYPE html>
<html>
<head><title>Kite OAuth Callback</title></head>
<body>
<p id="request_token" data-token="{request_token}">request_token={request_token}</p>
<p>Redirecting...</p>
<script>
    // For browser-based OAuth: redirect to frontend after a short delay
    setTimeout(function() {{
        window.location.href = "{frontend_url}/settings#brokers";
    }}, 1000);
    
    // Notify parent window (popup flow)
    if (window.opener) {{
        window.opener.postMessage({{ type: 'kite_oauth_success', request_token: '{request_token}' }}, '*');
        window.close();
    }}
</script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@app.post("/postback")
async def kite_postback():
    """Handle Kite postback notifications (order updates, etc)."""
    # Placeholder for order postback handling
    return {"status": "ok"}


@app.get("/login")
async def oauth_login_redirect(request_token: str = "", status: str = ""):
    """Alternative OAuth callback handler.
    
    Some Zerodha apps may have /login configured as redirect URL.
    This handles it identically to /callback.
    """
    return await oauth_callback_redirect(request_token=request_token, status_param=status)


# --- 13.1: Mount WebSocket (Socket.IO) server ---
app.mount("/ws", socket_app)
