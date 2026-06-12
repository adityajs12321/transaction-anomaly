import time

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db(max_attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """Create tables, retrying while PostgreSQL finishes booting."""
    from app import models  # noqa: F401  (register models with Base)

    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:  # pragma: no cover - startup race only
            last_error = exc
            time.sleep(delay_seconds)
    raise RuntimeError(f"Database not reachable after {max_attempts} attempts") from last_error


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
