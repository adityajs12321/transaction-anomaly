"""Business logic for job creation and retrieval (API side)."""

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
from app.models import Job, JobStatus
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

        Pagination, counting, anomaly filtering, and the category breakdown
        all happen in SQL — API memory no longer grows with job size.
        """
        job = self.get_job(job_id)
        if job.status == JobStatus.FAILED:
            raise ResultsNotReadyError(f"Job failed: {job.error_message}")
        if job.status != JobStatus.COMPLETED:
            raise ResultsNotReadyError(f"Job is still {job.status}; poll /jobs/{job.id}/status")

        return {
            "job": job,
            "transactions": self.transactions.list_for_job(job.id, limit=limit, offset=offset),
            "transactions_total": self.transactions.count_for_job(job.id),
            "anomalies": self.transactions.list_anomalies(job.id),
            "category_breakdown": self.transactions.category_breakdown(job.id),
            "summary": job.summary,
        }
