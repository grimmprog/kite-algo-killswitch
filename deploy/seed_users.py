"""Seed script to create admin and demo users."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.database.models.user import User
from src.auth.password import hash_password

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/trading_platform")

engine = create_engine(DATABASE_URL)

users_to_create = [
    {
        "email": "admin@kite.goroomz.in",
        "password": "Admin@1234",
        "capital": 100000.0,
        "risk_profile": "moderate",
        "daily_loss_limit_percent": 3.0,
        "max_trade_risk_percent": 2.0,
    },
    {
        "email": "demo@kite.goroomz.in",
        "password": "Demo@1234",
        "capital": 50000.0,
        "risk_profile": "conservative",
        "daily_loss_limit_percent": 2.0,
        "max_trade_risk_percent": 1.0,
    },
]

with Session(engine) as session:
    for user_data in users_to_create:
        # Check if user already exists
        existing = session.query(User).filter_by(email=user_data["email"]).first()
        if existing:
            print(f"User '{user_data['email']}' already exists (id={existing.id}), skipping.")
            continue

        user = User(
            email=user_data["email"],
            password_hash=hash_password(user_data["password"]),
            capital=user_data["capital"],
            risk_profile=user_data["risk_profile"],
            daily_loss_limit_percent=user_data["daily_loss_limit_percent"],
            max_trade_risk_percent=user_data["max_trade_risk_percent"],
        )
        session.add(user)
        session.commit()
        print(f"Created user '{user_data['email']}' with id={user.id}")

print("\nDone! Users created:")
print("  Admin: admin@kite.goroomz.in / Admin@1234")
print("  Demo:  demo@kite.goroomz.in / Demo@1234")
