from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.jobs.config import jobs_data_dir
from backend.jobs.models import Base


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_engine_url: str | None = None


def default_db_url() -> str:
    db_path = jobs_data_dir() / "jobs.sqlite3"
    return f"sqlite:///{db_path}"


def jobs_db_url() -> str:
    return os.getenv("DEXTER_JOBS_DB_URL", default_db_url())


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def get_engine() -> Engine:
    global _engine, _engine_url
    url = jobs_db_url()
    if _engine is not None and _engine_url == url:
        return _engine

    if url.startswith("sqlite:///"):
        db_file = Path(url.replace("sqlite:///", "", 1))
        if str(db_file) != ":memory:":
            db_file.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    _engine = create_engine(url, future=True, connect_args=connect_args)
    _engine_url = url
    if url.startswith("sqlite"):
        event.listen(_engine, "connect", _configure_sqlite)
    return _engine


def SessionLocal() -> sessionmaker[Session]:
    global _session_factory
    engine = get_engine()
    if _session_factory is None or _session_factory.kw.get("bind") is not engine:
        _session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return _session_factory


def get_session() -> Session:
    init_db()
    return SessionLocal()()


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())


def reset_engine_for_tests() -> None:
    global _engine, _session_factory, _engine_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _engine_url = None
