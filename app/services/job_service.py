"""Business logic for job creation and retrieval (API side)."""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.config import settings
from app.dao.job_dao import JobDAO
from app.dao.transaction_dao import TransactionDAO
from app.exceptions import (
    InvalidUploadError,
    JobNotFoundError,
    ResultsNotReadyError,
    UploadTooLargeError,
)
from app.models import Job, JobStatus, Transaction
from app.pipeline.cleaning import read_csv


class JobService:
    def __init__(self, db: Session):
        self.jobs = JobDAO(db)
        self.transactions = TransactionDAO(db)

    def create_job_from_upload(self, filename: str | None, content: bytes) -> Job:
        if not (filename or "").lower().endswith(".csv"):
            raise InvalidUploadError("Only .csv files are accepted")
        if len(content) > settings.max_upload_bytes:
            raise UploadTooLargeError(f"File exceeds {settings.max_upload_bytes} bytes")
        try:
            text = content.decode("utf-8-sig")
            rows = read_csv(text)
        except UnicodeDecodeError:
            raise InvalidUploadError("File must be UTF-8 encoded")
        except ValueError as exc:
            raise InvalidUploadError(str(exc))
        if not rows:
            raise InvalidUploadError("CSV contains a header but no data rows")

        job = self.jobs.create(filename=filename, raw_csv=text, row_count_raw=len(rows))

        from app.tasks import process_job

        process_job.delay(job.id)
        return job

    def get_job(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} not found")
        return job

    def list_jobs(
        self, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[Job], int]:
        return self.jobs.list(status, limit=limit, offset=offset)

    def status_summary(self, job: Job) -> dict | None:
        """High-level stats included in the status response once completed."""
        if job.status != JobStatus.COMPLETED:
            return None
        return {
            "row_count_raw": job.row_count_raw,
            "row_count_clean": job.row_count_clean,
            "duplicates_removed": (job.row_count_raw or 0) - (job.row_count_clean or 0),
            "anomaly_count": job.summary.anomaly_count if job.summary else 0,
            "risk_level": job.summary.risk_level if job.summary else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def get_results(self, job_id: str, limit: int = 100, offset: int = 0) -> dict:
        """Full structured output for a completed job.

        The transactions list is paginated; anomalies and the category
        breakdown are computed over the full set (they need every row).
        """
        job = self.get_job(job_id)
        if job.status == JobStatus.FAILED:
            raise ResultsNotReadyError(f"Job failed: {job.error_message}")
        if job.status != JobStatus.COMPLETED:
            raise ResultsNotReadyError(f"Job is still {job.status}; poll /jobs/{job.id}/status")

        transactions = self.transactions.list_for_job(job.id)
        return {
            "job": job,
            "transactions": transactions[offset : offset + limit],
            "transactions_total": len(transactions),
            "anomalies": [t for t in transactions if t.is_anomaly],
            "category_breakdown": self._category_breakdown(transactions),
            "summary": job.summary,
        }

    @staticmethod
    def _category_breakdown(transactions: list[Transaction]) -> dict:
        breakdown: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "total_by_currency": defaultdict(float)}
        )
        for t in transactions:
            entry = breakdown[t.final_category]
            entry["count"] += 1
            if t.amount is not None and t.currency:
                entry["total_by_currency"][t.currency] = round(
                    entry["total_by_currency"][t.currency] + t.amount, 2
                )
        return {
            category: {"count": v["count"], "total_by_currency": dict(v["total_by_currency"])}
            for category, v in breakdown.items()
        }
