"""Tests for Admin Users API (src/admin/api/users.py).

Tests cover:
- GET /admin/api/users: list all users
- POST /admin/api/users: create a new user
- PUT /admin/api/users/{user_id}: update a user
- DELETE /admin/api/users/{user_id}: delete a user
- Validation of request bodies
- Error handling for database failures
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.admin.api.users import router
from src.admin.dependencies import get_db


# ============================================================
# Fixtures
# ============================================================


def _create_test_app():
    """Create a fresh FastAPI app with the users router."""
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_user(id=1, email="test@example.com", capital=100000.0,
               risk_profile="moderate", daily_loss_limit_percent=2.0,
               killswitch_state=False, is_active=True):
    """Create a mock user object with specified attributes."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.capital = capital
    user.risk_profile = risk_profile
    user.daily_loss_limit_percent = daily_loss_limit_percent
    user.killswitch_state = killswitch_state
    user.is_active = is_active
    return user


# ============================================================
# Tests for GET /admin/api/users
# ============================================================


class TestListUsers:
    """Tests for listing users."""

    def test_list_returns_all_users(self):
        """GET /admin/api/users returns all users."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [
            _mock_user(id=1, email="user1@test.com"),
            _mock_user(id=2, email="user2@test.com"),
        ]
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/users")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["email"] == "user1@test.com"
        assert data[1]["email"] == "user2@test.com"
        app.dependency_overrides.clear()

    def test_list_returns_empty_list(self):
        """GET /admin/api/users returns empty list when no users exist."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = []
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/users")

        assert response.status_code == 200
        assert response.json() == []
        app.dependency_overrides.clear()

    def test_list_returns_500_on_db_error(self):
        """GET /admin/api/users returns 500 on database failure."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Connection timeout")
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.get("/api/users")

        assert response.status_code == 500
        app.dependency_overrides.clear()


# ============================================================
# Tests for POST /admin/api/users
# ============================================================


class TestCreateUser:
    """Tests for creating users."""

    @patch("src.admin.api.users.hash_password")
    def test_create_user_success(self, mock_hash):
        """POST /admin/api/users creates a user and returns 201."""
        mock_hash.return_value = "hashed_pw"
        app = _create_test_app()
        mock_db = MagicMock()
        # After add/commit/refresh, the user object has an id
        def refresh_user(user):
            user.id = 1
            user.email = "new@test.com"
            user.capital = 100000.0
            user.risk_profile = "moderate"
            user.daily_loss_limit_percent = 2.0
            user.killswitch_state = False
            user.is_active = True

        mock_db.refresh.side_effect = refresh_user
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/users", json={
            "email": "new@test.com",
            "password": "SecurePass123",
            "capital": 100000.0,
            "risk_profile": "moderate",
            "daily_loss_limit_percent": 2.0,
        })

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@test.com"
        assert data["capital"] == 100000.0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        app.dependency_overrides.clear()

    def test_create_user_invalid_capital(self):
        """POST /admin/api/users rejects negative capital."""
        app = _create_test_app()
        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/users", json={
            "email": "new@test.com",
            "password": "SecurePass123",
            "capital": -1000,
        })

        assert response.status_code == 422
        app.dependency_overrides.clear()

    def test_create_user_invalid_risk_profile(self):
        """POST /admin/api/users rejects invalid risk profile."""
        app = _create_test_app()
        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/users", json={
            "email": "new@test.com",
            "password": "SecurePass123",
            "risk_profile": "extreme",
        })

        assert response.status_code == 422
        app.dependency_overrides.clear()

    def test_create_user_invalid_daily_loss_limit(self):
        """POST /admin/api/users rejects out-of-range daily loss limit."""
        app = _create_test_app()
        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/users", json={
            "email": "new@test.com",
            "password": "SecurePass123",
            "daily_loss_limit_percent": 15.0,
        })

        assert response.status_code == 422
        app.dependency_overrides.clear()

    @patch("src.admin.api.users.hash_password")
    def test_create_user_db_error_returns_500(self, mock_hash):
        """POST /admin/api/users returns 500 on database error."""
        mock_hash.return_value = "hashed_pw"
        app = _create_test_app()
        mock_db = MagicMock()
        mock_db.commit.side_effect = Exception("Integrity error")
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.post("/api/users", json={
            "email": "new@test.com",
            "password": "SecurePass123",
        })

        assert response.status_code == 500
        mock_db.rollback.assert_called_once()
        app.dependency_overrides.clear()


# ============================================================
# Tests for PUT /admin/api/users/{user_id}
# ============================================================


class TestUpdateUser:
    """Tests for updating users."""

    def test_update_user_success(self):
        """PUT /admin/api/users/{id} updates user fields."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_user = _mock_user(id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        def refresh_user(user):
            user.capital = 200000.0

        mock_db.refresh.side_effect = refresh_user
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.put("/api/users/1", json={"capital": 200000.0})

        assert response.status_code == 200
        mock_db.commit.assert_called_once()
        app.dependency_overrides.clear()

    def test_update_user_not_found(self):
        """PUT /admin/api/users/{id} returns 404 for non-existent user."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.put("/api/users/999", json={"capital": 200000.0})

        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_update_user_invalid_capital(self):
        """PUT /admin/api/users/{id} rejects invalid capital."""
        app = _create_test_app()
        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.put("/api/users/1", json={"capital": -500})

        assert response.status_code == 422
        app.dependency_overrides.clear()

    def test_update_user_db_error_returns_500(self):
        """PUT /admin/api/users/{id} returns 500 on database error."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_user = _mock_user(id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_db.commit.side_effect = Exception("DB error")
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.put("/api/users/1", json={"capital": 200000.0})

        assert response.status_code == 500
        mock_db.rollback.assert_called_once()
        app.dependency_overrides.clear()


# ============================================================
# Tests for DELETE /admin/api/users/{user_id}
# ============================================================


class TestDeleteUser:
    """Tests for deleting users."""

    def test_delete_user_success(self):
        """DELETE /admin/api/users/{id} returns 204 on success."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_user = _mock_user(id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.delete("/api/users/1")

        assert response.status_code == 204
        mock_db.delete.assert_called_once_with(mock_user)
        mock_db.commit.assert_called_once()
        app.dependency_overrides.clear()

    def test_delete_user_not_found(self):
        """DELETE /admin/api/users/{id} returns 404 for non-existent user."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.delete("/api/users/999")

        assert response.status_code == 404
        app.dependency_overrides.clear()

    def test_delete_user_db_error_returns_500(self):
        """DELETE /admin/api/users/{id} returns 500 on database error."""
        app = _create_test_app()
        mock_db = MagicMock()
        mock_user = _mock_user(id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_db.delete.side_effect = Exception("FK constraint")
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        response = client.delete("/api/users/1")

        assert response.status_code == 500
        mock_db.rollback.assert_called_once()
        app.dependency_overrides.clear()
