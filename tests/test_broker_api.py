"""Tests for Broker API Integration.

Integration tests with mocked KiteConnect for:
- Position fetching via KiteClientFactory (Task 4.5.1)
- Order placement via kite.place_order() (Task 4.5.2)
- Market data fetching via kite.ltp()/kite.quote() (Task 4.5.3)

Requirements covered:
- 1.2.1: Integrate with Zerodha Kite Connect API
- 1.2.7: Fetch user positions from broker every 2-3 seconds
- 1.2.8: Fetch market data from broker every 3-5 seconds
- 1.3.4: Place orders with broker via Kite API
- 4.4.1: Use Kite Connect API for all broker operations
- 4.4.3: Handle broker API errors gracefully
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from src.broker.token_encryption import TokenEncryption
from src.broker.kite_client_factory import (
    KiteClientFactory,
    BrokerAuthError,
    TokenExpiredError,
)


# ============================================================
# Shared Fixtures
# ============================================================


@pytest.fixture
def encryption_key():
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode()


@pytest.fixture
def encryptor(encryption_key):
    """Create a TokenEncryption instance with a valid key."""
    return TokenEncryption(encryption_key)


@pytest.fixture
def mock_user(encryptor):
    """Create a mock user with valid encrypted broker token."""
    user = MagicMock()
    user.id = 1
    user.broker_access_token = encryptor.encrypt("live_access_token_abc123")
    user.broker_refresh_token = encryptor.encrypt("live_refresh_token_xyz789")
    user.broker_token_expiry = datetime.now(timezone.utc) + timedelta(hours=12)
    user.capital = 500000.0
    return user


@pytest.fixture
def mock_session_factory(mock_user):
    """Create a mock session factory that returns a session with the mock user."""
    def factory():
        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = mock_user
        return session
    return factory


@pytest.fixture
def client_factory(encryptor, mock_session_factory):
    """Create a KiteClientFactory with mocked dependencies."""
    return KiteClientFactory(
        api_key="test_api_key_123",
        token_encryption=encryptor,
        db_session_factory=mock_session_factory,
    )


# ============================================================
# Task 4.5.1: Test Position Fetching
# ============================================================


class TestPositionFetching:
    """Tests for position fetching via the broker API.

    Validates:
    - Positions can be fetched through KiteClientFactory
    - Token decryption works correctly during client initialization
    - Error handling when position fetch fails
    """

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_positions_success(self, MockKiteConnect, client_factory):
        """Test that positions can be fetched via KiteClientFactory.

        Verifies end-to-end flow:
        1. Factory decrypts the user's stored access token
        2. KiteConnect client is initialized with decrypted token
        3. kite.positions() returns expected position data
        """
        # Arrange
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite

        sample_positions = {
            "net": [
                {
                    "tradingsymbol": "NIFTY2361518000CE",
                    "exchange": "NFO",
                    "quantity": 50,
                    "average_price": 120.5,
                    "last_price": 135.0,
                    "pnl": 725.0,
                    "product": "MIS",
                    "instrument_token": 12345678,
                },
                {
                    "tradingsymbol": "RELIANCE",
                    "exchange": "NSE",
                    "quantity": -10,
                    "average_price": 2450.0,
                    "last_price": 2430.0,
                    "pnl": 200.0,
                    "product": "MIS",
                    "instrument_token": 87654321,
                },
            ],
            "day": [
                {
                    "tradingsymbol": "NIFTY2361518000CE",
                    "exchange": "NFO",
                    "quantity": 50,
                    "average_price": 120.5,
                    "last_price": 135.0,
                    "pnl": 725.0,
                    "product": "MIS",
                    "instrument_token": 12345678,
                },
            ],
        }
        mock_kite.positions.return_value = sample_positions

        # Act
        client = client_factory.get_client(user_id=1)
        positions = client.positions()

        # Assert
        assert positions == sample_positions
        assert len(positions["net"]) == 2
        assert positions["net"][0]["tradingsymbol"] == "NIFTY2361518000CE"
        assert positions["net"][0]["pnl"] == 725.0
        assert positions["net"][1]["quantity"] == -10

        # Verify KiteConnect was initialized with decrypted token
        mock_kite.set_access_token.assert_called_once_with("live_access_token_abc123")

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_positions_empty(self, MockKiteConnect, client_factory):
        """Test fetching positions when user has no open positions."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.positions.return_value = {"net": [], "day": []}

        client = client_factory.get_client(user_id=1)
        positions = client.positions()

        assert positions["net"] == []
        assert positions["day"] == []

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_positions_api_error(self, MockKiteConnect, client_factory):
        """Test error handling when position fetch fails with a network error."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.positions.side_effect = Exception("Network timeout: unable to reach broker")

        client = client_factory.get_client(user_id=1)

        with pytest.raises(Exception, match="Network timeout"):
            client.positions()

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_positions_token_expired_error(self, MockKiteConnect, client_factory, mock_user):
        """Test that expired token prevents position fetching."""
        # Set token to expired
        mock_user.broker_token_expiry = datetime.now(timezone.utc) - timedelta(hours=1)

        with pytest.raises(TokenExpiredError):
            client_factory.get_client(user_id=1)

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_factory_decrypts_token_correctly(self, MockKiteConnect, client_factory):
        """Test that the factory correctly decrypts stored encrypted tokens."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite

        client_factory.get_client(user_id=1)

        # The decrypted token should be "live_access_token_abc123" (set in mock_user fixture)
        mock_kite.set_access_token.assert_called_once_with("live_access_token_abc123")

    def test_fetch_positions_no_broker_token(self, client_factory, mock_user):
        """Test error when user has no broker token stored."""
        mock_user.broker_access_token = None
        mock_user.broker_token_expiry = None

        with pytest.raises((BrokerAuthError, TokenExpiredError)):
            client_factory.get_client(user_id=1)


