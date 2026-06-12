from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.database import init_db
from app.exceptions import (
    InvalidUploadError,
    JobNotFoundError,
    ResultsNotReadyError,
    UploadTooLargeError,
)
from app.routes.jobs import router as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI-Powered Transaction Processing Pipeline",
    description="Upload a dirty transactions CSV, get it returned cleaned."
    " Poll for status and results.",
    version="1.0",
    lifespan=lifespan,
)
app.include_router(jobs_router)

# Domain exception -> HTTP status mapping (keeps routers free of error handling)
_EXCEPTION_STATUS = {
    InvalidUploadError: 400,
    JobNotFoundError: 404,
    ResultsNotReadyError: 409,
    UploadTooLargeError: 413,
}

for _exc_type, _status in _EXCEPTION_STATUS.items():
    @app.exception_handler(_exc_type)
    async def _handle_domain_error(request: Request, exc: Exception, _status=_status):
        return JSONResponse(status_code=_status, content={"detail": str(exc)})


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
