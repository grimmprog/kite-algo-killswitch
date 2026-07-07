"""Advanced Orders API — GTT (Kite), Trailing SL & Targets (Dhan), Margin Estimation.

Endpoints:
- POST /api/v1/orders/gtt — Place a Zerodha GTT (Good Till Triggered) order
- POST /api/v1/orders/dhan — Place a Dhan order with trailing SL and targets
- POST /api/v1/orders/margin-estimate — Estimate margin required for an order
- GET  /api/v1/orders/gtt — List active GTT orders for the user
- DELETE /api/v1/orders/gtt/{gtt_id} — Cancel a GTT order
"""

import logging
import os
from typing import Dict, List, Optional

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db, get_redis
from src.broker.token_encryption import TokenEncryption
from src.cache.redis_client import RedisClient
from src.cache.redis_keys import RedisKeys
from src.database.models.broker_connection import BrokerConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orders", tags=["advanced-orders"])

DHAN_API_BASE = "https://api.dhan.co/v2"


# ============================================================
# Request/Response Models
# ============================================================


class GTTCondition(BaseModel):
    """A single GTT trigger condition."""
    trigger_price: float = Field(..., gt=0, description="Price at which the order triggers")
    order_price: float = Field(..., gt=0, description="Limit price for the triggered order (0 = market)")
    quantity: int = Field(..., gt=0, description="Quantity to buy/sell when triggered")


class GTTOrderRequest(BaseModel):
    """Request to place a Zerodha GTT (Good Till Triggered) order.

    GTT types:
    - single: One trigger condition (stop-loss OR entry)
    - two-leg: Two conditions (stop-loss + target / OCO)

    For NIFTY options:
    - Use exchange='NFO'
    - Symbol format: 'NIFTY2472424400CE' (index + expiry + strike + type)
    """
    symbol: str = Field(..., min_length=1, max_length=50)
    exchange: str = Field(..., pattern=r"^(NSE|NFO|BSE|BFO)$")
    side: str = Field(..., pattern=r"^(BUY|SELL)$")
    gtt_type: str = Field(default="single", pattern=r"^(single|two-leg)$")
    last_price: float = Field(..., gt=0, description="Current LTP of the instrument")
    condition: GTTCondition = Field(..., description="Primary trigger condition")
    second_condition: Optional[GTTCondition] = Field(
        default=None, description="Second leg (target/OCO) — required for two-leg GTT"
    )


class GTTOrderResponse(BaseModel):
    """Response after placing a GTT order."""
    success: bool
    gtt_id: Optional[int] = None
    message: str


class GTTListItem(BaseModel):
    """A single GTT order in the list."""
    gtt_id: int
    symbol: str
    exchange: str
    gtt_type: str
    status: str
    condition: Dict
    second_condition: Optional[Dict] = None
    created_at: Optional[str] = None


class DhanOrderRequest(BaseModel):
    """Request to place a Dhan order with trailing SL and targets.

    Supports:
    - Market/Limit orders
    - Trailing stop-loss (absolute trail value in points)
    - Multiple target levels (partial exits)
    """
    symbol: str = Field(..., min_length=1, max_length=50)
    exchange: str = Field(default="NSE_FNO", description="NSE_EQ, NSE_FNO, BSE_EQ, BSE_FNO")
    security_id: str = Field(..., description="Dhan security ID for the instrument")
    side: str = Field(..., pattern=r"^(BUY|SELL)$")
    quantity: int = Field(..., gt=0)
    order_type: str = Field(default="MARKET", pattern=r"^(MARKET|LIMIT|SL|SL-M)$")
    price: Optional[float] = Field(default=None, gt=0)
    trigger_price: Optional[float] = Field(default=None, gt=0)
    product: str = Field(default="INTRADAY", pattern=r"^(INTRADAY|CNC|MARGIN)$")
    # Trailing stop-loss
    trailing_sl: Optional[float] = Field(
        default=None, gt=0,
        description="Trailing stop-loss in absolute points (e.g., 10 = trail by ₹10)"
    )
    # Stop-loss price (initial)
    stop_loss_price: Optional[float] = Field(default=None, gt=0)
    # Target levels for partial/full exit
    target_price: Optional[float] = Field(default=None, gt=0, description="Primary target")
    target_2_price: Optional[float] = Field(default=None, gt=0, description="Second target")


