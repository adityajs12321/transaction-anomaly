from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Job


class JobDAO:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, filename: str, raw_csv: str, row_count_raw: int) -> Job:
        job = Job(filename=filename, raw_csv=raw_csv, row_count_raw=row_count_raw)
        self.db.add(job)
        self.db.commit()
        return job

    def get(self, job_id: str) -> Job | None:
        return self.db.get(Job, job_id)

    def list(
        self, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[Job], int]:
        """Return one page of jobs plus the total matching count."""
        query = select(Job)
        if status is not None:
            query = query.where(Job.status == status)
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = list(
            self.db.scalars(
                query.order_by(Job.created_at.desc()).limit(limit).offset(offset)
            )
        )
        return items, total

    def save(self) -> None:
        """Persist pending attribute changes on managed Job instances."""
        self.db.commit()
