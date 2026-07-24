import re
import sqlite3
from pathlib import Path

from app.config import settings


def _normalize(phone_number: str) -> str:
    """Compare by the last 10 digits so E.164 (+15551234567), local
    (5551234567), and formatted (555-123-4567) numbers all match."""
    digits = re.sub(r"\D", "", phone_number or "")
    return digits[-10:] if len(digits) >= 10 else digits


def get_customer_context(phone_number: str, db_path: str | None = None) -> dict:
    """Returns the customer record for a phone number, or {} if the DB
    doesn't exist yet or the number isn't on file (unknown caller)."""
    path = Path(db_path or settings.customer_db_path)
    target = _normalize(phone_number)
    if not path.exists() or not target:
        return {}

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        for row in conn.execute("SELECT * FROM customers"):
            if _normalize(row["phone_number"]) == target:
                context = dict(row)
                context["last_bill_paid"] = bool(context["last_bill_paid"])
                return context
    finally:
        conn.close()
    return {}
