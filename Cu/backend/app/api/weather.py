from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_farm
from app.database import get_db
from app.models import User, WeatherData
from app.security import get_current_user
from app.services.weather import geocode_place, latest_current, store_weather_for_farm, upcoming_forecast

router = APIRouter(tags=["weather"])


@router.get("/api/weather")
def get_weather(refresh: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farm = get_farm(db, user)
    current = latest_current(db, farm)
    stale = True
    if current and current.ingested_at:
        ingested = current.ingested_at
        if ingested.tzinfo is None:
            ingested = ingested.replace(tzinfo=timezone.utc)
        stale = (datetime.now(timezone.utc) - ingested).total_seconds() > 3 * 3600
    if refresh or current is None or stale:
        job = store_weather_for_farm(db, farm)
        if job.status == "failed" and current is None:
            return {
                "current": None,
                "forecast": [],
                "freshness": {
                    "quality": "missing",
                    "source": "Open-Meteo",
                    "last_updated": None,
                    "stale": True,
                    "message": f"Weather could not be fetched: {job.error_summary}",
                },
            }
        current = latest_current(db, farm)
    forecast = upcoming_forecast(db, farm)
    return {
        "location": {"latitude": farm.latitude, "longitude": farm.longitude, "district": farm.district, "state": farm.state},
        "current": None
        if not current
        else {
            "temperature_c": current.temperature_c,
            "humidity_percent": current.humidity_percent,
            "rainfall_mm": current.rainfall_mm,
            "wind_speed_kmh": current.wind_speed_kmh,
            "conditions": current.conditions,
            "observed_at": current.observed_at.isoformat() if current.observed_at else None,
        },
        "forecast": [
            {
                "date": w.observed_at.date().isoformat() if w.observed_at else None,
                "temperature_min_c": w.temperature_min_c,
                "temperature_max_c": w.temperature_max_c,
                "rainfall_mm": w.rainfall_mm,
                "wind_speed_kmh": w.wind_speed_kmh,
                "conditions": w.conditions,
                "quality": "forecast",
            }
            for w in forecast
        ],
        "freshness": {
            "quality": "actual" if current else "missing",
            "source": current.source if current else "Open-Meteo",
            "last_updated": current.ingested_at.isoformat() if current and current.ingested_at else None,
            "stale": False,
        },
    }


@router.get("/api/geocode")
def geocode(q: str = Query(min_length=2), user: User = Depends(get_current_user)):
    try:
        return {"results": geocode_place(q)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Place search failed: {exc}") from exc
