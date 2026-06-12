"""Steps (c)-(e): LLM classification, narrative summary, retry logic."""

import json
import logging
import re
import time

import httpx
from google import genai
from google.genai import types as genai_types

from app import observability
from app.config import settings

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = {
    "Food", "Shopping", "Travel", "Transport", "Utilities",
    "Cash Withdrawal", "Entertainment", "Other",
}


class LLMError(Exception):
    pass


_genai_client: genai.Client | None = None


def _get_genai_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not configured")
        _genai_client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=genai_types.HttpOptions(
                timeout=int(settings.llm_timeout_seconds * 1000)  # milliseconds
            ),
        )
    return _genai_client


def _call_gemini(prompt: str) -> tuple[str, dict | None]:
    response = _get_genai_client().models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    if response.text is None:
        raise LLMError(f"Gemini returned no text: {response}")
    meta = response.usage_metadata
    usage = None
    if meta is not None:
        usage = {"input": meta.prompt_token_count, "output": meta.candidates_token_count}
    return response.text, usage


def _call_ollama(prompt: str) -> tuple[str, dict | None]:
    response = httpx.post(
        f"{settings.ollama_base_url}/api/generate",
        json={"model": settings.ollama_model, "prompt": prompt, "stream": False, "format": "json"},
        timeout=settings.llm_timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    usage = {"input": data.get("prompt_eval_count"), "output": data.get("eval_count")}
    return data["response"], usage


def model_name() -> str:
    return settings.ollama_model if settings.llm_provider == "ollama" else settings.gemini_model


def generate(prompt: str) -> tuple[str, dict | None]:
    if settings.llm_provider == "ollama":
        return _call_ollama(prompt)
    return _call_gemini(prompt)


def call_with_retries(prompt: str, trace_name: str = "llm-call") -> str:
    """Call the LLM, retrying up to llm_max_retries times with exponential backoff.

    Traced as a Langfuse generation when observability is configured.
    """
    with observability.generation(trace_name, model=model_name(), input=prompt) as gen:
        delay = 1.0
        last_error: Exception | None = None
        for attempt in range(1 + settings.llm_max_retries):
            try:
                text, usage = generate(prompt)
                if gen is not None:
                    gen.update(
                        output=text,
                        metadata={"attempts": attempt + 1, "provider": settings.llm_provider},
                        **({"usage_details": usage} if usage else {}),
                    )
                return text
            except Exception as exc:
                last_error = exc
                logger.warning("LLM call failed (attempt %d): %s", attempt + 1, exc)
                if attempt < settings.llm_max_retries:
                    time.sleep(delay)
                    delay *= 2
        error = LLMError(
            f"LLM call failed after {1 + settings.llm_max_retries} attempts: {last_error}"
        )
        if gen is not None:
            gen.update(level="ERROR", status_message=str(error))
        raise error


def parse_json_response(text: str) -> dict:
    """Parse LLM output as JSON, tolerating markdown code fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)


def classify_batch(batch: list[dict]) -> dict[str, str]:
    """Classify a batch of transactions in a single LLM call.

    `batch` items need: id, merchant, amount, currency, notes.
    Returns {id: category}. Raises LLMError if all retries fail.
    """
    lines = "\n".join(
        f"{t['id']} | {t['merchant'] or 'unknown'} | {t['amount']} {t['currency'] or ''} | {t['notes'] or ''}"
        for t in batch
    )
    categories = ", ".join(sorted(ALLOWED_CATEGORIES))
    prompt = (
        "You are a financial transaction classifier. Assign each transaction below "
        f"exactly one category from this list: {categories}.\n\n"
        "Transactions (id | merchant | amount currency | notes):\n"
        f"{lines}\n\n"
        'Respond with ONLY a JSON object mapping each id (as a string) to its category, '
        'for example: {"12": "Food", "13": "Travel"}.'
    )
    raw = call_with_retries(prompt, trace_name="classify-transactions")
    parsed = parse_json_response(raw)
    result: dict[str, str] = {}
    for txn_id, category in parsed.items():
        if isinstance(category, str) and category in ALLOWED_CATEGORIES:
            result[str(txn_id)] = category
    return result


def narrative_summary(stats: dict) -> dict:
    """Single LLM call producing the JSON narrative summary."""
    prompt = (
        "You are a financial analyst. Below are pre-computed statistics for a batch of "
        "processed transactions:\n\n"
        f"{json.dumps(stats, indent=2, default=str)}\n\n"
        "Respond with ONLY a JSON object with exactly these keys:\n"
        '- "narrative": a 2-3 sentence plain-English summary of the spending patterns '
        "and any anomalies\n"
        '- "risk_level": one of "low", "medium", "high", based on the anomaly count '
        "and severity\n"
    )
    raw = call_with_retries(prompt, trace_name="narrative-summary")
    parsed = parse_json_response(raw)
    risk = str(parsed.get("risk_level", "")).lower()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    return {"narrative": str(parsed.get("narrative", "")), "risk_level": risk}
