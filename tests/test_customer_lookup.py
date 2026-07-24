import sqlite3
from pathlib import Path

import pytest

from app.data.customer_lookup import get_customer_context


@pytest.fixture
def temp_db(tmp_path: Path) -> str:
    db_path = tmp_path / "customers.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE customers (
            phone_number TEXT PRIMARY KEY,
            full_name TEXT,
            account_status TEXT,
            plan_name TEXT,
            monthly_data_gb REAL,
            data_used_gb REAL,
            last_bill_amount REAL,
            last_bill_paid INTEGER,
            open_support_tickets INTEGER,
            loyalty_tier TEXT,
            contract_end_date TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("+15551234567", "Test User", "active", "Unlimited Plus", 100, 42.0, 80.0, 1, 0, "Gold", "2027-01-01"),
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_exact_match(temp_db):
    context = get_customer_context("+15551234567", db_path=temp_db)
    assert context["full_name"] == "Test User"
    assert context["last_bill_paid"] is True


def test_formatted_number_matches(temp_db):
    context = get_customer_context("(555) 123-4567", db_path=temp_db)
    assert context["full_name"] == "Test User"


def test_local_number_matches(temp_db):
    context = get_customer_context("5551234567", db_path=temp_db)
    assert context["full_name"] == "Test User"


def test_unknown_caller_returns_empty(temp_db):
    assert get_customer_context("+19995550000", db_path=temp_db) == {}


def test_missing_db_returns_empty(tmp_path):
    missing_path = tmp_path / "does_not_exist.db"
    assert get_customer_context("+15551234567", db_path=str(missing_path)) == {}


def test_empty_number_returns_empty(temp_db):
    assert get_customer_context("", db_path=temp_db) == {}
