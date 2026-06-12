from datetime import date

from app.pipeline.anomaly import detect_anomalies
from app.pipeline.cleaning import clean_rows, parse_amount, parse_date
from app.pipeline.llm import parse_json_response


def make_row(**overrides) -> dict:
    base = {
        "txn_id": "TXN00001", "date": "01-02-2025", "merchant": "Swiggy",
        "amount": "450.00", "currency": "inr", "status": "success",
        "category": "", "account_id": "ACC-1001", "notes": "",
    }
    base.update(overrides)
    return base


def test_parse_date_both_formats():
    assert parse_date("15-03-2025") == date(2025, 3, 15)
    assert parse_date("2025/03/15") == date(2025, 3, 15)
    assert parse_date("") is None
    assert parse_date("not-a-date") is None


def test_parse_amount_strips_symbols():
    assert parse_amount("$1,234.50") == 1234.50
    assert parse_amount("450") == 450.0
    assert parse_amount("") is None


def test_clean_rows_normalises_and_dedupes():
    rows = [make_row(), make_row(), make_row(txn_id="TXN00002")]
    cleaned = clean_rows(rows)
    assert len(cleaned) == 2  # exact duplicate removed
    assert cleaned[0]["currency"] == "INR"
    assert cleaned[0]["status"] == "SUCCESS"
    assert cleaned[0]["category"] == "Uncategorised"
    assert cleaned[0]["date"] == date(2025, 2, 1)


def test_statistical_outlier_flagged():
    rows = clean_rows([
        make_row(txn_id=f"T{i}", amount="100") for i in range(5)
    ] + [make_row(txn_id="BIG", amount="100000")])
    detect_anomalies(rows)
    big = next(r for r in rows if r["txn_id"] == "BIG")
    assert big["is_anomaly"]
    assert "exceeds 3x" in big["anomaly_reasons"][0]
    assert not any(r["is_anomaly"] for r in rows if r["txn_id"] != "BIG")


def test_usd_domestic_brand_flagged():
    rows = clean_rows([make_row(currency="USD")])
    detect_anomalies(rows)
    assert rows[0]["is_anomaly"]
    assert "domestic-only" in rows[0]["anomaly_reasons"][0]


def test_parse_json_response_handles_fences():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_response('{"a": 1}') == {"a": 1}
