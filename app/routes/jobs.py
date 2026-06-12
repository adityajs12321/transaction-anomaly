from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.models import JobStatus
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    return JobService(db)


@router.post("/upload", response_model=schemas.JobCreated, status_code=202)
async def upload_csv(file: UploadFile, service: JobService = Depends(get_job_service)):
    content = await file.read()
    job = service.create_job_from_upload(file.filename, content)
    return schemas.JobCreated(
        job_id=job.id,
        status=job.status,
        message=f"Accepted {job.row_count_raw} rows; processing enqueued. "
        f"Poll /jobs/{job.id}/status.",
    )


@router.get("", response_model=schemas.JobListPage)
def list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: JobService = Depends(get_job_service),
):
    if status is not None and status not in JobStatus.ALL:
        raise HTTPException(400, f"Invalid status; expected one of {sorted(JobStatus.ALL)}")
    jobs, total = service.list_jobs(status, limit=limit, offset=offset)
    return schemas.JobListPage(items=jobs, total=total, limit=limit, offset=offset)


@router.get("/{job_id}/status", response_model=schemas.JobStatusResponse)
def job_status(job_id: str, service: JobService = Depends(get_job_service)):
    job = service.get_job(job_id)
    return schemas.JobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        error_message=job.error_message,
        summary=service.status_summary(job),
    )


@router.get("/{job_id}/results", response_model=schemas.JobResultsResponse)
def job_results(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: JobService = Depends(get_job_service),
):
    results = service.get_results(job_id, limit=limit, offset=offset)
    return schemas.JobResultsResponse(
        job_id=results["job"].id,
        status=results["job"].status,
        transactions=[schemas.TransactionOut.model_validate(t) for t in results["transactions"]],
        transactions_total=results["transactions_total"],
        limit=limit,
        offset=offset,
        anomalies=[schemas.TransactionOut.model_validate(t) for t in results["anomalies"]],
        category_breakdown=results["category_breakdown"],
        summary=schemas.SummaryOut.model_validate(results["summary"]) if results["summary"] else None,
    )
