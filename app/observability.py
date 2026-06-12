"""Optional Langfuse tracing. Every helper no-ops when keys are not configured,
so the pipeline never depends on observability being available."""

import logging
from contextlib import contextmanager

from app.config import settings

logger = logging.getLogger(__name__)

_client = None
_init_attempted = False


def get_client():
    global _client, _init_attempted
    if not _init_attempted:
        _init_attempted = True
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            try:
                from langfuse import Langfuse

                _client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                )
                logger.info("Langfuse tracing enabled (%s)", settings.langfuse_host)
            except Exception as exc:
                logger.warning("Langfuse init failed; tracing disabled: %s", exc)
    return _client


@contextmanager
def job_trace(name: str, metadata: dict | None = None):
    """Root span for one processed job. Yields the span, or None when disabled."""
    client = get_client()
    if client is None:
        yield None
        return
    try:
        with client.start_as_current_span(name=name, metadata=metadata) as span:
            yield span
    finally:
        client.flush()


@contextmanager
def generation(name: str, model: str | None = None, input: object = None):
    """Generation span for one LLM call. Yields the span, or None when disabled."""
    client = get_client()
    if client is None:
        yield None
        return
    with client.start_as_current_generation(name=name, model=model, input=input) as gen:
        yield gen