class DhanOrderResponse(BaseModel):
    """Response after placing a Dhan order."""
    success: bool
    order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    target_order_id: Optional[str] = None
    message: str


class MarginEstimateRequest(BaseModel):
    """Request to estimate margin required for an order."""
    broker: str = Field(..., pattern=r"^(kite|dhan)$")
    symbol: str = Field(..., min_length=1, max_length=50)
    exchange: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    side: str = Field(..., pattern=r"^(BUY|SELL)$")
    order_type: str = Field(default="MARKET")
    price: Optional[float] = Field(default=None, gt=0)
    # Dhan-specific
    security_id: Optional[str] = None
    product: str = Field(default="INTRADAY")


class MarginEstimateResponse(BaseModel):
    """Estimated margin and capital check result."""
    required_margin: float
    available_margin: float
    sufficient_funds: bool
    shortfall: float = Field(default=0, description="How much more capital is needed (0 if sufficient)")
    broker: str
    breakdown: Optional[Dict] = None


# ============================================================
# Helper: Get Kite Client
# ============================================================


def _get_kite_client(db: Session, user_id: int):
    """Get an authenticated KiteConnect client for the user.

    Returns:
        Configured KiteConnect instance.

    Raises:
        HTTPException 503: If Kite is not connected.
    """
    from src.broker.kite_client_factory import KiteClientFactory, BrokerAuthError, TokenExpiredError
    from src.broker.token_encryption import TokenEncryption

    api_key = os.environ.get("KITE_API_KEY", "")
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")

    if not api_key or not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kite not configured",
        )

    token_enc = TokenEncryption(encryption_key=encryption_key)

    def session_factory():
        return db

    factory = KiteClientFactory(
        api_key=api_key,
        token_encryption=token_enc,
        db_session_factory=session_factory,
    )

    try:
        return factory.get_client(user_id)
    except (BrokerAuthError, TokenExpiredError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Kite not connected: {e}",
        )


def _get_dhan_credentials(db: Session, user_id: int) -> tuple:
    """Get Dhan access token and client ID for the user.

    Returns:
        Tuple of (access_token, client_id).

    Raises:
        HTTPException 503: If Dhan is not connected.
    """
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dhan not connected",
        )

    connection = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.user_id == user_id,
            BrokerConnection.broker_type == "dhan",
            BrokerConnection.access_token_encrypted.isnot(None),
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dhan not connected",
        )

    encryptor = TokenEncryption(encryption_key=encryption_key)
    access_token = encryptor.decrypt(connection.access_token_encrypted)
    client_id = (
        encryptor.decrypt(connection.client_id_encrypted)
        if connection.client_id_encrypted else ""
    )

    return access_token, client_id


# ============================================================
# GTT Orders (Kite/Zerodha)
# ============================================================


