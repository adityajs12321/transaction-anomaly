from app.database import SessionLocal, init_db
from app.services.processing_service import ProcessingService
from app.worker import celery_app


@celery_app.task(name="process_job")
def process_job(job_id: str) -> None:
    init_db()  # no-op if tables already exist; protects against worker-first startup
    db = SessionLocal()
    try:
        ProcessingService(db).process(job_id)
    finally:
        db.close()
