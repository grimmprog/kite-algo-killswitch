"""Tests for Admin Dependencies (src/admin/dependencies.py).

Tests cover:
- get_db: database session creation and cleanup
- get_redis: Redis client retrieval
- _get_session_factory: lazy singleton pattern
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest

from src.admin import dependencies


# ============================================================
# Tests for get_db
# ============================================================


class TestGetDb:
    """Tests for the database session dependency."""

    @patch("src.admin.dependencies._get_session_factory")
    def test_yields_session_and_closes(self, mock_factory):
        """get_db yields a session and closes it after use."""
        mock_session = MagicMock()
        mock_factory.return_value = MagicMock(return_value=mock_session)

        gen = dependencies.get_db()
        session = next(gen)

        assert session == mock_session
        # Trigger cleanup
        try:
            next(gen)
        except StopIteration:
            pass
        mock_session.close.assert_called_once()

    @patch("src.admin.dependencies._get_session_factory")
    def test_closes_session_on_exception(self, mock_factory):
        """get_db closes session even when request handler raises."""
        mock_session = MagicMock()
        mock_factory.return_value = MagicMock(return_value=mock_session)

        gen = dependencies.get_db()
        session = next(gen)

        # Simulate exception cleanup
        try:
            gen.throw(RuntimeError("Handler error"))
        except RuntimeError:
            pass
        mock_session.close.assert_called_once()


# ============================================================
# Tests for get_redis
# ============================================================


class TestGetRedis:
    """Tests for the Redis client dependency."""

    @patch("src.admin.dependencies.get_redis_client")
    def test_returns_redis_client(self, mock_get_redis):
        """get_redis returns the singleton Redis client."""
        mock_client = MagicMock()
        mock_get_redis.return_value = mock_client

        result = dependencies.get_redis()

        assert result == mock_client
        mock_get_redis.assert_called_once()


# ============================================================
# Tests for _get_session_factory
# ============================================================


class TestGetSessionFactory:
    """Tests for the lazy session factory singleton."""

    @patch("src.admin.dependencies.create_engine")
    @patch("src.admin.dependencies.sessionmaker")
    def test_creates_engine_on_first_call(self, mock_sessionmaker, mock_create_engine):
        """Creates engine and sessionmaker on first call."""
        # Reset module-level state
        dependencies._engine = None
        dependencies._SessionFactory = None

        mock_create_engine.return_value = MagicMock()
        mock_sessionmaker.return_value = MagicMock()

        result = dependencies._get_session_factory()

        mock_create_engine.assert_called_once()
        mock_sessionmaker.assert_called_once()
        assert result is not None

        # Clean up
        dependencies._engine = None
        dependencies._SessionFactory = None

    @patch("src.admin.dependencies.create_engine")
    @patch("src.admin.dependencies.sessionmaker")
    def test_reuses_factory_on_subsequent_calls(self, mock_sessionmaker, mock_create_engine):
        """Returns cached sessionmaker on subsequent calls."""
        # Reset module-level state
        dependencies._engine = None
        dependencies._SessionFactory = None

        mock_create_engine.return_value = MagicMock()
        mock_factory = MagicMock()
        mock_sessionmaker.return_value = mock_factory

        result1 = dependencies._get_session_factory()
        result2 = dependencies._get_session_factory()

        # Should only create once
        assert mock_create_engine.call_count == 1
        assert result1 == result2

        # Clean up
        dependencies._engine = None
        dependencies._SessionFactory = None
