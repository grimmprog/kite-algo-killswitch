"""Tests for Alembic migration schema verification.

Verifies that:
1. All models can be imported and tables created via Base.metadata.create_all()
2. All expected tables exist (users, trades, positions, orders, killswitch_logs)
3. All expected columns exist on each table
4. Constraints (foreign keys, unique, nullable) are present
5. The migration script is syntactically correct and importable

Note: Some PostgreSQL-specific features (triggers, CHECK constraints with
TRIM/LENGTH) won't work in SQLite. Tests handle SQLite limitations gracefully.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from src.database.base import Base
from src.database.models import User, Trade, Position, Order, KillSwitchLog


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def inspector(engine):
    """Return a SQLAlchemy inspector for the in-memory database."""
    return inspect(engine)


@pytest.fixture
def session(engine):
    """Create a session for testing data operations."""
    with Session(engine) as session:
        yield session


class TestMigrationScriptImportable:
    """Verify the migration script is syntactically correct."""

    def test_migration_module_importable(self):
        """Migration script can be imported without errors."""
        import importlib.util

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "001_initial_schema.py",
        )
        spec = importlib.util.spec_from_file_location(
            "migration_001", os.path.abspath(migration_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Verify it has the expected Alembic attributes
        assert hasattr(module, "revision")
        assert hasattr(module, "down_revision")
        assert hasattr(module, "upgrade")
        assert hasattr(module, "downgrade")
        assert module.revision == "a001"
        assert module.down_revision is None

    def test_migration_upgrade_is_callable(self):
        """The upgrade function in the migration is callable."""
        import importlib.util

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "001_initial_schema.py",
        )
        spec = importlib.util.spec_from_file_location(
            "migration_001", os.path.abspath(migration_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert callable(module.upgrade)
        assert callable(module.downgrade)


class TestAllTablesExist:
    """Verify all expected tables are created."""

    def test_users_table_exists(self, inspector):
        assert "users" in inspector.get_table_names()

    def test_trades_table_exists(self, inspector):
        assert "trades" in inspector.get_table_names()

    def test_positions_table_exists(self, inspector):
        assert "positions" in inspector.get_table_names()

    def test_orders_table_exists(self, inspector):
        assert "orders" in inspector.get_table_names()

    def test_killswitch_logs_table_exists(self, inspector):
        assert "killswitch_logs" in inspector.get_table_names()

    def test_exactly_five_tables(self, inspector):
        tables = inspector.get_table_names()
        expected = {"users", "trades", "positions", "orders", "killswitch_logs"}
        assert expected == set(tables)


class TestUsersTableColumns:
    """Verify all columns exist on the users table."""

    EXPECTED_COLUMNS = [
        "id",
        "email",
        "password_hash",
        "capital",
        "risk_profile",
        "daily_loss_limit_percent",
        "max_trade_risk_percent",
        "killswitch_state",
        "broker_access_token",
        "broker_refresh_token",
        "broker_token_expiry",
        "created_at",
        "last_login",
        "is_active",
    ]

    def test_all_columns_present(self, inspector):
        columns = [col["name"] for col in inspector.get_columns("users")]
        for expected_col in self.EXPECTED_COLUMNS:
            assert expected_col in columns, f"Missing column: {expected_col}"

    def test_id_is_primary_key(self, inspector):
        pk = inspector.get_pk_constraint("users")
        assert "id" in pk["constrained_columns"]

    def test_email_not_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("users")}
        assert columns["email"]["nullable"] is False

    def test_password_hash_not_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("users")}
        assert columns["password_hash"]["nullable"] is False

    def test_capital_not_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("users")}
        assert columns["capital"]["nullable"] is False

    def test_broker_tokens_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("users")}
        assert columns["broker_access_token"]["nullable"] is True
        assert columns["broker_refresh_token"]["nullable"] is True
        assert columns["broker_token_expiry"]["nullable"] is True

    def test_email_unique_constraint(self, inspector):
        # Check unique constraints first
        unique_constraints = inspector.get_unique_constraints("users")
        email_unique = any(
            "email" in uc["column_names"] for uc in unique_constraints
        )
        # SQLite may enforce uniqueness via a unique index instead of a named constraint
        if not email_unique:
            indexes = inspector.get_indexes("users")
            email_unique = any(
                "email" in idx["column_names"] and idx.get("unique", False)
                for idx in indexes
            )
        assert email_unique, "Email should have a unique constraint (via constraint or unique index)"


class TestTradesTableColumns:
    """Verify all columns exist on the trades table."""

    EXPECTED_COLUMNS = [
        "id",
        "user_id",
        "symbol",
        "exchange",
        "qty",
        "side",
        "entry_price",
        "exit_price",
        "pnl",
        "margin_used",
        "risk_snapshot_json",
        "status",
        "timestamp",
        "exit_timestamp",
    ]

    def test_all_columns_present(self, inspector):
        columns = [col["name"] for col in inspector.get_columns("trades")]
        for expected_col in self.EXPECTED_COLUMNS:
            assert expected_col in columns, f"Missing column: {expected_col}"

    def test_id_is_primary_key(self, inspector):
        pk = inspector.get_pk_constraint("trades")
        assert "id" in pk["constrained_columns"]

    def test_user_id_foreign_key(self, inspector):
        fks = inspector.get_foreign_keys("trades")
        user_fk = [fk for fk in fks if fk["referred_table"] == "users"]
        assert len(user_fk) > 0, "trades should have FK to users"
        assert "user_id" in user_fk[0]["constrained_columns"]

    def test_symbol_not_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("trades")}
        assert columns["symbol"]["nullable"] is False

    def test_exit_price_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("trades")}
        assert columns["exit_price"]["nullable"] is True

    def test_exit_timestamp_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("trades")}
        assert columns["exit_timestamp"]["nullable"] is True


class TestPositionsTableColumns:
    """Verify all columns exist on the positions table."""

    EXPECTED_COLUMNS = [
        "id",
        "user_id",
        "net_delta",
        "net_gamma",
        "net_vega",
        "margin_used",
        "unrealized_pnl",
        "updated_at",
    ]

    def test_all_columns_present(self, inspector):
        columns = [col["name"] for col in inspector.get_columns("positions")]
        for expected_col in self.EXPECTED_COLUMNS:
            assert expected_col in columns, f"Missing column: {expected_col}"

    def test_id_is_primary_key(self, inspector):
        pk = inspector.get_pk_constraint("positions")
        assert "id" in pk["constrained_columns"]

    def test_user_id_foreign_key(self, inspector):
        fks = inspector.get_foreign_keys("positions")
        user_fk = [fk for fk in fks if fk["referred_table"] == "users"]
        assert len(user_fk) > 0, "positions should have FK to users"
        assert "user_id" in user_fk[0]["constrained_columns"]

    def test_user_id_unique(self, inspector):
        unique_constraints = inspector.get_unique_constraints("positions")
        user_id_unique = any(
            "user_id" in uc["column_names"] for uc in unique_constraints
        )
        assert user_id_unique, "user_id should have a unique constraint on positions"


class TestOrdersTableColumns:
    """Verify all columns exist on the orders table."""

    EXPECTED_COLUMNS = [
        "id",
        "user_id",
        "broker_order_id",
        "symbol",
        "qty",
        "price",
        "status",
        "retries",
        "error_message",
        "timestamp",
    ]

    def test_all_columns_present(self, inspector):
        columns = [col["name"] for col in inspector.get_columns("orders")]
        for expected_col in self.EXPECTED_COLUMNS:
            assert expected_col in columns, f"Missing column: {expected_col}"

    def test_id_is_primary_key(self, inspector):
        pk = inspector.get_pk_constraint("orders")
        assert "id" in pk["constrained_columns"]

    def test_user_id_foreign_key(self, inspector):
        fks = inspector.get_foreign_keys("orders")
        user_fk = [fk for fk in fks if fk["referred_table"] == "users"]
        assert len(user_fk) > 0, "orders should have FK to users"
        assert "user_id" in user_fk[0]["constrained_columns"]

    def test_broker_order_id_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("orders")}
        assert columns["broker_order_id"]["nullable"] is True

    def test_price_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("orders")}
        assert columns["price"]["nullable"] is True

    def test_error_message_nullable(self, inspector):
        columns = {col["name"]: col for col in inspector.get_columns("orders")}
        assert columns["error_message"]["nullable"] is True


class TestKillswitchLogsTableColumns:
    """Verify all columns exist on the killswitch_logs table."""

    EXPECTED_COLUMNS = [
        "id",
        "user_id",
        "trigger_reason",
        "loss_percent",
        "capital_at_trigger",
        "positions_closed_count",
        "timestamp",
    ]

    def test_all_columns_present(self, inspector):
        columns = [col["name"] for col in inspector.get_columns("killswitch_logs")]
        for expected_col in self.EXPECTED_COLUMNS:
            assert expected_col in columns, f"Missing column: {expected_col}"

    def test_id_is_primary_key(self, inspector):
        pk = inspector.get_pk_constraint("killswitch_logs")
        assert "id" in pk["constrained_columns"]

    def test_user_id_foreign_key(self, inspector):
        fks = inspector.get_foreign_keys("killswitch_logs")
        user_fk = [fk for fk in fks if fk["referred_table"] == "users"]
        assert len(user_fk) > 0, "killswitch_logs should have FK to users"
        assert "user_id" in user_fk[0]["constrained_columns"]

    def test_trigger_reason_not_nullable(self, inspector):
        columns = {
            col["name"]: col for col in inspector.get_columns("killswitch_logs")
        }
        assert columns["trigger_reason"]["nullable"] is False

    def test_loss_percent_nullable(self, inspector):
        columns = {
            col["name"]: col for col in inspector.get_columns("killswitch_logs")
        }
        assert columns["loss_percent"]["nullable"] is True

    def test_capital_at_trigger_nullable(self, inspector):
        columns = {
            col["name"]: col for col in inspector.get_columns("killswitch_logs")
        }
        assert columns["capital_at_trigger"]["nullable"] is True


class TestSchemaUpAndDown:
    """Test that schema can be created and dropped (simulating up/down)."""

    def test_create_all_succeeds(self):
        """Simulates 'upgrade' - creating all tables from scratch."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        # Should not raise
        Base.metadata.create_all(engine)

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert len(tables) == 5
        engine.dispose()

    def test_drop_all_succeeds(self):
        """Simulates 'downgrade' - dropping all tables."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        # Verify tables exist
        inspector = inspect(engine)
        assert len(inspector.get_table_names()) == 5

        # Drop all tables (simulates downgrade)
        Base.metadata.drop_all(engine)

        # Verify tables are gone
        inspector = inspect(engine)
        assert len(inspector.get_table_names()) == 0
        engine.dispose()

    def test_create_drop_create_idempotent(self):
        """Schema can be recreated after dropping (up-down-up cycle)."""
        engine = create_engine("sqlite:///:memory:", echo=False)

        # First up
        Base.metadata.create_all(engine)
        assert len(inspect(engine).get_table_names()) == 5

        # Down
        Base.metadata.drop_all(engine)
        assert len(inspect(engine).get_table_names()) == 0

        # Second up
        Base.metadata.create_all(engine)
        assert len(inspect(engine).get_table_names()) == 5

        engine.dispose()


class TestForeignKeyRelationships:
    """Verify foreign key cascade relationships work."""

    def test_trades_references_users(self, inspector):
        fks = inspector.get_foreign_keys("trades")
        user_fks = [fk for fk in fks if fk["referred_table"] == "users"]
        assert len(user_fks) == 1
        assert user_fks[0]["referred_columns"] == ["id"]

    def test_positions_references_users(self, inspector):
        fks = inspector.get_foreign_keys("positions")
        user_fks = [fk for fk in fks if fk["referred_table"] == "users"]
        assert len(user_fks) == 1
        assert user_fks[0]["referred_columns"] == ["id"]

    def test_orders_references_users(self, inspector):
        fks = inspector.get_foreign_keys("orders")
        user_fks = [fk for fk in fks if fk["referred_table"] == "users"]
        assert len(user_fks) == 1
        assert user_fks[0]["referred_columns"] == ["id"]

    def test_killswitch_logs_references_users(self, inspector):
        fks = inspector.get_foreign_keys("killswitch_logs")
        user_fks = [fk for fk in fks if fk["referred_table"] == "users"]
        assert len(user_fks) == 1
        assert user_fks[0]["referred_columns"] == ["id"]


class TestDataInsertionIntegrity:
    """Test that data can be inserted following schema constraints."""

    def test_insert_user(self, session):
        """Can insert a valid user record."""
        user = User(
            email="test@example.com",
            password_hash="$2b$12$hashedpassword",
            capital=100000.0,
            risk_profile="moderate",
            daily_loss_limit_percent=2.0,
            max_trade_risk_percent=1.0,
        )
        session.add(user)
        session.commit()

        assert user.id is not None
        assert user.email == "test@example.com"

    def test_insert_trade_with_user(self, session):
        """Can insert a trade linked to a user."""
        user = User(
            email="trader@example.com",
            password_hash="$2b$12$hashedpassword",
            capital=50000.0,
            risk_profile="aggressive",
            daily_loss_limit_percent=5.0,
            max_trade_risk_percent=2.0,
        )
        session.add(user)
        session.commit()

        trade = Trade(
            user_id=user.id,
            symbol="RELIANCE",
            exchange="NSE",
            qty=10,
            side="BUY",
            entry_price=2500.0,
            status="OPEN",
        )
        session.add(trade)
        session.commit()

        assert trade.id is not None
        assert trade.user_id == user.id

    def test_insert_position_with_user(self, session):
        """Can insert a position record for a user."""
        user = User(
            email="pos@example.com",
            password_hash="$2b$12$hashedpassword",
            capital=75000.0,
            risk_profile="conservative",
            daily_loss_limit_percent=1.0,
            max_trade_risk_percent=0.5,
        )
        session.add(user)
        session.commit()

        position = Position(
            user_id=user.id,
            net_delta=0.5,
            net_gamma=0.1,
            net_vega=0.2,
            margin_used=5000.0,
            unrealized_pnl=200.0,
        )
        session.add(position)
        session.commit()

        assert position.id is not None
        assert position.user_id == user.id

    def test_insert_order_with_user(self, session):
        """Can insert an order linked to a user."""
        user = User(
            email="order@example.com",
            password_hash="$2b$12$hashedpassword",
            capital=60000.0,
            risk_profile="moderate",
            daily_loss_limit_percent=3.0,
            max_trade_risk_percent=1.5,
        )
        session.add(user)
        session.commit()

        order = Order(
            user_id=user.id,
            symbol="NIFTY23DECCE",
            qty=50,
            price=150.0,
            status="PENDING",
        )
        session.add(order)
        session.commit()

        assert order.id is not None
        assert order.user_id == user.id

    def test_insert_killswitch_log_with_user(self, session):
        """Can insert a killswitch log linked to a user."""
        user = User(
            email="ks@example.com",
            password_hash="$2b$12$hashedpassword",
            capital=80000.0,
            risk_profile="moderate",
            daily_loss_limit_percent=2.0,
            max_trade_risk_percent=1.0,
        )
        session.add(user)
        session.commit()

        log = KillSwitchLog(
            user_id=user.id,
            trigger_reason="Daily loss limit exceeded",
            loss_percent=2.5,
            capital_at_trigger=78000.0,
            positions_closed_count=3,
        )
        session.add(log)
        session.commit()

        assert log.id is not None
        assert log.user_id == user.id
        assert log.trigger_reason == "Daily loss limit exceeded"
