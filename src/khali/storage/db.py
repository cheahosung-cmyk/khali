"""DB 엔진/세션 부트스트랩."""

from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def init_db(database_url: str):
    global _engine, _Session
    # sqlite 파일 경로의 디렉토리 생성
    if database_url.startswith("sqlite:///"):
        path = database_url.replace("sqlite:///", "", 1)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    _engine = create_engine(database_url, connect_args=connect_args, future=True)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)

    # 모델 등록 보장 후 테이블 생성
    from . import models  # noqa: F401

    Base.metadata.create_all(_engine)
    _migrate_sqlite(_engine)
    return _engine


def _migrate_sqlite(engine):
    """기존 SQLite DB에 누락된 컬럼을 안전하게 추가 (create_all 은 ALTER 안 함)."""
    if engine.dialect.name != "sqlite":
        return
    from sqlalchemy import text

    expected = {
        "bot_state": {
            "peak_equity": "FLOAT DEFAULT 0.0",
            "last_rebalance": "DATETIME",
        }
    }
    with engine.begin() as conn:
        for table, cols in expected.items():
            existing = {
                row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))
            }
            for col, decl in cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))


@contextmanager
def get_session():
    if _Session is None:
        raise RuntimeError("init_db() 를 먼저 호출하세요.")
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
