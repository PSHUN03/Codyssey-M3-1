"""데이터베이스 연결. 로컬은 SQLite, 운영은 PostgreSQL(DATABASE_URL)을 쓴다."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def normalize_url(url: str) -> str:
    """Render 등이 주는 postgres:// URL을 psycopg 드라이버 URL로 바꾼다."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


def init_engine(url: str) -> Engine:
    global _engine, _session_factory
    url = normalize_url(url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)

    from app import models  # noqa: F401  테이블 메타데이터 등록

    # MVP 단계에서는 시작 시 테이블을 생성한다. 스키마 변경이 잦아지면 Alembic 마이그레이션을 도입한다.
    Base.metadata.create_all(_engine)
    add_missing_columns(_engine)
    return _engine


def add_missing_columns(engine: Engine) -> None:
    """create_all은 기존 테이블에 열을 더하지 않으므로, 모델에 새로 생긴 nullable 열만 ALTER TABLE로 붙인다."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or not column.nullable:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))


def new_session() -> Session:
    if _session_factory is None:
        raise RuntimeError("DB가 초기화되지 않았습니다. init_engine()을 먼저 호출하세요.")
    return _session_factory()


def get_db() -> Iterator[Session]:
    db = new_session()
    try:
        yield db
    finally:
        db.close()
