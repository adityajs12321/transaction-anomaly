"""Step (b): rule-based anomaly detection."""

from collections import defaultdict
from statistics import median

# Domestic-only Indian brands that should never transact in USD.
DOMESTIC_ONLY_BRANDS = {
    "swiggy", "ola", "irctc", "zomato", "bigbasket", "blinkit",
    "jiomart", "dmart", "rapido", "redbus", "paytm", "phonepe",
    "meesho", "tata cliq", "bookmyshow",
}


def detect_anomalies(rows: list[dict]) -> list[dict]:
    """Annotate each cleaned row with is_anomaly / anomaly_reasons in place."""
    # Median per (account, currency): mixing INR and USD amounts in one median
    # would make the 3x comparison meaningless.
    amounts_by_account: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        if row["account_id"] and row["amount"] is not None:
            amounts_by_account[(row["account_id"], row["currency"])].append(row["amount"])

    medians = {key: median(vals) for key, vals in amounts_by_account.items()}

    for row in rows:
        reasons: list[str] = []

        acct_median = medians.get((row["account_id"], row["currency"]))
        if (
            row["amount"] is not None
            and acct_median is not None
            and acct_median > 0
            and row["amount"] > 3 * acct_median
        ):
            reasons.append(
                f"Amount {row['amount']:.2f} exceeds 3x the account median ({acct_median:.2f})"
            )

        merchant = (row["merchant"] or "").strip().lower()
        if row["currency"] == "USD" and merchant in DOMESTIC_ONLY_BRANDS:
            reasons.append(
                f"Currency is USD but '{row['merchant']}' is a domestic-only (INR) brand"
            )

        row["is_anomaly"] = bool(reasons)
        row["anomaly_reasons"] = reasons
    return rows
