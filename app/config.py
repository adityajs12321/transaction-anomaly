from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/transactions"
    redis_url: str = "redis://redis:6379/0"

    # LLM provider: "gemini" (free tier) or "ollama" (local)
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2"

    # Langfuse observability (optional — tracing is disabled when keys are empty)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    llm_max_retries: int = 3
    llm_batch_size: int = 40
    llm_timeout_seconds: float = 60.0

    max_upload_bytes: int = 5 * 1024 * 1024


settings = Settings()