@router.post("/gtt", response_model=GTTOrderResponse)
async def place_gtt_order(
    request: GTTOrderRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Place a Zerodha GTT (Good Till Triggered) order.

    GTT orders remain active until triggered or cancelled (up to 1 year).
    Useful for setting stop-loss or target orders that persist across sessions.

    Single-leg: One trigger (e.g., stop-loss at 100)
    Two-leg (OCO): Two triggers (e.g., stop-loss at 90 AND target at 130)
    """
    # Check kill switch
    ks = redis.get(RedisKeys.user_killswitch(user_id))
    if ks and ks.lower() == "true":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trading blocked: kill switch is active",
        )

    kite = _get_kite_client(db, user_id)

    try:
        # Build trigger values and orders list
        if request.gtt_type == "single":
            trigger_values = [request.condition.trigger_price]
            orders = [{
                "exchange": request.exchange,
                "tradingsymbol": request.symbol,
                "transaction_type": request.side,
                "quantity": request.condition.quantity,
                "order_type": "LIMIT" if request.condition.order_price > 0 else "MARKET",
                "product": "MIS",
                "price": request.condition.order_price if request.condition.order_price > 0 else 0,
            }]
            gtt_type = kite.GTT_TYPE_SINGLE

        else:
            # Two-leg (OCO)
            if not request.second_condition:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="second_condition is required for two-leg GTT",
                )

            trigger_values = [
                request.condition.trigger_price,
                request.second_condition.trigger_price,
            ]
            orders = [
                {
                    "exchange": request.exchange,
                    "tradingsymbol": request.symbol,
                    "transaction_type": request.side,
                    "quantity": request.condition.quantity,
                    "order_type": "LIMIT",
                    "product": "MIS",
                    "price": request.condition.order_price,
                },
                {
                    "exchange": request.exchange,
                    "tradingsymbol": request.symbol,
                    "transaction_type": request.side,
                    "quantity": request.second_condition.quantity,
                    "order_type": "LIMIT",
                    "product": "MIS",
                    "price": request.second_condition.order_price,
                },
            ]
            gtt_type = kite.GTT_TYPE_OCO

        # Place GTT via Kite Connect API
        response = kite.place_gtt(
            trigger_type=gtt_type,
            tradingsymbol=request.symbol,
            exchange=request.exchange,
            trigger_values=trigger_values,
            last_price=request.last_price,
            orders=orders,
        )

        gtt_id = response.get("trigger_id")
        logger.info(
            "GTT placed for user %d: gtt_id=%s, symbol=%s, type=%s",
            user_id, gtt_id, request.symbol, request.gtt_type,
        )

        return GTTOrderResponse(success=True, gtt_id=gtt_id, message="GTT order placed successfully")

    except Exception as e:
        logger.error("GTT placement failed for user %d: %s: %s", user_id, type(e).__name__, str(e))
        return GTTOrderResponse(success=False, gtt_id=None, message=f"GTT failed: {str(e)}")


@router.get("/gtt", response_model=List[GTTListItem])
async def list_gtt_orders(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active GTT orders for the user."""
    kite = _get_kite_client(db, user_id)

    try:
        gtts = kite.get_gtts()
        result = []
        for g in gtts:
            item = GTTListItem(
                gtt_id=g.get("id", 0),
                symbol=g.get("condition", {}).get("tradingsymbol", ""),
                exchange=g.get("condition", {}).get("exchange", ""),
                gtt_type="two-leg" if len(g.get("orders", [])) > 1 else "single",
                status=g.get("status", "unknown"),
                condition={
                    "trigger_price": g.get("condition", {}).get("trigger_values", [0])[0],
                    "last_price": g.get("condition", {}).get("last_price", 0),
                },
                second_condition=(
                    {"trigger_price": g["condition"]["trigger_values"][1]}
                    if len(g.get("condition", {}).get("trigger_values", [])) > 1
                    else None
                ),
                created_at=g.get("created_at"),
            )
            result.append(item)
        return result

    except Exception as e:
        logger.error("Failed to list GTTs for user %d: %s", user_id, str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch GTT list: {str(e)}")


@router.delete("/gtt/{gtt_id}")
async def cancel_gtt_order(
    gtt_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel (delete) a GTT order."""
    kite = _get_kite_client(db, user_id)

    try:
        kite.delete_gtt(gtt_id)
        logger.info("GTT %d cancelled by user %d", gtt_id, user_id)
        return {"success": True, "message": f"GTT {gtt_id} cancelled"}
    except Exception as e:
        logger.error("Failed to cancel GTT %d for user %d: %s", gtt_id, user_id, str(e))
        raise HTTPException(status_code=400, detail=f"Failed to cancel GTT: {str(e)}")


# ============================================================
# Dhan Orders with Trailing SL & Targets
# ============================================================


@router.post("/dhan", response_model=DhanOrderResponse)
async def place_dhan_order(
    request: DhanOrderRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Place a Dhan order with optional trailing stop-loss and target orders.

    Flow:
    1. Place the primary order (market/limit)
    2. If stop_loss_price or trailing_sl is set, place a SL/SL-M order
    3. If target_price is set, place a limit target order

    For trailing SL, Dhan's native trailing feature is used via the
    'trailingStopLoss' parameter in the order payload.
    """
    # Check kill switch
    ks = redis.get(RedisKeys.user_killswitch(user_id))
    if ks and ks.lower() == "true":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trading blocked: kill switch is active",
        )

    access_token, client_id = _get_dhan_credentials(db, user_id)

    headers = {
        "Content-Type": "application/json",
        "access-token": access_token,
    }

    # Map side to Dhan format
    dhan_side = "BUY" if request.side == "BUY" else "SELL"
    exit_side = "SELL" if request.side == "BUY" else "BUY"

    # Map order type
    dhan_order_type_map = {
        "MARKET": "MARKET",
        "LIMIT": "LIMIT",
        "SL": "STOP_LOSS",
        "SL-M": "STOP_LOSS_MARKET",
    }
    dhan_order_type = dhan_order_type_map.get(request.order_type, "MARKET")

    # Map product
    dhan_product_map = {
        "INTRADAY": "INTRADAY",
        "CNC": "CNC",
        "MARGIN": "MARGIN",
    }
    dhan_product = dhan_product_map.get(request.product, "INTRADAY")

    # --- Step 1: Place primary order ---
    primary_payload = {
        "dhanClientId": client_id,
        "transactionType": dhan_side,
        "exchangeSegment": request.exchange,
        "productType": dhan_product,
        "orderType": dhan_order_type,
        "validity": "DAY",
        "securityId": request.security_id,
        "quantity": request.quantity,
        "price": request.price or 0,
        "triggerPrice": request.trigger_price or 0,
    }

    try:
        resp = http_requests.post(
            f"{DHAN_API_BASE}/orders",
            json=primary_payload,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        primary_result = resp.json()
        primary_order_id = primary_result.get("orderId", "")

    except Exception as e:
        logger.error("Dhan primary order failed for user %d: %s", user_id, str(e))
        return DhanOrderResponse(
            success=False, order_id=None, message=f"Primary order failed: {str(e)}"
        )

    # --- Step 2: Place trailing SL order ---
    sl_order_id = None
    if request.stop_loss_price or request.trailing_sl:
        sl_payload = {
            "dhanClientId": client_id,
            "transactionType": exit_side,
            "exchangeSegment": request.exchange,
            "productType": dhan_product,
            "orderType": "STOP_LOSS" if request.stop_loss_price else "STOP_LOSS_MARKET",
            "validity": "DAY",
            "securityId": request.security_id,
            "quantity": request.quantity,
            "price": request.stop_loss_price or 0,
            "triggerPrice": request.stop_loss_price or 0,
        }

        # Add trailing stop-loss if specified
        if request.trailing_sl:
            sl_payload["trailingStopLoss"] = {
                "stopLossValue": request.trailing_sl,
            }

        try:
            resp = http_requests.post(
                f"{DHAN_API_BASE}/orders",
                json=sl_payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            sl_result = resp.json()
            sl_order_id = sl_result.get("orderId", "")
        except Exception as e:
            logger.warning(
                "Dhan SL order failed for user %d (primary OK): %s", user_id, str(e)
            )

    # --- Step 3: Place target order ---
    target_order_id = None
    if request.target_price:
        target_payload = {
            "dhanClientId": client_id,
            "transactionType": exit_side,
            "exchangeSegment": request.exchange,
            "productType": dhan_product,
            "orderType": "LIMIT",
            "validity": "DAY",
            "securityId": request.security_id,
            "quantity": request.quantity,
            "price": request.target_price,
            "triggerPrice": 0,
        }

        try:
            resp = http_requests.post(
                f"{DHAN_API_BASE}/orders",
                json=target_payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            target_result = resp.json()
            target_order_id = target_result.get("orderId", "")
        except Exception as e:
            logger.warning(
                "Dhan target order failed for user %d (primary OK): %s", user_id, str(e)
            )

    logger.info(
        "Dhan order placed for user %d: primary=%s, sl=%s, target=%s",
        user_id, primary_order_id, sl_order_id, target_order_id,
    )

    return DhanOrderResponse(
        success=True,
        order_id=primary_order_id,
        sl_order_id=sl_order_id,
        target_order_id=target_order_id,
        message="Order placed successfully",
    )


# ============================================================
# Margin Estimation
# ============================================================


@router.post("/margin-estimate", response_model=MarginEstimateResponse)
async def estimate_margin(
    request: MarginEstimateRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Estimate total margin required for an order and check against available capital.

    For Kite: Uses kite.order_margins() API
    For Dhan: Uses Dhan margin calculator API

    Returns the required margin, available funds, and whether the order
    will succeed or fail due to insufficient capital.
    """
    if request.broker == "kite":
        return await _estimate_kite_margin(request, user_id, db)
    else:
        return await _estimate_dhan_margin(request, user_id, db)


async def _estimate_kite_margin(
    request: MarginEstimateRequest,
    user_id: int,
    db: Session,
) -> MarginEstimateResponse:
    """Estimate margin via Kite Connect API.

    Uses kite.order_margins() to get exchange-level margin requirement,
    and kite.margins() to get available funds.
    """
    kite = _get_kite_client(db, user_id)

    try:
        # Get margin required for this order
        margin_params = [{
            "exchange": request.exchange,
            "tradingsymbol": request.symbol,
            "transaction_type": request.side,
            "variety": "regular",
            "product": "MIS",
            "order_type": request.order_type,
            "quantity": request.quantity,
            "price": request.price or 0,
        }]

        margin_response = kite.order_margins(margin_params)

        if margin_response and len(margin_response) > 0:
            margin_data = margin_response[0]
            required_margin = margin_data.get("total", 0)
            breakdown = {
                "span": margin_data.get("span", 0),
                "exposure": margin_data.get("exposure", 0),
                "option_premium": margin_data.get("option_premium", 0),
                "additional": margin_data.get("additional", 0),
                "bo": margin_data.get("bo", 0),
                "cash": margin_data.get("cash", 0),
                "var": margin_data.get("var", 0),
                "pnl": margin_data.get("pnl", {}).get("realised", 0),
                "total": margin_data.get("total", 0),
            }
        else:
            # Fallback: estimate as price * quantity (for options = premium)
            estimated_price = request.price or 0
            required_margin = estimated_price * request.quantity
            breakdown = {"estimated": True, "premium_based": required_margin}

    except Exception as e:
        logger.warning("Kite margin API failed for user %d: %s, using fallback", user_id, str(e))
        estimated_price = request.price or 0
        required_margin = estimated_price * request.quantity
        breakdown = {"estimated": True, "fallback_reason": str(e)}

    # Get available margin
    try:
        margins = kite.margins(segment="equity")
        available_margin = margins.get("available", {}).get("live_balance", 0)
        # Also check net (cash + collateral)
        available_margin += margins.get("available", {}).get("collateral", 0)
    except Exception as e:
        logger.warning("Failed to fetch Kite margins for user %d: %s", user_id, str(e))
        available_margin = 0

    shortfall = max(0, required_margin - available_margin)

    return MarginEstimateResponse(
        required_margin=round(required_margin, 2),
        available_margin=round(available_margin, 2),
        sufficient_funds=available_margin >= required_margin,
        shortfall=round(shortfall, 2),
        broker="kite",
        breakdown=breakdown,
    )


async def _estimate_dhan_margin(
    request: MarginEstimateRequest,
    user_id: int,
    db: Session,
) -> MarginEstimateResponse:
    """Estimate margin via Dhan API.

    Uses Dhan's fund limit endpoint for available balance and
    estimates margin based on order parameters.
    """
    access_token, client_id = _get_dhan_credentials(db, user_id)

    headers = {
        "Content-Type": "application/json",
        "access-token": access_token,
    }

    # Get available funds from Dhan
    available_margin = 0
    try:
        resp = http_requests.get(
            f"{DHAN_API_BASE}/fundlimit",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        fund_data = resp.json()

        # Dhan returns various limit fields
        available_margin = float(fund_data.get("availabelBalance", 0))
        # sodLimit is Start-of-Day limit
        if available_margin == 0:
            available_margin = float(fund_data.get("sodLimit", 0))

    except Exception as e:
        logger.warning("Failed to fetch Dhan funds for user %d: %s", user_id, str(e))

    # Estimate margin required
    # For options buying: margin = premium * quantity
    # For options selling: use Dhan margin calculator if available
    breakdown = {}
    try:
        margin_payload = {
            "dhanClientId": client_id,
            "exchangeSegment": request.exchange or "NSE_FNO",
            "transactionType": request.side,
            "quantity": request.quantity,
            "productType": request.product,
            "securityId": request.security_id or "",
            "price": request.price or 0,
            "triggerPrice": 0,
        }

        resp = http_requests.post(
            f"{DHAN_API_BASE}/margincalculator",
            json=margin_payload,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        margin_data = resp.json()
        required_margin = float(margin_data.get("totalMarginRequired", 0))
        breakdown = margin_data

    except Exception as e:
        # Fallback: premium-based estimate
        logger.warning("Dhan margin calc failed for user %d: %s, using fallback", user_id, str(e))
        estimated_price = request.price or 0
        required_margin = estimated_price * request.quantity
        breakdown = {"estimated": True, "premium_based": required_margin}

    shortfall = max(0, required_margin - available_margin)

    return MarginEstimateResponse(
        required_margin=round(required_margin, 2),
        available_margin=round(available_margin, 2),
        sufficient_funds=available_margin >= required_margin,
        shortfall=round(shortfall, 2),
        broker="dhan",
        breakdown=breakdown,
    )
