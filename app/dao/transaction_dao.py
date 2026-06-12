from sqlalchemy import select
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

    def list_for_job(self, job_id: str) -> list[Transaction]:
        return list(
            self.db.scalars(
                select(Transaction).where(Transaction.job_id == job_id).order_by(Transaction.id)
            )
        )

    def save(self) -> None:
        """Persist pending attribute changes on managed Transaction instances."""
        self.db.commit()