# ============================================================
# Task 4.5.2: Test Order Placement
# ============================================================


class TestOrderPlacement:
    """Tests for order placement via broker API.

    Validates:
    - kite.place_order() is called with correct parameters
    - Successful order returns order_id
    - Error handling for network errors and order exceptions
    """

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_place_order_success(self, MockKiteConnect, client_factory):
        """Test successful order placement returns order_id.

        Verifies that kite.place_order() is called with all correct
        parameters and returns the broker-assigned order ID.
        """
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.VARIETY_REGULAR = "regular"
        mock_kite.place_order.return_value = "220901000012345"

        client = client_factory.get_client(user_id=1)

        # Place a buy order
        order_id = client.place_order(
            variety="regular",
            exchange="NFO",
            tradingsymbol="NIFTY2361518000CE",
            transaction_type="BUY",
            quantity=50,
            product="MIS",
            order_type="MARKET",
            price=None,
        )

        # Assert order was placed successfully
        assert order_id == "220901000012345"
        mock_kite.place_order.assert_called_once_with(
            variety="regular",
            exchange="NFO",
            tradingsymbol="NIFTY2361518000CE",
            transaction_type="BUY",
            quantity=50,
            product="MIS",
            order_type="MARKET",
            price=None,
        )

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_place_order_limit(self, MockKiteConnect, client_factory):
        """Test placing a limit order with specified price."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.place_order.return_value = "220901000012346"

        client = client_factory.get_client(user_id=1)

        order_id = client.place_order(
            variety="regular",
            exchange="NSE",
            tradingsymbol="RELIANCE",
            transaction_type="SELL",
            quantity=10,
            product="MIS",
            order_type="LIMIT",
            price=2450.0,
        )

        assert order_id == "220901000012346"
        mock_kite.place_order.assert_called_once_with(
            variety="regular",
            exchange="NSE",
            tradingsymbol="RELIANCE",
            transaction_type="SELL",
            quantity=10,
            product="MIS",
            order_type="LIMIT",
            price=2450.0,
        )

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_place_order_network_error(self, MockKiteConnect, client_factory):
        """Test error handling when order placement fails due to network error."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.place_order.side_effect = Exception(
            "NetworkException: Connection timed out"
        )

        client = client_factory.get_client(user_id=1)

        with pytest.raises(Exception, match="NetworkException"):
            client.place_order(
                variety="regular",
                exchange="NFO",
                tradingsymbol="NIFTY2361518000CE",
                transaction_type="BUY",
                quantity=50,
                product="MIS",
                order_type="MARKET",
                price=None,
            )

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_place_order_insufficient_margin(self, MockKiteConnect, client_factory):
        """Test error handling when order is rejected due to insufficient margin."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.place_order.side_effect = Exception(
            "OrderException: Insufficient funds"
        )

        client = client_factory.get_client(user_id=1)

        with pytest.raises(Exception, match="Insufficient funds"):
            client.place_order(
                variety="regular",
                exchange="NFO",
                tradingsymbol="BANKNIFTY2361543000PE",
                transaction_type="BUY",
                quantity=25,
                product="MIS",
                order_type="MARKET",
                price=None,
            )

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_place_order_invalid_token_triggers_auth_error(
        self, MockKiteConnect, client_factory
    ):
        """Test that token invalidation error is handled by the factory."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.place_order.side_effect = Exception(
            "TokenException: Token is invalid or has expired"
        )

        client = client_factory.get_client(user_id=1)

        with pytest.raises(Exception, match="Token is invalid"):
            client.place_order(
                variety="regular",
                exchange="NSE",
                tradingsymbol="INFY",
                transaction_type="BUY",
                quantity=100,
                product="MIS",
                order_type="MARKET",
                price=None,
            )

        # After auth error, factory should remove client from pool
        client_factory.handle_auth_error(
            user_id=1, error=Exception("Token expired")
        )
        assert client_factory.get_pool_size() == 0


