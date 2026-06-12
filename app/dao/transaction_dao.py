from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Transaction


class TransactionDAO:
    def __init__(self, db: Session):
        self.db = db

    def bulk_create(self, job_id: str, rows: list[dict]) -> list[Transaction]:
        transactions = [Transaction(job_id=job_id, **row) for row in rows]
        self.db.add_all(transactions)
        self.db.commit()
        return transactions

    def list_for_job(
        self, job_id: str, limit: int | None = None, offset: int = 0
    ) -> list[Transaction]:
        query = (
            select(Transaction).where(Transaction.job_id == job_id).order_by(Transaction.id)
        )
        if limit is not None:
            query = query.limit(limit).offset(offset)
        return list(self.db.scalars(query))

    def count_for_job(self, job_id: str) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.job_id == job_id)
            )
            or 0
        )

    def list_anomalies(self, job_id: str) -> list[Transaction]:
        return list(
            self.db.scalars(
                select(Transaction)
                .where(Transaction.job_id == job_id, Transaction.is_anomaly.is_(True))
                .order_by(Transaction.id)
            )
        )

    def category_breakdown(self, job_id: str) -> dict:
        """Per-category counts and per-currency totals, aggregated in SQL."""
        rows = self.db.execute(
            select(
                Transaction.category,
                Transaction.currency,
                func.count(),
                func.sum(Transaction.amount),
            )
            .where(Transaction.job_id == job_id)
            .group_by(Transaction.category, Transaction.currency)
        ).all()

        breakdown: dict[str, dict] = {}
        for category, currency, count, total in rows:
            entry = breakdown.setdefault(
                category or "Uncategorised", {"count": 0, "total_by_currency": {}}
            )
            entry["count"] += count
            if currency and total is not None:
                entry["total_by_currency"][currency] = round(float(total), 2)
        return breakdown

    def save(self) -> None:
        """Persist pending attribute changes on managed Transaction instances."""
        self.db.commit()
