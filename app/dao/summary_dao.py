from sqlalchemy.orm import Session

from app.models import JobSummary


class SummaryDAO:
    def __init__(self, db: Session):
        self.db = db

    def create(self, summary: JobSummary) -> JobSummary:
        self.db.add(summary)
        self.db.commit()
        return summary
