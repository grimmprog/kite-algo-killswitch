"""Daily P&L Worker — Auto-saves daily trading performance at market close.

Runs at 3:35 PM IST (5 minutes after market close) to capture final
P&L for all active users. Data is stored in daily_pnl_snapshots table
for historical analysis and AI review.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.workers.daily_pnl_worker.save_all_daily_pnl")
def save_all_daily_pnl():
    """Save daily P&L snapshot for all users with active Kite sessions.

    Called by Celery beat at 3:35 PM IST daily.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from src.broker.token_encryption import TokenEncryption
    from src.database.models.broker_connection import BrokerConnection
    from src.database.models.daily_pnl import DailyPnLSnapshot

    database_url = os.environ.get("DATABASE_URL", "")
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    api_key = os.environ.get("KITE_API_KEY", "")

    if not database_url or not encryption_key or not api_key:
        logger.error("Missing env vars for daily P&L worker")
        return {"error": "Missing configuration"}

    engine = create_engine(database_url)
    enc = TokenEncryption(encryption_key=encryption_key)
    today = date.today()
    saved = 0

    with Session(engine) as db:
        # Find all users with active Kite connections
        connections = (
            db.query(BrokerConnection)
            .filter(
                BrokerConnection.broker_type == "kite",
                BrokerConnection.access_token_encrypted.isnot(None),
            )
            .all()
        )

        for conn in connections:
            user_id = conn.user_id

            # Skip if token expired
            if conn.token_expiry:
                expiry = conn.token_expiry
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry < datetime.now(timezone.utc):
                    continue

            try:
                from kiteconnect import KiteConnect

                token = enc.decrypt(conn.access_token_encrypted)
                kite = KiteConnect(api_key=api_key)
                kite.set_access_token(token)

                # Fetch data
                trades = kite.trades()
                orders = kite.orders()
                positions = kite.positions()
                margins = kite.margins(segment="equity")

                # Compute
                available = margins.get("available", {})
                net_capital = float(margins.get("net", available.get("cash", 0)))

                day_positions = positions.get("day", [])
                total_pnl = 0.0
                winning = 0
                losing = 0
                max_profit = 0.0
                max_loss = 0.0
                symbols = set()

                for pos in day_positions:
                    pnl = float(pos.get("pnl", 0))
                    total_pnl += pnl
                    sym = pos.get("tradingsymbol", "")
                    if sym:
                        symbols.add(sym)
                    if pnl > 0:
                        winning += 1
                        max_profit = max(max_profit, pnl)
                    elif pnl < 0:
                        losing += 1
                        max_loss = min(max_loss, pnl)

                executed = [o for o in orders if o.get("status") == "COMPLETE"]
                num_orders = len(executed)
                brokerage = num_orders * 20.0

                sell_turnover = 0.0
                total_turnover = 0.0
                for t in trades:
                    qty = int(t.get("filled_quantity", t.get("quantity", 0)))
                    price = float(t.get("average_price", 0))
                    val = qty * price
                    total_turnover += val
                    if t.get("transaction_type") == "SELL":
                        sell_turnover += val

                stt = sell_turnover * 0.0015
                exchange_charges = total_turnover * 0.00053
                gst = (brokerage + exchange_charges) * 0.18
                total_charges = round(brokerage + stt + exchange_charges + gst, 2)
                net_pnl = round(total_pnl - total_charges, 2)

                # Upsert
                existing = (
                    db.query(DailyPnLSnapshot)
                    .filter(
                        DailyPnLSnapshot.user_id == user_id,
                        DailyPnLSnapshot.trade_date == today,
                    )
                    .first()
                )

                if existing:
                    existing.gross_pnl = round(total_pnl, 2)
                    existing.total_charges = total_charges
                    existing.net_pnl = net_pnl
                    existing.opening_capital = round(net_capital - net_pnl, 2)
                    existing.closing_capital = round(net_capital, 2)
                    existing.total_trades = num_orders
                    existing.winning_trades = winning
                    existing.losing_trades = losing
                    existing.max_profit_trade = round(max_profit, 2)
                    existing.max_loss_trade = round(max_loss, 2)
                    existing.brokerage = round(brokerage, 2)
                    existing.stt = round(stt, 2)
                    existing.exchange_charges = round(exchange_charges, 2)
                    existing.gst = round(gst, 2)
                    existing.instruments_traded = json.dumps(list(symbols))
                else:
                    snapshot = DailyPnLSnapshot(
                        user_id=user_id,
                        trade_date=today,
                        gross_pnl=round(total_pnl, 2),
                        total_charges=total_charges,
                        net_pnl=net_pnl,
                        opening_capital=round(net_capital - net_pnl, 2),
                        closing_capital=round(net_capital, 2),
                        total_trades=num_orders,
                        winning_trades=winning,
                        losing_trades=losing,
                        max_profit_trade=round(max_profit, 2),
                        max_loss_trade=round(max_loss, 2),
                        brokerage=round(brokerage, 2),
                        stt=round(stt, 2),
                        exchange_charges=round(exchange_charges, 2),
                        gst=round(gst, 2),
                        instruments_traded=json.dumps(list(symbols)),
                    )
                    db.add(snapshot)

                db.commit()
                saved += 1
                logger.info("Saved daily P&L for user %d: net=%.2f", user_id, net_pnl)

            except Exception as e:
                logger.error("Failed to save daily P&L for user %d: %s", user_id, str(e))
                continue

    return {"saved": saved, "date": today.isoformat()}
