"""Trade Journal Service — creates journal entries on trade exit events.

Wires the Position Monitor auto-exit flow to TradeJournalEntry creation,
capturing all metadata (setup_type, confidence_score, trend_direction,
exit_reason, AI grade if available).

Implements Requirements: 14.5, 7.3-7.6
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from src.database.models.scan_signal import ScanSignal
from src.database.models.trade import Trade
from src.database.models.trade_journal import TradeJournalEntry

logger = logging.getLogger(__name__)


class TradeJournalService:
    """Creates TradeJournalEntry records when trades are exited.

    Gathers metadata from the trade, position monitor state, and
    related scan signal (if available) to build a complete journal entry.
    """

    def __init__(self, db: Session) -> None:
        """Initialize TradeJournalService.

        Args:
            db: SQLAlchemy session for database operations.
        """
        if db is None:
            raise ValueError("db cannot be None")
        self.db = db

    def create_journal_entry_on_exit(
        self,
        trade_id: int,
        user_id: int,
        exit_reason: str,
        exit_price: float,
        ai_grade: Optional[str] = None,
        ai_entry_feedback: Optional[str] = None,
        ai_exit_feedback: Optional[str] = None,
        ai_sizing_feedback: Optional[str] = None,
        ai_risk_feedback: Optional[str] = None,
        ai_patterns: Optional[list] = None,
    ) -> Optional[TradeJournalEntry]:
        """Create a TradeJournalEntry after a trade exit event.

        Looks up the trade record and related scan signal to populate
        setup_type, confidence_score, and trend_direction. Calculates P&L
        from entry/exit prices.

        Args:
            trade_id: The ID of the exited trade.
            user_id: The user who owns the trade.
            exit_reason: The reason for exit (sl_hit, target_hit,
                        trailing_stop_hit, closed, manual).
            exit_price: The price at which the trade was exited.
            ai_grade: Optional AI grade (A/B/C/D/F) if available.
            ai_entry_feedback: Optional AI feedback on entry.
            ai_exit_feedback: Optional AI feedback on exit.
            ai_sizing_feedback: Optional AI feedback on sizing.
            ai_risk_feedback: Optional AI feedback on risk.
            ai_patterns: Optional list of AI-identified patterns.

        Returns:
            The created TradeJournalEntry, or None if the trade was not found
            or a journal entry already exists for this trade.
        """
        # Check if journal entry already exists for this trade
        existing = (
            self.db.query(TradeJournalEntry)
            .filter(
                TradeJournalEntry.trade_id == trade_id,
                TradeJournalEntry.user_id == user_id,
            )
            .first()
        )
        if existing:
            logger.debug(
                "Journal entry already exists for trade %d, skipping", trade_id
            )
            return existing

        # Fetch the trade record
        trade = self.db.query(Trade).filter(Trade.id == trade_id).first()
        if trade is None:
            logger.warning("Trade %d not found, cannot create journal entry", trade_id)
            return None

        # Compute P&L
        quantity = trade.qty
        pnl = (exit_price - trade.entry_price) * quantity

        # Look up related scan signal for metadata (setup_type, confidence, trend)
        setup_type: Optional[str] = None
        confidence_score: Optional[float] = None
        trend_direction: Optional[str] = None

        signal = self._find_related_signal(trade)
        if signal:
            setup_type = signal.signal_type
            confidence_score = signal.confidence_score
            # Extract trend direction from signal metadata
            if signal.metadata_json and isinstance(signal.metadata_json, dict):
                trend_direction = signal.metadata_json.get("trend_direction")

        # Create the journal entry
        journal_entry = TradeJournalEntry(
            user_id=user_id,
            trade_id=trade_id,
            symbol=trade.symbol,
            entry_price=trade.entry_price,
            exit_price=exit_price,
            pnl=pnl,
            setup_type=setup_type,
            confidence_score=confidence_score,
            trend_direction=trend_direction,
            exit_reason=exit_reason,
            ai_grade=ai_grade,
            ai_entry_feedback=ai_entry_feedback,
            ai_exit_feedback=ai_exit_feedback,
            ai_sizing_feedback=ai_sizing_feedback,
            ai_risk_feedback=ai_risk_feedback,
            ai_patterns=ai_patterns,
            trade_date=date.today(),
        )

        try:
            self.db.add(journal_entry)
            self.db.commit()
            self.db.refresh(journal_entry)

            logger.info(
                "Created journal entry %d for trade %d (user %d): exit_reason=%s, pnl=%.2f",
                journal_entry.id,
                trade_id,
                user_id,
                exit_reason,
                pnl,
            )
            return journal_entry

        except Exception as e:
            self.db.rollback()
            logger.error(
                "Failed to create journal entry for trade %d: %s: %s",
                trade_id,
                type(e).__name__,
                str(e),
            )
            return None

    def _find_related_signal(self, trade: Trade) -> Optional[ScanSignal]:
        """Find the scan signal that originated this trade.

        Searches for an approved signal matching the trade's symbol and user,
        created shortly before the trade.

        Args:
            trade: The trade to find the related signal for.

        Returns:
            The matching ScanSignal, or None if not found.
        """
        try:
            signal = (
                self.db.query(ScanSignal)
                .filter(
                    ScanSignal.user_id == trade.user_id,
                    ScanSignal.symbol == trade.symbol,
                    ScanSignal.status == "approved",
                )
                .order_by(ScanSignal.created_at.desc())
                .first()
            )
            return signal
        except Exception as e:
            logger.warning(
                "Error finding related signal for trade %d: %s",
                trade.id,
                str(e),
            )
            return None

    def enrich_with_ai_review(
        self,
        journal_entry_id: int,
        ai_grade: str,
        ai_entry_feedback: Optional[str] = None,
        ai_exit_feedback: Optional[str] = None,
        ai_sizing_feedback: Optional[str] = None,
        ai_risk_feedback: Optional[str] = None,
        ai_patterns: Optional[list] = None,
    ) -> Optional[TradeJournalEntry]:
        """Enrich an existing journal entry with AI trade review data.

        Called asynchronously after the AI trade review completes.

        Args:
            journal_entry_id: The ID of the journal entry to update.
            ai_grade: The AI grade (A/B/C/D/F).
            ai_entry_feedback: AI feedback on entry timing.
            ai_exit_feedback: AI feedback on exit timing.
            ai_sizing_feedback: AI feedback on position sizing.
            ai_risk_feedback: AI feedback on risk management.
            ai_patterns: List of identified patterns.

        Returns:
            The updated TradeJournalEntry, or None if not found.
        """
        entry = (
            self.db.query(TradeJournalEntry)
            .filter(TradeJournalEntry.id == journal_entry_id)
            .first()
        )
        if entry is None:
            logger.warning("Journal entry %d not found for AI enrichment", journal_entry_id)
            return None

        entry.ai_grade = ai_grade
        if ai_entry_feedback:
            entry.ai_entry_feedback = ai_entry_feedback
        if ai_exit_feedback:
            entry.ai_exit_feedback = ai_exit_feedback
        if ai_sizing_feedback:
            entry.ai_sizing_feedback = ai_sizing_feedback
        if ai_risk_feedback:
            entry.ai_risk_feedback = ai_risk_feedback
        if ai_patterns:
            entry.ai_patterns = ai_patterns

        try:
            self.db.commit()
            self.db.refresh(entry)
            logger.info(
                "Enriched journal entry %d with AI grade: %s",
                journal_entry_id,
                ai_grade,
            )
            return entry
        except Exception as e:
            self.db.rollback()
            logger.error(
                "Failed to enrich journal entry %d: %s: %s",
                journal_entry_id,
                type(e).__name__,
                str(e),
            )
            return None
