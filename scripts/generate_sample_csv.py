"""Generate a deterministic ~90-row dirty transactions.csv matching the
assignment description: mixed date formats, $ prefixes, inconsistent casing,
blank fields, exact duplicates, suspicious large amounts, USD on domestic brands.
"""

import csv
import random
from pathlib import Path

random.seed(42)

MERCHANTS = {
    "Swiggy": ("Food", "INR", 250, 700),
    "Zomato": ("Food", "INR", 200, 800),
    "Amazon": ("Shopping", "INR", 400, 5000),
    "Flipkart": ("Shopping", "INR", 300, 4000),
    "IRCTC": ("Travel", "INR", 500, 3000),
    "Ola": ("Transport", "INR", 100, 600),
    "Uber": ("Transport", "INR", 120, 700),
    "Netflix": ("Entertainment", "INR", 199, 649),
    "BookMyShow": ("Entertainment", "INR", 300, 1200),
    "Airtel": ("Utilities", "INR", 299, 999),
    "Tata Power": ("Utilities", "INR", 800, 3500),
    "ATM Withdrawal": ("Cash Withdrawal", "INR", 1000, 10000),
    "MakeMyTrip": ("Travel", "INR", 3000, 15000),
    "Starbucks": ("Food", "USD", 5, 25),
    "Apple.com": ("Shopping", "USD", 10, 300),
}
ACCOUNTS = ["ACC-1001", "ACC-1002", "ACC-1003", "ACC-1004"]
STATUSES = ["SUCCESS", "success", "Success", "FAILED", "failed", "PENDING", "pending"]


def random_date() -> str:
    day, month = random.randint(1, 28), random.randint(1, 12)
    year = 2025
    if random.random() < 0.5:
        return f"{day:02d}-{month:02d}-{year}"  # DD-MM-YYYY
    return f"{year}/{month:02d}/{day:02d}"      # YYYY/MM/DD


rows: list[dict] = []
for i in range(1, 81):
    merchant, meta = random.choice(list(MERCHANTS.items()))
    category, currency, lo, hi = meta
    amount = round(random.uniform(lo, hi), 2)
    row = {
        "txn_id": f"TXN{i:05d}",
        "date": random_date(),
        "merchant": merchant,
        "amount": str(amount),
        "currency": currency,
        "status": random.choice(STATUSES),
        "category": category,
        "account_id": random.choice(ACCOUNTS),
        "notes": "",
    }
    # Inject dirtiness
    if i % 9 == 0:
        row["txn_id"] = ""                                # blank txn_id
    if i % 7 == 0:
        row["amount"] = f"${row['amount']}"               # $ prefix
    if i % 5 == 0:
        row["currency"] = row["currency"].lower()         # 'inr' / 'usd'
    if i % 6 == 0:
        row["category"] = ""                              # blank category
    rows.append(row)

# Suspiciously large transactions (statistical outliers)
for i, (merchant, acct) in enumerate(
    [("Amazon", "ACC-1001"), ("ATM Withdrawal", "ACC-1002"), ("MakeMyTrip", "ACC-1003")]
):
    rows.append({
        "txn_id": f"TXN9{i:04d}",
        "date": random_date(),
        "merchant": merchant,
        "amount": str(round(random.uniform(150000, 500000), 2)),
        "currency": "INR",
        "status": "SUCCESS",
        "category": "",
        "account_id": acct,
        "notes": "SUSPICIOUS",
    })

# Currency anomalies: USD on domestic-only brands
for i, merchant in enumerate(["Swiggy", "Ola", "IRCTC"]):
    rows.append({
        "txn_id": f"TXN8{i:04d}",
        "date": random_date(),
        "merchant": merchant,
        "amount": str(round(random.uniform(20, 90), 2)),
        "currency": "USD",
        "status": "SUCCESS",
        "category": "",
        "account_id": random.choice(ACCOUNTS),
        "notes": "",
    })

# Exact duplicate rows
for source_index in (3, 10, 25, 40):
    dup = dict(rows[source_index])
    dup["notes"] = dup["notes"] or "Duplicate?"
    rows.append(dict(rows[source_index]))

random.shuffle(rows)

out = Path(__file__).resolve().parent.parent / "sample_data" / "transactions.csv"
out.parent.mkdir(exist_ok=True)
with out.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} rows to {out}")
