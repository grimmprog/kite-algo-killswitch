"""
Manual Integration Test for Phase 1 - Web Trading Platform
============================================================
This script tests all Phase 1 components against real PostgreSQL and Redis.

Prerequisites:
- PostgreSQL running on localhost:5432 with database 'trading_platform'
- Redis running on localhost:6379
- Alembic migration already applied (alembic upgrade head)

Run: python manual_test_phase1.py
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta

# Load .env
from dotenv import load_dotenv
load_dotenv()

# Ensure src is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_pass(msg):
    print(f"  ✅ {msg}")


def print_fail(msg):
    print(f"  ❌ {msg}")


def print_info(msg):
    print(f"  ℹ️  {msg}")


# ============================================================
# TEST 1: Database Connection & Models
# ============================================================
def test_database():
    print_header("TEST 1: PostgreSQL Database & Models")

    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import Session
    from src.database.base import Base
    from src.database.models import User, Trade, Position, Order, KillSwitchLog

    db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/trading_platform")
    engine = create_engine(db_url)

    # Check connection
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print_pass(f"Connected to PostgreSQL: {db_url.split('@')[1]}")
    except Exception as e:
        print_fail(f"Cannot connect to PostgreSQL: {e}")
        return False

    # Check tables exist
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    expected = {"users", "trades", "positions", "orders", "killswitch_logs", "alembic_version"}
    if expected.issubset(set(tables)):
        print_pass(f"All tables present: {', '.join(sorted(expected - {'alembic_version'}))}")
    else:
        missing = expected - set(tables)
        print_fail(f"Missing tables: {missing}")
        return False

    # Insert a test user
    with Session(engine) as session:
        # Clean up previous test data
        session.execute(text("DELETE FROM killswitch_logs WHERE user_id IN (SELECT id FROM users WHERE email = 'test@phase1.com')"))
        session.execute(text("DELETE FROM orders WHERE user_id IN (SELECT id FROM users WHERE email = 'test@phase1.com')"))
        session.execute(text("DELETE FROM trades WHERE user_id IN (SELECT id FROM users WHERE email = 'test@phase1.com')"))
        session.execute(text("DELETE FROM positions WHERE user_id IN (SELECT id FROM users WHERE email = 'test@phase1.com')"))
        session.execute(text("DELETE FROM users WHERE email = 'test@phase1.com'"))
        session.commit()

        from src.auth.password import hash_password
        user = User(
            email="test@phase1.com",
            password_hash=hash_password("TestPass123"),
            capital=100000.0,
            risk_profile="moderate",
            daily_loss_limit_percent=2.0,
            max_trade_risk_percent=1.0,
        )
        session.add(user)
        session.commit()
        user_id = user.id
        print_pass(f"Created test user (id={user_id}, email=test@phase1.com)")

        # Insert a trade
        trade = Trade(
            user_id=user_id,
            symbol="NIFTY2361518000CE",
            exchange="NFO",
            qty=50,
            side="BUY",
            entry_price=120.5,
            status="OPEN",
        )
        session.add(trade)
        session.commit()
        print_pass(f"Created test trade (id={trade.id}, symbol={trade.symbol})")

        # Insert a position
        pos = Position(
            user_id=user_id,
            net_delta=0.5,
            net_gamma=0.02,
            net_vega=150.0,
            margin_used=25000.0,
            unrealized_pnl=725.0,
        )
        session.add(pos)
        session.commit()
        print_pass(f"Created test position (delta={pos.net_delta}, margin={pos.margin_used})")

        # Insert an order
        order = Order(
            user_id=user_id,
            symbol="NIFTY2361518000CE",
            qty=50,
            status="COMPLETE",
            broker_order_id="220901000012345",
            price=120.5,
        )
        session.add(order)
        session.commit()
        print_pass(f"Created test order (id={order.id}, status={order.status})")

        # Insert a killswitch log
        ks_log = KillSwitchLog(
            user_id=user_id,
            trigger_reason="Manual test: daily loss limit exceeded",
            loss_percent=2.5,
            capital_at_trigger=97500.0,
            positions_closed_count=1,
        )
        session.add(ks_log)
        session.commit()
        print_pass(f"Created killswitch log (reason={ks_log.trigger_reason[:30]}...)")

    # Verify constraints work
    with Session(engine) as session:
        try:
            bad_user = User(
                email="test@phase1.com",  # Duplicate!
                password_hash=hash_password("AnotherPass1"),
                capital=50000.0,
                risk_profile="moderate",
                daily_loss_limit_percent=2.0,
                max_trade_risk_percent=1.0,
            )
            session.add(bad_user)
            session.commit()
            print_fail("Duplicate email should have been rejected!")
        except Exception:
            session.rollback()
            print_pass("Unique email constraint enforced correctly")

    engine.dispose()
    return True


# ============================================================
# TEST 2: Redis Connection & Operations
# ============================================================
def test_redis():
    print_header("TEST 2: Redis Connection & Cache Operations")

    from src.cache import get_redis_client, RedisKeys, RiskMetrics, TTL, reset_redis_client

    reset_redis_client()
    client = get_redis_client(url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

    # Ping
    if client.ping():
        print_pass("Connected to Redis (PING -> PONG)")
    else:
        print_fail("Cannot connect to Redis")
        return False

    # Test set/get
    client.set("test:phase1:hello", "world", ttl=30)
    value = client.get("test:phase1:hello")
    if value == "world":
        print_pass("SET/GET working: test:phase1:hello = 'world'")
    else:
        print_fail(f"SET/GET failed, got: {value}")

    # Test hash operations (risk metrics)
    user_id = 42
    risk_key = RedisKeys.user_risk(user_id)
    metrics = RiskMetrics(
        pnl=-1500.0,
        net_delta=0.45,
        net_gamma=0.02,
        net_vega=150.0,
        margin_used=50000.0,
    )
    client.hset(risk_key, metrics.to_redis_hash())
    stored = client.hgetall(risk_key)
    if stored.get("pnl") == "-1500.0" and stored.get("net_delta") == "0.45":
        print_pass(f"Hash ops working: {risk_key} -> pnl=-1500.0, delta=0.45")
    else:
        print_fail(f"Hash ops failed, got: {stored}")

    # Test RiskMetrics roundtrip
    restored = RiskMetrics.from_redis_hash(stored)
    if restored.pnl == -1500.0 and restored.net_delta == 0.45:
        print_pass("RiskMetrics roundtrip: serialize -> Redis -> deserialize ✓")
    else:
        print_fail(f"RiskMetrics roundtrip failed: {restored}")

    # Test killswitch flag
    ks_key = RedisKeys.user_killswitch(user_id)
    client.set(ks_key, "true")
    if client.get(ks_key) == "true":
        print_pass(f"Kill switch flag: {ks_key} = 'true'")
    else:
        print_fail("Kill switch flag set/get failed")

    # Test list operations (recent orders)
    orders_key = RedisKeys.user_recent_orders(user_id)
    client.delete(orders_key)
    client.lpush(orders_key, "NIFTY:BUY:50", "RELIANCE:SELL:10")
    client.expire(orders_key, TTL.RECENT_ORDERS)
    orders = client.lrange(orders_key, 0, -1)
    if len(orders) == 2:
        print_pass(f"List ops working: {orders_key} -> {orders}")
    else:
        print_fail(f"List ops failed, got: {orders}")

    # Test TTL
    ttl_val = client.ttl(orders_key)
    if 0 < ttl_val <= TTL.RECENT_ORDERS:
        print_pass(f"TTL working: {orders_key} expires in {ttl_val}s (max {TTL.RECENT_ORDERS}s)")
    else:
        print_fail(f"TTL check failed, got: {ttl_val}")

    # Test market data key
    market_key = RedisKeys.market_data("NIFTY")
    import json
    market_data = json.dumps({
        "spot": 18650.75,
        "vwap": 18645.30,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    client.set(market_key, market_data, ttl=TTL.MARKET_DATA)
    retrieved = client.get(market_key)
    parsed = json.loads(retrieved)
    if parsed["spot"] == 18650.75:
        print_pass(f"Market data cached: {market_key} -> spot=18650.75, TTL={TTL.MARKET_DATA}s")
    else:
        print_fail(f"Market data caching failed: {parsed}")

    # Cleanup
    client.delete("test:phase1:hello")
    client.delete(risk_key)
    client.delete(ks_key)
    client.delete(orders_key)
    client.delete(market_key)
    print_pass("Cleaned up all test keys")

    reset_redis_client()
    return True


# ============================================================
# TEST 3: Authentication System
# ============================================================
def test_auth():
    print_header("TEST 3: Authentication (JWT + bcrypt)")

    from src.auth import JWTHandler, hash_password, verify_password

    secret = os.environ.get("JWT_SECRET_KEY", "test-secret")
    handler = JWTHandler(secret_key=secret)

    # Test password hashing
    password = "MySecureTrading123"
    hashed = hash_password(password)
    if hashed.startswith("$2b$12$"):
        print_pass(f"Password hashed with bcrypt cost 12: {hashed[:20]}...")
    else:
        print_fail(f"Unexpected hash format: {hashed}")

    if verify_password(password, hashed):
        print_pass("Password verification: correct password accepted")
    else:
        print_fail("Password verification failed for correct password")

    if not verify_password("WrongPassword1", hashed):
        print_pass("Password verification: wrong password rejected")
    else:
        print_fail("Wrong password was accepted!")

    # Test short password rejection
    try:
        hash_password("short")
        print_fail("Short password (<8 chars) should be rejected")
    except ValueError:
        print_pass("Short password (<8 chars) correctly rejected")

    # Test JWT access token
    access_token = handler.create_access_token(user_id=1)
    payload = handler.verify_token(access_token)
    if payload["sub"] == "1" and payload["type"] == "access":
        print_pass(f"Access token created: type=access, sub=1, expires in 24h")
    else:
        print_fail(f"Access token payload incorrect: {payload}")

    # Test JWT refresh token
    refresh_token = handler.create_refresh_token(user_id=1)
    payload = handler.verify_token(refresh_token)
    if payload["sub"] == "1" and payload["type"] == "refresh":
        print_pass(f"Refresh token created: type=refresh, sub=1, expires in 30d")
    else:
        print_fail(f"Refresh token payload incorrect: {payload}")

    # Test user_id extraction
    extracted = handler.extract_user_id(access_token)
    if extracted == 1:
        print_pass(f"User ID extracted from token: {extracted}")
    else:
        print_fail(f"User ID extraction failed: got {extracted}")

    # Test expired token rejection
    import jwt as pyjwt
    expired_payload = {
        "sub": "1", "type": "access",
        "iat": datetime.now(timezone.utc) - timedelta(hours=25),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    expired_token = pyjwt.encode(expired_payload, secret, algorithm="HS256")
    try:
        handler.verify_token(expired_token)
        print_fail("Expired token should be rejected")
    except pyjwt.ExpiredSignatureError:
        print_pass("Expired token correctly rejected")

    # Test tampered token rejection
    tampered = access_token[:-1] + ("X" if access_token[-1] != "X" else "Y")
    try:
        handler.verify_token(tampered)
        print_fail("Tampered token should be rejected")
    except pyjwt.InvalidTokenError:
        print_pass("Tampered token correctly rejected")

    return True


# ============================================================
# TEST 4: Broker Token Encryption
# ============================================================
def test_broker_encryption():
    print_header("TEST 4: Broker Token Encryption (Fernet)")

    from src.broker import TokenEncryption

    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        key = TokenEncryption.generate_key()
        print_info(f"No ENCRYPTION_KEY in env, generated: {key[:20]}...")

    enc = TokenEncryption(key)

    # Encrypt a token
    broker_token = "kite_access_token_abc123xyz"
    encrypted = enc.encrypt(broker_token)
    if encrypted != broker_token:
        print_pass(f"Token encrypted: {broker_token[:15]}... -> {encrypted[:25]}...")
    else:
        print_fail("Encryption produced same output as input!")

    # Decrypt
    decrypted = enc.decrypt(encrypted)
    if decrypted == broker_token:
        print_pass(f"Token decrypted correctly: {decrypted}")
    else:
        print_fail(f"Decryption failed: got {decrypted}")

    # Same plaintext gives different ciphertext (random IV)
    encrypted2 = enc.encrypt(broker_token)
    if encrypted != encrypted2:
        print_pass("Different ciphertext for same plaintext (random IV)")
    else:
        print_fail("Same ciphertext produced - Fernet should use random IV")

    # Wrong key fails
    from src.broker import TokenEncryptionError
    wrong_enc = TokenEncryption(TokenEncryption.generate_key())
    try:
        wrong_enc.decrypt(encrypted)
        print_fail("Wrong key should fail decryption")
    except TokenEncryptionError:
        print_pass("Wrong key correctly rejected during decryption")

    return True


# ============================================================
# TEST 5: End-to-End Auth Flow (with real DB)
# ============================================================
def test_auth_flow_e2e():
    print_header("TEST 5: End-to-End Auth Flow (DB + JWT + bcrypt)")

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from src.database.models import User
    from src.auth import JWTHandler, hash_password
    from src.auth.service import AuthService
    from src.auth.exceptions import AuthenticationError

    db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/trading_platform")
    engine = create_engine(db_url)
    secret = os.environ.get("JWT_SECRET_KEY", "test-secret")
    handler = JWTHandler(secret_key=secret)

    # Setup: create a fresh user
    with Session(engine) as session:
        session.execute(text("DELETE FROM users WHERE email = 'e2e@test.com'"))
        session.commit()

        user = User(
            email="e2e@test.com",
            password_hash=hash_password("E2ETestPass99"),
            capital=200000.0,
            risk_profile="aggressive",
            daily_loss_limit_percent=5.0,
            max_trade_risk_percent=2.5,
        )
        session.add(user)
        session.commit()
        user_id = user.id
        print_pass(f"Created user for E2E test (id={user_id})")

    # Test login
    with Session(engine) as session:
        service = AuthService(jwt_handler=handler, db_session=session)

        result = service.authenticate_user("e2e@test.com", "E2ETestPass99")
        if result["user_id"] == user_id and "access_token" in result:
            print_pass(f"Login successful: user_id={result['user_id']}, token_type={result['token_type']}")
        else:
            print_fail(f"Login result unexpected: {result}")
            return False

        # Verify the access token works
        extracted_id = handler.extract_user_id(result["access_token"])
        if extracted_id == user_id:
            print_pass(f"Access token valid: extract_user_id -> {extracted_id}")
        else:
            print_fail(f"Access token user_id mismatch: {extracted_id}")

    # Test token refresh
    with Session(engine) as session:
        service = AuthService(jwt_handler=handler, db_session=session)
        refresh_result = service.refresh_access_token(result["refresh_token"])
        if "access_token" in refresh_result:
            new_id = handler.extract_user_id(refresh_result["access_token"])
            if new_id == user_id:
                print_pass(f"Token refresh successful: new access token for user {new_id}")
            else:
                print_fail(f"Refreshed token has wrong user_id: {new_id}")
        else:
            print_fail(f"Token refresh failed: {refresh_result}")

    # Test wrong password
    with Session(engine) as session:
        service = AuthService(jwt_handler=handler, db_session=session)
        try:
            service.authenticate_user("e2e@test.com", "WrongPassword1")
            print_fail("Wrong password should raise AuthenticationError")
        except AuthenticationError:
            print_pass("Wrong password correctly rejected")

    # Test logout
    with Session(engine) as session:
        service = AuthService(jwt_handler=handler, db_session=session)
        if service.logout(user_id):
            print_pass(f"Logout successful for user {user_id}")
        else:
            print_fail("Logout returned False")

    # Cleanup
    with Session(engine) as session:
        session.execute(text("DELETE FROM users WHERE email = 'e2e@test.com'"))
        session.commit()

    engine.dispose()
    return True


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("\n" + "🚀 " * 20)
    print("  PHASE 1 MANUAL INTEGRATION TESTS")
    print("  Web Trading Platform - Foundation & Infrastructure")
    print("🚀 " * 20)

    results = []

    results.append(("PostgreSQL & Models", test_database()))
    results.append(("Redis & Cache", test_redis()))
    results.append(("Authentication", test_auth()))
    results.append(("Broker Encryption", test_broker_encryption()))
    results.append(("E2E Auth Flow", test_auth_flow_e2e()))

    print_header("RESULTS SUMMARY")
    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}  {name}")

    print(f"\n  {passed}/{total} test groups passed")

    if passed == total:
        print("\n  🎉 ALL PHASE 1 INTEGRATION TESTS PASSED!")
    else:
        print("\n  ⚠️  Some tests failed. Check output above.")

    sys.exit(0 if passed == total else 1)
