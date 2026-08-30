import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine, ensure_schema, migrate_constraints, ping_database
from app.jobs import start_scheduler
from app.seed import seed_if_empty

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.crops import router as crops_router
from app.api.farms import router as farms_router
from app.api.markets import router as markets_router
from app.api.recommendations import router as rec_router
from app.api.weather import router as weather_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    Base.metadata.create_all(bind=engine)
    migrate_constraints()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    start_scheduler()
    yield


app = FastAPI(
    title="Farm-to-Market Decision Support System",
    description="Data-driven crop, market, and sell/store advice for small farmers in India.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(farms_router)
app.include_router(markets_router)
app.include_router(weather_router)
app.include_router(crops_router)
app.include_router(rec_router)
app.include_router(admin_router)


@app.get("/api/health")
def health():
    try:
        db_kind = ping_database()
        db_ok = True
        db_error = None
    except Exception as exc:  # noqa: BLE001
        db_kind = "supabase-postgres" if settings.is_supabase else ("sqlite" if settings.is_sqlite else "postgresql")
        db_ok = False
        db_error = str(exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_kind,
        "database_ok": db_ok,
        "database_error": db_error,
        "mandi_api_configured": bool(settings.data_gov_in_api_key),
    }
