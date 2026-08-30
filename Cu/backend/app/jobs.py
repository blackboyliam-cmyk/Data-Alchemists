import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Farm
from app.services.ingestion import fetch_agmarknet
from app.services.weather import store_weather_for_farm

logger = logging.getLogger("farmdss.jobs")
settings = get_settings()
scheduler = BackgroundScheduler()


def job_sync_mandi():
    db: Session = SessionLocal()
    try:
        job = fetch_agmarknet(db)
        logger.info("Mandi sync %s ok=%s fail=%s", job.status, job.records_ok, job.records_failed)
    except Exception:
        logger.exception("Mandi sync crashed")
    finally:
        db.close()


def job_sync_weather():
    db: Session = SessionLocal()
    try:
        farms = db.query(Farm).all()
        for farm in farms:
            store_weather_for_farm(db, farm)
        logger.info("Weather sync finished for %s farms", len(farms))
    except Exception:
        logger.exception("Weather sync crashed")
    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(job_sync_mandi, "interval", minutes=settings.sync_interval_minutes, id="mandi", replace_existing=True)
    scheduler.add_job(
        job_sync_weather,
        "interval",
        minutes=settings.weather_sync_interval_minutes,
        id="weather",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")
