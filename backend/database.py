import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy backend/.env.example to backend/.env "
        "and fill in a valid PostgreSQL connection string."
    )


def _sqlite_date_trunc(part: str, val: str | None) -> str | None:
    if not val:
        return None
    val_str = str(val).strip()
    part = str(part).lower().strip()
    if part in ("year", "yyyy", "yy"):
        return val_str[:4] + "-01-01"
    elif part in ("month", "mon", "mm"):
        return val_str[:7] + "-01"
    elif part in ("day", "dd"):
        return val_str[:10]
    elif part in ("hour", "hh"):
        return val_str[:13] + ":00:00"
    return val_str


@event.listens_for(Engine, "connect")
def _set_sqlite_custom_functions(dbapi_connection, connection_record):
    if hasattr(dbapi_connection, "create_function"):
        try:
            dbapi_connection.create_function("date_trunc", 2, _sqlite_date_trunc)
            dbapi_connection.create_function("DATE_TRUNC", 2, _sqlite_date_trunc)
        except Exception:
            pass


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_engine():
    return engine


def get_db_session():
    """FastAPI dependency yielding a SQLAlchemy session (for the query cache tables)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
