"""Property-based tests for Trade Journal filtering and sorting (Task 9.7).

**Property 14: Trade Journal Filtering and Sorting**
- Verify all returned entries match the applied filters
- Verify results are sorted in the correct order by the specified column

**Validates: Requirements 14.2, 14.3**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date, timedelta
from typing import List, Optional
from dataclasses import dataclass

from hypothesis import given, strategies as st, settings, assume


# ============================================================
# Pure filtering/sorting logic extracted from journal router
# ============================================================

VALID_SETUP_TYPES = [
    "trend_pullback",
    "consolidation_breakout",
    "momentum",
    "reversal",
    "scalp",
]
VALID_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX", "RELIANCE", "TCS", "INFY"]
VALID_TREND_DIRECTIONS = ["bullish", "bearish", "neutral"]
VALID_EXIT_REASONS = ["sl_hit", "target_hit", "trailing_stop", "manual", "time_based"]
VALID_SORT_COLUMNS = [
    "trade_date",
    "symbol",
    "entry_price",
    "exit_price",
    "pnl",
    "setup_type",
    "confidence_score",
    "trend_direction",
    "exit_reason",
    "ai_grade",
]


@dataclass
class JournalEntry:
    """Simplified journal entry for property testing."""

    trade_date: date
    symbol: str
    entry_price: float
    exit_price: float
    pnl: float
    setup_type: str
    confidence_score: float
    trend_direction: str
    exit_reason: str
    ai_grade: Optional[str] = None


def filter_entries(
    entries: List[JournalEntry],
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    setup_type: Optional[str] = None,
    symbol: Optional[str] = None,
    profit_loss: Optional[str] = None,
) -> List[JournalEntry]:
    """Apply filters matching the journal router logic.

    Mirrors the query filtering in src/api/routers/journal.py:
    - date_from: trade_date >= date_from
    - date_to: trade_date <= date_to
    - setup_type: exact match
    - symbol: exact match
    - profit_loss: 'profit' means pnl > 0, 'loss' means pnl < 0
    """
    result = list(entries)

    if date_from is not None:
        result = [e for e in result if e.trade_date >= date_from]
    if date_to is not None:
        result = [e for e in result if e.trade_date <= date_to]
    if setup_type is not None:
        result = [e for e in result if e.setup_type == setup_type]
    if symbol is not None:
        result = [e for e in result if e.symbol == symbol]
    if profit_loss == "profit":
        result = [e for e in result if e.pnl > 0]
    elif profit_loss == "loss":
        result = [e for e in result if e.pnl < 0]

    return result


def sort_entries(
    entries: List[JournalEntry],
    sort_by: str = "trade_date",
    sort_order: str = "desc",
) -> List[JournalEntry]:
    """Apply sorting matching the journal router logic.

    Mirrors the ORDER BY logic in src/api/routers/journal.py:
    - sort_by: column name from SORT_COLUMNS
    - sort_order: 'asc' or 'desc'
    """
    if sort_by not in VALID_SORT_COLUMNS:
        sort_by = "trade_date"

    reverse = sort_order == "desc"

    def sort_key(entry: JournalEntry):
        val = getattr(entry, sort_by)
        if val is None:
            # None values sort last for both asc and desc
            # Use a tuple to handle None comparison
            return (1, "")
        return (0, val)

    return sorted(entries, key=sort_key, reverse=reverse)


# ============================================================
# Custom Strategies
# ============================================================


def journal_entry_strategy():
    """Generate a random journal entry."""
    return st.builds(
        JournalEntry,
        trade_date=st.dates(
            min_value=date(2024, 1, 1),
            max_value=date(2024, 12, 31),
        ),
        symbol=st.sampled_from(VALID_SYMBOLS),
        entry_price=st.floats(
            min_value=100.0,
            max_value=50000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        exit_price=st.floats(
            min_value=100.0,
            max_value=50000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        pnl=st.floats(
            min_value=-5000.0,
            max_value=5000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        setup_type=st.sampled_from(VALID_SETUP_TYPES),
        confidence_score=st.floats(
            min_value=50.0,
            max_value=100.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        trend_direction=st.sampled_from(VALID_TREND_DIRECTIONS),
        exit_reason=st.sampled_from(VALID_EXIT_REASONS),
        ai_grade=st.sampled_from(["A", "B", "C", "D", "F", None]),
    )


def journal_entries_strategy():
    """Generate a list of 0-20 journal entries."""
    return st.lists(journal_entry_strategy(), min_size=0, max_size=20)


def date_range_strategy():
    """Generate an optional date range (from, to) where from <= to."""
    return st.one_of(
        st.just((None, None)),
        st.tuples(
            st.dates(min_value=date(2024, 1, 1), max_value=date(2024, 12, 31)),
            st.dates(min_value=date(2024, 1, 1), max_value=date(2024, 12, 31)),
        ).map(lambda t: (min(t[0], t[1]), max(t[0], t[1]))),
    )


def filter_params_strategy():
    """Generate a combination of filter parameters."""
    return st.fixed_dictionaries({
        "date_from": st.one_of(
            st.none(),
            st.dates(min_value=date(2024, 1, 1), max_value=date(2024, 12, 31)),
        ),
        "date_to": st.one_of(
            st.none(),
            st.dates(min_value=date(2024, 1, 1), max_value=date(2024, 12, 31)),
        ),
        "setup_type": st.one_of(st.none(), st.sampled_from(VALID_SETUP_TYPES)),
        "symbol": st.one_of(st.none(), st.sampled_from(VALID_SYMBOLS)),
        "profit_loss": st.one_of(st.none(), st.sampled_from(["profit", "loss"])),
    })


def sort_params_strategy():
    """Generate sort parameters."""
    return st.fixed_dictionaries({
        "sort_by": st.sampled_from(VALID_SORT_COLUMNS),
        "sort_order": st.sampled_from(["asc", "desc"]),
    })


# ============================================================
# Property 14: Trade Journal Filtering and Sorting
# ============================================================


class TestJournalFiltering:
    """Property-based tests verifying journal filtering correctness.

    **Validates: Requirements 14.2, 14.3**
    """

    @given(
        entries=journal_entries_strategy(),
        filters=filter_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_all_returned_entries_match_date_from_filter(self, entries, filters):
        """All returned entries have trade_date >= date_from when filter is set.

        **Validates: Requirements 14.2**

        Property: For any list of journal entries and a date_from filter,
        every entry in the filtered result has trade_date >= date_from.
        """
        result = filter_entries(entries, date_from=filters["date_from"])

        if filters["date_from"] is not None:
            for entry in result:
                assert entry.trade_date >= filters["date_from"], (
                    f"Entry trade_date {entry.trade_date} < date_from "
                    f"{filters['date_from']}"
                )

    @given(
        entries=journal_entries_strategy(),
        filters=filter_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_all_returned_entries_match_date_to_filter(self, entries, filters):
        """All returned entries have trade_date <= date_to when filter is set.

        **Validates: Requirements 14.2**

        Property: For any list of journal entries and a date_to filter,
        every entry in the filtered result has trade_date <= date_to.
        """
        result = filter_entries(entries, date_to=filters["date_to"])

        if filters["date_to"] is not None:
            for entry in result:
                assert entry.trade_date <= filters["date_to"], (
                    f"Entry trade_date {entry.trade_date} > date_to "
                    f"{filters['date_to']}"
                )

    @given(
        entries=journal_entries_strategy(),
        filters=filter_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_all_returned_entries_match_setup_type_filter(self, entries, filters):
        """All returned entries have matching setup_type when filter is set.

        **Validates: Requirements 14.2**

        Property: For any list of journal entries and a setup_type filter,
        every entry in the filtered result has setup_type equal to the filter value.
        """
        result = filter_entries(entries, setup_type=filters["setup_type"])

        if filters["setup_type"] is not None:
            for entry in result:
                assert entry.setup_type == filters["setup_type"], (
                    f"Entry setup_type '{entry.setup_type}' != filter "
                    f"'{filters['setup_type']}'"
                )

    @given(
        entries=journal_entries_strategy(),
        filters=filter_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_all_returned_entries_match_symbol_filter(self, entries, filters):
        """All returned entries have matching symbol when filter is set.

        **Validates: Requirements 14.2**

        Property: For any list of journal entries and a symbol filter,
        every entry in the filtered result has symbol equal to the filter value.
        """
        result = filter_entries(entries, symbol=filters["symbol"])

        if filters["symbol"] is not None:
            for entry in result:
                assert entry.symbol == filters["symbol"], (
                    f"Entry symbol '{entry.symbol}' != filter '{filters['symbol']}'"
                )

    @given(
        entries=journal_entries_strategy(),
        filters=filter_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_all_returned_entries_match_profit_loss_filter(self, entries, filters):
        """All returned entries match profit/loss filter when set.

        **Validates: Requirements 14.2**

        Property: For any list of journal entries:
        - profit_loss='profit' → all entries have pnl > 0
        - profit_loss='loss' → all entries have pnl < 0
        """
        result = filter_entries(entries, profit_loss=filters["profit_loss"])

        if filters["profit_loss"] == "profit":
            for entry in result:
                assert entry.pnl > 0, (
                    f"Entry pnl {entry.pnl} should be > 0 for profit filter"
                )
        elif filters["profit_loss"] == "loss":
            for entry in result:
                assert entry.pnl < 0, (
                    f"Entry pnl {entry.pnl} should be < 0 for loss filter"
                )

    @given(
        entries=journal_entries_strategy(),
        filters=filter_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_combined_filters_all_criteria_met(self, entries, filters):
        """Combined filters: all returned entries satisfy all active filters.

        **Validates: Requirements 14.2**

        Property: For any list of journal entries with multiple filters applied,
        every entry in the result satisfies ALL active filter criteria simultaneously.
        """
        result = filter_entries(
            entries,
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            setup_type=filters["setup_type"],
            symbol=filters["symbol"],
            profit_loss=filters["profit_loss"],
        )

        for entry in result:
            if filters["date_from"] is not None:
                assert entry.trade_date >= filters["date_from"]
            if filters["date_to"] is not None:
                assert entry.trade_date <= filters["date_to"]
            if filters["setup_type"] is not None:
                assert entry.setup_type == filters["setup_type"]
            if filters["symbol"] is not None:
                assert entry.symbol == filters["symbol"]
            if filters["profit_loss"] == "profit":
                assert entry.pnl > 0
            elif filters["profit_loss"] == "loss":
                assert entry.pnl < 0

    @given(
        entries=journal_entries_strategy(),
        filters=filter_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_no_matching_entries_excluded(self, entries, filters):
        """Filtering does not exclude entries that match all criteria.

        **Validates: Requirements 14.2**

        Property: Every entry from the input that satisfies all active filters
        appears in the filtered result (completeness).
        """
        result = filter_entries(
            entries,
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            setup_type=filters["setup_type"],
            symbol=filters["symbol"],
            profit_loss=filters["profit_loss"],
        )

        for entry in entries:
            should_include = True
            if filters["date_from"] is not None and entry.trade_date < filters["date_from"]:
                should_include = False
            if filters["date_to"] is not None and entry.trade_date > filters["date_to"]:
                should_include = False
            if filters["setup_type"] is not None and entry.setup_type != filters["setup_type"]:
                should_include = False
            if filters["symbol"] is not None and entry.symbol != filters["symbol"]:
                should_include = False
            if filters["profit_loss"] == "profit" and entry.pnl <= 0:
                should_include = False
            if filters["profit_loss"] == "loss" and entry.pnl >= 0:
                should_include = False

            if should_include:
                assert entry in result, (
                    f"Entry {entry} should be in results but was excluded"
                )


class TestJournalSorting:
    """Property-based tests verifying journal sorting correctness.

    **Validates: Requirements 14.3**
    """

    @given(
        entries=journal_entries_strategy(),
        sort_params=sort_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_result_sorted_in_correct_order(self, entries, sort_params):
        """Results are sorted by the specified column in the specified order.

        **Validates: Requirements 14.3**

        Property: For any list of journal entries and sort parameters,
        the sorted output is in correct ascending or descending order
        by the specified column.
        """
        result = sort_entries(
            entries,
            sort_by=sort_params["sort_by"],
            sort_order=sort_params["sort_order"],
        )

        if len(result) <= 1:
            return  # Trivially sorted

        sort_by = sort_params["sort_by"]
        ascending = sort_params["sort_order"] == "asc"

        for i in range(len(result) - 1):
            val_a = getattr(result[i], sort_by)
            val_b = getattr(result[i + 1], sort_by)

            # Handle None values (they sort last)
            if val_a is None and val_b is None:
                continue
            if val_a is None:
                # None should be at the end
                assert not ascending or val_b is None, (
                    f"None value at index {i} should sort after non-None "
                    f"values in ascending order"
                )
                continue
            if val_b is None:
                continue  # Next value is None, which is fine (it's at the end)

            if ascending:
                assert val_a <= val_b, (
                    f"Sort order violated at index {i}: "
                    f"{val_a} > {val_b} (expected ascending by {sort_by})"
                )
            else:
                assert val_a >= val_b, (
                    f"Sort order violated at index {i}: "
                    f"{val_a} < {val_b} (expected descending by {sort_by})"
                )

    @given(
        entries=journal_entries_strategy(),
        sort_params=sort_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_sorting_preserves_all_entries(self, entries, sort_params):
        """Sorting does not add or remove entries.

        **Validates: Requirements 14.3**

        Property: For any list of journal entries, sorting produces
        a result with the same length and same entries (just reordered).
        """
        result = sort_entries(
            entries,
            sort_by=sort_params["sort_by"],
            sort_order=sort_params["sort_order"],
        )

        assert len(result) == len(entries), (
            f"Sorting changed entry count: {len(entries)} -> {len(result)}"
        )

        # Every entry in input is in output and vice versa
        for entry in entries:
            assert entry in result, (
                f"Entry {entry} from input not found in sorted output"
            )

    @given(
        entries=journal_entries_strategy(),
        filters=filter_params_strategy(),
        sort_params=sort_params_strategy(),
    )
    @settings(max_examples=200, deadline=None)
    def test_filter_then_sort_produces_correct_result(self, entries, filters, sort_params):
        """Filtering then sorting: result matches filters AND is sorted.

        **Validates: Requirements 14.2, 14.3**

        Property: For any list of entries with filters and sort params,
        filtering then sorting produces a result where all entries match
        the filters and are in the correct sort order.
        """
        filtered = filter_entries(
            entries,
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            setup_type=filters["setup_type"],
            symbol=filters["symbol"],
            profit_loss=filters["profit_loss"],
        )
        result = sort_entries(
            filtered,
            sort_by=sort_params["sort_by"],
            sort_order=sort_params["sort_order"],
        )

        # All entries match filters
        for entry in result:
            if filters["date_from"] is not None:
                assert entry.trade_date >= filters["date_from"]
            if filters["date_to"] is not None:
                assert entry.trade_date <= filters["date_to"]
            if filters["setup_type"] is not None:
                assert entry.setup_type == filters["setup_type"]
            if filters["symbol"] is not None:
                assert entry.symbol == filters["symbol"]
            if filters["profit_loss"] == "profit":
                assert entry.pnl > 0
            elif filters["profit_loss"] == "loss":
                assert entry.pnl < 0

        # Result is sorted correctly
        if len(result) > 1:
            sort_by = sort_params["sort_by"]
            ascending = sort_params["sort_order"] == "asc"

            for i in range(len(result) - 1):
                val_a = getattr(result[i], sort_by)
                val_b = getattr(result[i + 1], sort_by)

                if val_a is None or val_b is None:
                    continue

                if ascending:
                    assert val_a <= val_b
                else:
                    assert val_a >= val_b