# ============================================================
# Task 4.5.3: Test Market Data Fetching
# ============================================================


class TestMarketDataFetching:
    """Tests for market data fetching via broker API.

    Validates:
    - kite.ltp() and kite.quote() are called correctly
    - Market data responses are returned properly
    - Error handling when market data fetch fails
    """

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_ltp_success(self, MockKiteConnect, client_factory):
        """Test fetching last traded price (LTP) for instruments."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite

        ltp_response = {
            "NSE:NIFTY 50": {"instrument_token": 256265, "last_price": 18650.75},
            "NSE:NIFTY BANK": {"instrument_token": 260105, "last_price": 43520.10},
        }
        mock_kite.ltp.return_value = ltp_response

        client = client_factory.get_client(user_id=1)
        result = client.ltp(["NSE:NIFTY 50", "NSE:NIFTY BANK"])

        # Assert correct data returned
        assert result["NSE:NIFTY 50"]["last_price"] == 18650.75
        assert result["NSE:NIFTY BANK"]["last_price"] == 43520.10

        # Verify ltp was called with correct instruments
        mock_kite.ltp.assert_called_once_with(["NSE:NIFTY 50", "NSE:NIFTY BANK"])

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_quote_success(self, MockKiteConnect, client_factory):
        """Test fetching full quote data for instruments."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite

        quote_response = {
            "NFO:NIFTY2361518000CE": {
                "instrument_token": 12345678,
                "last_price": 135.0,
                "volume": 1250000,
                "buy_quantity": 50000,
                "sell_quantity": 45000,
                "ohlc": {
                    "open": 120.0,
                    "high": 140.0,
                    "low": 115.0,
                    "close": 118.5,
                },
                "oi": 980000,
                "oi_day_high": 1050000,
                "oi_day_low": 950000,
            },
        }
        mock_kite.quote.return_value = quote_response

        client = client_factory.get_client(user_id=1)
        result = client.quote(["NFO:NIFTY2361518000CE"])

        # Assert full quote data returned
        assert result["NFO:NIFTY2361518000CE"]["last_price"] == 135.0
        assert result["NFO:NIFTY2361518000CE"]["volume"] == 1250000
        assert result["NFO:NIFTY2361518000CE"]["ohlc"]["high"] == 140.0
        assert result["NFO:NIFTY2361518000CE"]["oi"] == 980000

        # Verify quote was called with correct instruments
        mock_kite.quote.assert_called_once_with(["NFO:NIFTY2361518000CE"])

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_ltp_multiple_instruments(self, MockKiteConnect, client_factory):
        """Test fetching LTP for multiple instruments in a single call."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite

        ltp_response = {
            "NSE:RELIANCE": {"instrument_token": 738561, "last_price": 2450.30},
            "NSE:INFY": {"instrument_token": 408065, "last_price": 1520.75},
            "NSE:TCS": {"instrument_token": 2953217, "last_price": 3380.90},
        }
        mock_kite.ltp.return_value = ltp_response

        client = client_factory.get_client(user_id=1)
        result = client.ltp(["NSE:RELIANCE", "NSE:INFY", "NSE:TCS"])

        assert len(result) == 3
        assert result["NSE:RELIANCE"]["last_price"] == 2450.30
        assert result["NSE:INFY"]["last_price"] == 1520.75
        assert result["NSE:TCS"]["last_price"] == 3380.90

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_market_data_error(self, MockKiteConnect, client_factory):
        """Test error handling when market data fetch fails."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.ltp.side_effect = Exception(
            "DataException: Too many instruments requested"
        )

        client = client_factory.get_client(user_id=1)

        with pytest.raises(Exception, match="Too many instruments"):
            client.ltp(["NSE:NIFTY 50"])

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_quote_network_error(self, MockKiteConnect, client_factory):
        """Test error handling when quote fetch fails due to network issue."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.quote.side_effect = Exception(
            "NetworkException: Connection refused"
        )

        client = client_factory.get_client(user_id=1)

        with pytest.raises(Exception, match="Connection refused"):
            client.quote(["NFO:NIFTY2361518000CE"])

    @patch("src.broker.kite_client_factory.KiteConnect")
    def test_fetch_market_data_token_expired(self, MockKiteConnect, client_factory):
        """Test error handling when market data fetch fails due to expired token."""
        mock_kite = MagicMock()
        MockKiteConnect.return_value = mock_kite
        mock_kite.ltp.side_effect = Exception(
            "TokenException: Token is invalid or has expired"
        )

        client = client_factory.get_client(user_id=1)

        with pytest.raises(Exception, match="Token is invalid"):
            client.ltp(["NSE:NIFTY 50"])
