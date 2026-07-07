"""Property-based tests for Dhan Disconnect Clears All Credentials (Property 5).

Uses Hypothesis to verify:
- For any user with stored Dhan credentials, executing the disconnect operation
  SHALL result in all Dhan credential fields (access_token_encrypted,
  client_id_encrypted, account_name) being null and the status being "Disconnected".

**Validates: Requirements 5.7**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.base import Base
from src.database.models.user import User
from src.database.models.broker_connection import BrokerConnection
from src.broker.token_encryption import TokenEncryption
from src.services.broker_settings_service import BrokerSettingsService


# ============================================================
# Strategies
# ============================================================

# Generate non-empty credential strings (simulating encrypted token values)
credential_strategy = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=200,
)

# Generate account names (non-empty strings)
account_name_strategy = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "N")),
    min_size=1,
    max_size=50,
)

# Generate various status values that a Dhan connection might have
status_strategy = st.sampled_from(["connected", "disconnected", "error"])

# Generate optional error messages
error_message_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(codec="utf-8", categories=("L", "N", "P", "Z")),
        min_size=1,
        max_size=100,
    ),
)


# ============================================================
# Helpers
# ============================================================


def create_test_db():
    """Create a fresh in-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


def create_test_user(session: Session) -> int:
    """Insert a minimal user record and return its ID."""
    user = User(
        email="test@example.com",
        password_hash="hashed_password_placeholder",
        capital=100000.0,
        risk_profile="moderate",
    )
    session.add(user)
    session.flush()
    return user.id


# ============================================================
# Property 5: Dhan Disconnect Clears All Credentials
# ============================================================


class TestDhanDisconnectClearsAllCredentials:
    """Property-based tests for Dhan disconnect clearing all credentials.

    **Validates: Requirements 5.7**

    Core invariant:
    - For any user with stored Dhan credentials, executing the disconnect
      operation SHALL result in all Dhan credential fields
      (access_token_encrypted, client_id_encrypted, account_name) being null
      and the status being "disconnected", and error_message being null.
    """

    @given(
        access_token=credential_strategy,
        client_id=credential_strategy,
        account_name=account_name_strategy,
        status=status_strategy,
        error_message=error_message_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_disconnect_clears_all_credential_fields(
        self,
        access_token: str,
        client_id: str,
        account_name: str,
        status: str,
        error_message,
    ):
        """Disconnect always nullifies all credential fields and sets status disconnected.

        **Validates: Requirements 5.7**

        Property: For any user with stored Dhan credentials, executing the
        disconnect operation SHALL result in all Dhan credential fields
        (access_token_encrypted, client_id_encrypted, account_name) being null
        and the status being "Disconnected".
        """
        engine = create_test_db()

        with Session(engine) as session:
            # Set up: create user and a pre-existing Dhan connection
            user_id = create_test_user(session)

            connection = BrokerConnection(
                user_id=user_id,
                broker_type="dhan",
                access_token_encrypted=access_token,
                client_id_encrypted=client_id,
                account_name=account_name,
                status=status,
                error_message=error_message,
            )
            session.add(connection)
            session.commit()

            # Act: execute disconnect
            encryption_key = TokenEncryption.generate_key()
            token_encryption = TokenEncryption(encryption_key)
            service = BrokerSettingsService(token_encryption=token_encryption)

            service.disconnect_dhan(db=session, user_id=user_id)

            # Assert: all credential fields are None, status is "disconnected"
            session.refresh(connection)

            assert connection.access_token_encrypted is None, (
                f"access_token_encrypted should be None, got: "
                f"{connection.access_token_encrypted!r}"
            )
            assert connection.client_id_encrypted is None, (
                f"client_id_encrypted should be None, got: "
                f"{connection.client_id_encrypted!r}"
            )
            assert connection.account_name is None, (
                f"account_name should be None, got: {connection.account_name!r}"
            )
            assert connection.status == "disconnected", (
                f"status should be 'disconnected', got: {connection.status!r}"
            )
            assert connection.error_message is None, (
                f"error_message should be None, got: {connection.error_message!r}"
            )

        engine.dispose()

    @given(
        access_token=credential_strategy,
        client_id=credential_strategy,
        account_name=account_name_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_disconnect_is_idempotent(
        self,
        access_token: str,
        client_id: str,
        account_name: str,
    ):
        """Calling disconnect twice produces the same cleared state.

        **Validates: Requirements 5.7**

        Property: Disconnect is idempotent — calling it multiple times on the
        same user produces the same final state (all fields cleared, status
        "disconnected").
        """
        engine = create_test_db()

        with Session(engine) as session:
            # Set up: create user and Dhan connection with credentials
            user_id = create_test_user(session)

            connection = BrokerConnection(
                user_id=user_id,
                broker_type="dhan",
                access_token_encrypted=access_token,
                client_id_encrypted=client_id,
                account_name=account_name,
                status="connected",
                error_message=None,
            )
            session.add(connection)
            session.commit()

            encryption_key = TokenEncryption.generate_key()
            token_encryption = TokenEncryption(encryption_key)
            service = BrokerSettingsService(token_encryption=token_encryption)

            # First disconnect
            service.disconnect_dhan(db=session, user_id=user_id)

            # Second disconnect (should not raise or change state)
            service.disconnect_dhan(db=session, user_id=user_id)

            # Assert: still in cleared state
            session.refresh(connection)

            assert connection.access_token_encrypted is None
            assert connection.client_id_encrypted is None
            assert connection.account_name is None
            assert connection.status == "disconnected"
            assert connection.error_message is None

        engine.dispose()

    @given(
        access_token=credential_strategy,
        client_id=credential_strategy,
        account_name=account_name_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_disconnect_nonexistent_user_is_safe(
        self,
        access_token: str,
        client_id: str,
        account_name: str,
    ):
        """Disconnecting a user with no Dhan connection does not raise.

        **Validates: Requirements 5.7**

        Property: Calling disconnect_dhan for a user_id with no stored Dhan
        connection SHALL complete without error (no-op behavior).
        """
        engine = create_test_db()

        with Session(engine) as session:
            # Set up: create user but NO Dhan connection record
            user_id = create_test_user(session)
            session.commit()

            encryption_key = TokenEncryption.generate_key()
            token_encryption = TokenEncryption(encryption_key)
            service = BrokerSettingsService(token_encryption=token_encryption)

            # Act: should not raise
            service.disconnect_dhan(db=session, user_id=user_id)

            # Assert: no Dhan connection exists for this user (still None)
            from sqlalchemy import select
            result = session.execute(
                select(BrokerConnection).where(
                    BrokerConnection.user_id == user_id,
                    BrokerConnection.broker_type == "dhan",
                )
            ).scalar_one_or_none()

            assert result is None, (
                "No Dhan connection should exist after disconnect on non-existent record"
            )

        engine.dispose()
