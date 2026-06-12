# AI-Powered Transaction Processing Pipeline

Backend API that accepts a dirty financial-transactions CSV, processes it
asynchronously through a job queue, uses an LLM to classify transactions and
generate a narrative summary, and exposes results via a polling API.

## Architecture

```
            ┌──────────┐   enqueue    ┌─────────┐   dequeue   ┌────────────────┐
 client ──▶ │ FastAPI  │ ───────────▶ │  Redis  │ ──────────▶ │ Celery worker  │
   ▲        │  (api)   │              └─────────┘             │  clean → flag  │
   │        └────┬─────┘                                      │  → LLM batch   │
   │  poll       │                                            │  → LLM summary │
   └─────────────┤            ┌────────────┐                  └───────┬────────┘
                 └──────────▶ │ PostgreSQL │ ◀────────────────────────┘
                              └────────────┘
```

- **API** (FastAPI): validates the upload, persists a `Job` (status=`pending`),
  enqueues `process_job`, returns `job_id` immediately.
- **Worker** (Celery): cleaning → anomaly detection → batched LLM
  classification → single LLM narrative call → summary persisted.
- **PostgreSQL**: `jobs`, `transactions`, `job_summaries` tables.
- **Redis**: Celery broker/backend.
- **LLM**: Gemini free tier by default; Ollama supported via env. LLM failures
  retry 3× with exponential backoff, then mark the batch `llm_failed` — the job
  still completes.

## Quick start

```bash
# Optional: enable LLM steps (free key from https://aistudio.google.com)
cp .env.example .env   # and set GEMINI_API_KEY

docker compose up --build
```

That single command starts PostgreSQL, Redis, the API (http://localhost:8000),
and the worker. No other setup. Interactive API docs at
http://localhost:8000/docs.

> Without `GEMINI_API_KEY`, everything still runs end to end; LLM-dependent
> fields are marked `llm_failed: true` per the assignment's retry/continue rule.
> To use a local model instead: `LLM_PROVIDER=ollama` (Ollama on the host).

## Endpoints & example curl requests

### 1. Upload a CSV

```bash
curl -s -X POST http://localhost:8000/jobs/upload \
  -F "file=@sample_data/transactions.csv"
# → {"job_id":"<uuid>","status":"pending","message":"Accepted 90 rows; ..."}
```

### 2. Poll job status

While processing, `progress` reports the current pipeline step live —
including per-chunk classification counts:

```bash
curl -s http://localhost:8000/jobs/<job_id>/status
# → {"job_id":"...","status":"processing",
#    "progress":{"step":"classifying","classified":16,"total":19}}
# and once finished:
# → {"job_id":"...","status":"completed","progress":{"step":"completed"},
#    "summary":{"row_count_raw":90,"row_count_clean":86,"duplicates_removed":4,
#    "anomaly_count":23,"risk_level":"high","completed_at":"..."}}
```

### 3. Fetch full results (paginated transactions)

```bash
curl -s "http://localhost:8000/jobs/<job_id>/results?limit=100&offset=0"
# → paginated cleaned transactions (+ transactions_total), flagged anomalies,
#   per-category spend breakdown, and the LLM narrative summary
```

`limit` defaults to 100 (max 1000). Anomalies and the category breakdown
always cover the full set.

### 4. List jobs (filtered + paginated)

```bash
curl -s "http://localhost:8000/jobs?status=completed&limit=20&offset=0"
# → {"items":[...],"total":6,"limit":20,"offset":0}
```

## Processing pipeline (worker)

| Step | What happens |
|---|---|
| a) Cleaning | Dates (`DD-MM-YYYY`, `YYYY/MM/DD`) → ISO 8601; `$`/`,` stripped from amounts; currency & status uppercased; blank categories → `Uncategorised`; exact duplicate rows removed |
| b) Anomaly detection | Amount > 3× the account's median; `USD` currency on domestic-only brands (Swiggy, Ola, IRCTC, …) |
| c) LLM classification | Uncategorised rows split into chunks of `LLM_BATCH_SIZE` (default 40) — one LLM call per chunk, so large files never exceed a single prompt. Categories: Food, Shopping, Travel, Transport, Utilities, Cash Withdrawal, Entertainment, Other |
| d) LLM narrative | One call producing `narrative` + `risk_level`; totals/top-merchants computed in code for accuracy |
| e) Retry logic | Each LLM call retried up to 3× with exponential backoff (1s, 2s, 4s); permanent failures set `llm_failed` and processing continues |

## Observability (Langfuse)

LLM calls are traced with [Langfuse](https://langfuse.com) when keys are
configured (free cloud tier — create a project at https://cloud.langfuse.com
and copy the API keys into `.env`):

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

Each processed job produces one `process-job` trace containing nested
generations for every `classify-transactions` batch and the
`narrative-summary` call, with the full prompt, model output, token usage,
provider, retry attempt count, and errors (retries that exhaust mark the
generation `ERROR`). Without keys, tracing is a no-op — the pipeline never
depends on Langfuse being reachable.

## Data model

- **jobs** — id (UUID), filename, status, row_count_raw, row_count_clean,
  raw_csv, error_message, created_at, completed_at
- **transactions** — job_id FK, cleaned fields, is_anomaly, anomaly_reasons
  (JSON), llm_category, llm_failed
- **job_summaries** — job_id FK, total_spend_inr, total_spend_usd,
  top_merchants (JSON), anomaly_count, narrative, risk_level, llm_failed

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `ollama` |
| `GEMINI_API_KEY` | _empty_ | Free-tier key; LLM steps degrade gracefully if unset |
| `GEMINI_MODEL` | `gemini-flash-latest` | Gemini model id |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Local Ollama |
| `OLLAMA_MODEL` | `llama3.2` | Local model name |
| `LLM_BATCH_SIZE` | `40` | Transactions per LLM classification call (chunking) |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | _empty_ | Enable Langfuse LLM tracing |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse instance (cloud or self-hosted) |

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest tests/            # unit tests (cleaning, anomaly, LLM parsing)
python3 scripts/generate_sample_csv.py       # regenerate the sample dirty CSV
```

## Project layout

The backend follows a router → service → DAO layering: routers only parse
requests and shape responses, services own the business logic, DAOs own all
database access.

```
app/
  main.py                  FastAPI app, startup table creation, exception mapping
  config.py                env-driven settings (pydantic-settings)
  database.py              engine/session, init_db with boot retry
  models.py                Job, Transaction, JobSummary
  schemas.py               API response models
  exceptions.py            domain errors (mapped to HTTP codes in main.py)
  routes/jobs.py           ROUTER: upload, status, results, list endpoints
  services/
    job_service.py         SERVICE: upload validation, status/results assembly
    processing_service.py  SERVICE: pipeline steps (a)-(e) orchestration
  dao/
    job_dao.py             DAO: Job queries
    transaction_dao.py     DAO: Transaction queries
    summary_dao.py         DAO: JobSummary persistence
  worker.py                Celery app
  tasks.py                 thin Celery entrypoint -> ProcessingService
  observability.py         optional Langfuse tracing (no-op without keys)
  pipeline/
    cleaning.py            step (a) pure functions
    anomaly.py             step (b) pure functions
    llm.py                 steps (c)-(e): providers, retries, prompts
sample_data/transactions.csv   ~90-row dirty sample
tests/                     unit tests
```
