from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()
DATABASE_URL = settings.resolved_database_url()
SCHEMA = None if settings.is_sqlite else "farmdss"

connect_args = {}
if settings.is_sqlite:
    connect_args = {"check_same_thread": False}
elif settings.is_supabase:
    # PgBouncer transaction mode (pooler port 6543) cannot use prepared statements.
    connect_args = {"prepare_threshold": None}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


def ensure_schema() -> None:
    if not SCHEMA:
        return
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))


def migrate_constraints() -> None:
    if settings.is_sqlite or not SCHEMA:
        return
    table = f'"{SCHEMA}".market_prices'
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS uq_price_observation"))
        conn.execute(
            text(
                f"ALTER TABLE {table} ADD CONSTRAINT uq_price_observation "
                "UNIQUE (market_id, commodity_raw, variety, grade, price_date)"
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_database() -> str:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    if settings.is_sqlite:
        return "sqlite"
    if settings.is_supabase:
        return "supabase-postgres"
    return "postgresql"
