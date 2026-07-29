"""Generates a synthetic telecom customer dataset for the demo.

Run directly (`python scripts/seed_customer_data.py`) or as the CML AMP
run_session task before the Application starts.
"""

import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

FIRST_NAMES = [
    "James", "Maria", "Wei", "Aisha", "Liam", "Sofia", "Noah", "Priya", "Ethan", "Fatima",
    "Lucas", "Ingrid", "Mateo", "Yuki", "Omar", "Elena", "Kwame", "Nadia", "Diego", "Chloe",
]
LAST_NAMES = [
    "Nguyen", "Garcia", "Smith", "Khan", "Muller", "Rossi", "Kim", "Patel", "Johnson", "Silva",
    "Kowalski", "Andersson", "Haile", "Tanaka", "Reyes", "Petrov", "Osei", "Ibrahim", "Rivera", "Dubois",
]
CITIES = [
    "Austin, Texas", "Denver, Colorado", "Chicago, Illinois", "Seattle, Washington",
    "Miami, Florida", "Boston, Massachusetts", "Phoenix, Arizona", "Portland, Oregon",
    "Atlanta, Georgia", "Minneapolis, Minnesota",
]
PLANS = [
    ("Basic 5GB", 5),
    ("Standard 15GB", 15),
    ("Unlimited Plus", 100),
    ("Family Share 50GB", 50),
    ("Business Pro 30GB", 30),
]
STATUSES = ["active", "active", "active", "past_due", "suspended"]
TIERS = ["Bronze", "Silver", "Gold", "Platinum"]

NUM_CUSTOMERS = 40
SEED = 20260723  # deterministic so the demo dataset is reproducible across runs

# A real record for live demo calls -- not synthetic, so the agent can greet
# the actual caller by name with a genuine tenure/loyalty story.
DEMO_CUSTOMER = {
    "phone_number": "+18577578290",
    "full_name": "Athul Prasad",
    "account_status": "active",
    "plan_name": "Unlimited Plus",
    "monthly_data_gb": 100,
    "data_used_gb": 42.3,
    "last_bill_amount": 89.99,
    "last_bill_paid": True,
    "open_support_tickets": 0,
    "loyalty_tier": "Platinum",
    "contract_end_date": (date.today() + timedelta(days=210)).isoformat(),
    "city": "San Francisco, California",
    "customer_since_date": "2018-03-14",
}


def _phone_number(index: int) -> str:
    # Obviously-fake NANP numbers in the reserved 555 exchange.
    return f"+1555{index:07d}"


def build_customers() -> list[dict]:
    rng = random.Random(SEED)
    customers = [DEMO_CUSTOMER]
    for i in range(1, NUM_CUSTOMERS + 1):
        plan_name, plan_gb = rng.choice(PLANS)
        used = round(rng.uniform(0.1, plan_gb * 1.1), 1)
        contract_end = date.today() + timedelta(days=rng.randint(-60, 400))
        customer_since = date.today() - timedelta(days=rng.randint(30, 3650))
        customers.append(
            {
                "phone_number": _phone_number(i),
                "full_name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                "account_status": rng.choice(STATUSES),
                "plan_name": plan_name,
                "monthly_data_gb": plan_gb,
                "data_used_gb": used,
                "last_bill_amount": round(rng.uniform(35, 145), 2),
                "last_bill_paid": rng.random() > 0.2,
                "open_support_tickets": rng.choices([0, 1, 2, 3], weights=[60, 25, 10, 5])[0],
                "loyalty_tier": rng.choice(TIERS),
                "contract_end_date": contract_end.isoformat(),
                "city": rng.choice(CITIES),
                "customer_since_date": customer_since.isoformat(),
            }
        )
    return customers


def seed(db_path: str | None = None) -> str:
    path = Path(db_path or settings.customer_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    try:
        conn.execute("DROP TABLE IF EXISTS customers")
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
                contract_end_date TEXT,
                city TEXT,
                customer_since_date TEXT
            )
            """
        )
        rows = [
            (
                c["phone_number"],
                c["full_name"],
                c["account_status"],
                c["plan_name"],
                c["monthly_data_gb"],
                c["data_used_gb"],
                c["last_bill_amount"],
                int(c["last_bill_paid"]),
                c["open_support_tickets"],
                c["loyalty_tier"],
                c["contract_end_date"],
                c["city"],
                c["customer_since_date"],
            )
            for c in build_customers()
        ]
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    return str(path)


if __name__ == "__main__":
    seeded_path = seed()
    print(f"Seeded {NUM_CUSTOMERS + 1} customers (including 1 real demo record) into {seeded_path}")
    print(f"Sample lookup number: {_phone_number(1)}")
