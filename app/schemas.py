from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class JobCreated(BaseModel):
    job_id: str
    status: str
    message: str


class JobListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: str
    row_count_raw: int | None
    row_count_clean: int | None
    created_at: datetime


class JobListPage(BaseModel):
    items: list[JobListItem]
    total: int
    limit: int
    offset: int


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: dict | None = None
    error_message: str | None = None
    summary: dict | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    txn_id: str | None
    date: date | None
    merchant: str | None
    amount: float | None
    currency: str | None
    status: str | None
    category: str | None
    llm_category: str | None
    final_category: str
    account_id: str | None
    notes: str | None
    is_anomaly: bool
    anomaly_reasons: list | None
    llm_failed: bool


class SummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_spend_inr: float
    total_spend_usd: float
    top_merchants: list | None
    anomaly_count: int
    narrative: str | None
    risk_level: str | None
    llm_failed: bool


class JobResultsResponse(BaseModel):
    job_id: str
    status: str
    transactions: list[TransactionOut]
    transactions_total: int
    limit: int
    offset: int
    anomalies: list[TransactionOut]
    category_breakdown: dict
    summary: SummaryOut | None
