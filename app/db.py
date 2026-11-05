from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

engine = None
SessionLocal = None


class Base(DeclarativeBase):
    pass


def init_engine(url: str) -> None:
    global engine, SessionLocal
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url.endswith("sqlite://"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    _ensure_listing_columns()


def _ensure_listing_columns() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "listings" not in inspector.get_table_names():
        return
    present = {column["name"] for column in inspector.get_columns("listings")}
    statements = []
    if "proposal_origin" not in present:
        statements.append("ALTER TABLE listings ADD COLUMN proposal_origin VARCHAR(16) DEFAULT 'template'")
    if "proposed_price_text" not in present:
        statements.append("ALTER TABLE listings ADD COLUMN proposed_price_text TEXT")
    if "in_crm" not in present:
        if engine.dialect.name == "sqlite":
            statements.append("ALTER TABLE listings ADD COLUMN in_crm BOOLEAN NOT NULL DEFAULT 0")
        else:
            statements.append("ALTER TABLE listings ADD COLUMN in_crm BOOLEAN NOT NULL DEFAULT FALSE")
    if "crm_due_on" not in present:
        statements.append("ALTER TABLE listings ADD COLUMN crm_due_on DATE")
    if "commercial_proposal" not in present:
        statements.append("ALTER TABLE listings ADD COLUMN commercial_proposal TEXT")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


@contextmanager
def session_scope():
    if SessionLocal is None:
        raise RuntimeError("database is not initialised")
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
