"""Step (a): data cleaning for raw CSV rows."""

import csv
import io
from datetime import date, datetime

DATE_FORMATS = ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y")
REQUIRED_COLUMNS = {
    "txn_id", "date", "merchant", "amount", "currency",
    "status", "category", "account_id", "notes",
}


def parse_date(raw: str | None) -> date | None:
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = raw.strip().replace("$", "").replace("₹", "").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def read_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
    return [row for row in reader]


def clean_row(row: dict) -> dict:
    def text(field: str) -> str:
        return (row.get(field) or "").strip()

    return {
        "txn_id": text("txn_id") or None,
        "date": parse_date(row.get("date")),
        "merchant": text("merchant") or None,
        "amount": parse_amount(row.get("amount")),
        "currency": text("currency").upper() or None,
        "status": text("status").upper() or None,
        "category": text("category") or "Uncategorised",
        "account_id": text("account_id") or None,
        "notes": text("notes") or None,
    }


def clean_rows(raw_rows: list[dict]) -> list[dict]:
    """Normalise every row and drop exact duplicates (post-normalisation)."""
    seen: set[tuple] = set()
    cleaned: list[dict] = []
    for raw in raw_rows:
        row = clean_row(raw)
        key = tuple(row[k].isoformat() if isinstance(row[k], date) else row[k] for k in sorted(row))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(row)
    return cleaned
