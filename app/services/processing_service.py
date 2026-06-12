"""Pipeline orchestration for the worker: steps (a)-(e) of the assignment."""

import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from app import observability
from app.config import settings
from app.dao.job_dao import JobDAO
from app.dao.summary_dao import SummaryDAO
from app.dao.transaction_dao import TransactionDAO
from app.models import Job, JobStatus, JobSummary, Transaction, utcnow
from app.pipeline import anomaly, cleaning, llm

logger = logging.getLogger(__name__)


class ProcessingService:
    def __init__(self, db: Session):
        self.db = db
        self.jobs = JobDAO(db)
        self.transactions = TransactionDAO(db)
        self.summaries = SummaryDAO(db)

    def process(self, job_id: str) -> None:
        with observability.job_trace("process-job", metadata={"job_id": job_id}) as span:
            try:
                job = self.jobs.get(job_id)
                if job is None:
                    logger.error("Job %s not found", job_id)
                    return
                job.status = JobStatus.PROCESSING
                self._set_progress(job, step="cleaning")
                
                # Cleaning and anomaly detection
                transactions = self._clean_and_persist(job)

                # LLM Classification
                self._classify_uncategorised(job, transactions)

                self._set_progress(job, step="summarizing")
                # Narrative summary
                self._build_summary(job, transactions)

                job.status = JobStatus.COMPLETED
                job.completed_at = utcnow()
                self._set_progress(job, step="completed")
                if span is not None:
                    span.update(output={
                        "status": job.status,
                        "row_count_raw": job.row_count_raw,
                        "row_count_clean": job.row_count_clean,
                        "anomaly_count": sum(1 for t in transactions if t.is_anomaly),
                    })
            except Exception as exc:
                logger.exception("Job %s failed", job_id)
                self.db.rollback()
                if span is not None:
                    span.update(level="ERROR", status_message=str(exc)[:500])
                job = self.jobs.get(job_id)
                if job is not None:
                    job.status = JobStatus.FAILED
                    job.error_message = str(exc)[:2000]
                    job.completed_at = utcnow()
                    self.jobs.save()

    def _set_progress(self, job: Job, **progress) -> None:
        """Persist the current pipeline step so /status can report it live.

        On failure the last written progress is kept, showing where the job died.
        """
        job.progress = progress
        self.jobs.save()

    def _clean_and_persist(self, job: Job) -> list[Transaction]:
        """Steps (a)-(b): clean rows, detect anomalies, persist transactions."""
        raw_rows = cleaning.read_csv(job.raw_csv)
        cleaned = cleaning.clean_rows(raw_rows)
        job.row_count_raw = len(raw_rows)
        job.row_count_clean = len(cleaned)

        anomaly.detect_anomalies(cleaned)
        return self.transactions.bulk_create(job.id, cleaned)

    def _classify_uncategorised(self, job: Job, transactions: list[Transaction]) -> None:
        """Step (c): LLM classification for rows without a category.

        Pending rows are split into chunks of llm_batch_size — one LLM call per
        chunk
        """
        pending = [t for t in transactions if t.category == "Uncategorised"]
        self._set_progress(job, step="classifying", classified=0, total=len(pending))
        for start in range(0, len(pending), settings.llm_batch_size):
            batch = pending[start : start + settings.llm_batch_size]
            payload = [
                {"id": str(t.id), "merchant": t.merchant, "amount": t.amount,
                 "currency": t.currency, "notes": t.notes}
                for t in batch
            ]
            try:
                assignments = llm.classify_batch(payload)
            except Exception as exc:
                logger.error("Classification batch failed permanently: %s", exc)
                for t in batch:
                    t.llm_failed = True
                assignments = {}
            for t in batch:
                if not t.llm_failed:
                    category = assignments.get(str(t.id))
                    if category is None:
                        t.llm_failed = True
                    else:
                        # Replace the blank category; llm_category records provenance
                        t.category = category
                        t.llm_category = category
            self.transactions.save()
            self._set_progress(
                job, step="classifying", classified=start + len(batch), total=len(pending)
            )

    def _build_summary(self, job: Job, transactions: list[Transaction]) -> None:
        """Step (d): single LLM call for the narrative; numeric fields computed locally."""
        stats = self._compute_stats(transactions)
        summary = JobSummary(
            job_id=job.id,
            total_spend_inr=stats["total_spend_by_currency"].get("INR", 0.0),
            total_spend_usd=stats["total_spend_by_currency"].get("USD", 0.0),
            top_merchants=stats["top_merchants"],
            anomaly_count=stats["anomaly_count"],
        )
        try:
            result = llm.narrative_summary(stats)
            summary.narrative = result["narrative"]
            summary.risk_level = result["risk_level"]
        except Exception as exc:
            logger.error("Narrative summary failed permanently: %s", exc)
            summary.llm_failed = True
        self.summaries.create(summary)

    @staticmethod
    def _compute_stats(transactions: list[Transaction]) -> dict:
        spend_by_currency: dict[str, float] = defaultdict(float)
        spend_by_merchant: dict[str, float] = defaultdict(float)
        for t in transactions:
            if t.amount is None:
                continue
            if t.currency:
                spend_by_currency[t.currency] += t.amount
            if t.merchant:
                spend_by_merchant[t.merchant] += t.amount

        top_merchants = [
            {"merchant": m, "total_spend": round(total, 2)}
            for m, total in sorted(
                spend_by_merchant.items(), key=lambda kv: kv[1], reverse=True
            )[:3]
        ]
        anomalies = [t for t in transactions if t.is_anomaly]
        return {
            "transaction_count": len(transactions),
            "total_spend_by_currency": {c: round(v, 2) for c, v in spend_by_currency.items()},
            "top_merchants": top_merchants,
            "anomaly_count": len(anomalies),
            "anomaly_examples": [
                {"merchant": t.merchant, "amount": t.amount, "reasons": t.anomaly_reasons}
                for t in anomalies[:10]
            ],
            "category_counts": {
                cat: sum(1 for t in transactions if t.category == cat)
                for cat in {t.category for t in transactions}
            },
        }
