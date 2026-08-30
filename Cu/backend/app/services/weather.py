from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Farm, SyncJob, WeatherData

settings = get_settings()

WMO = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


def condition_from_code(code: Optional[int]) -> str:
    if code is None:
        return "Unknown"
    return WMO.get(code, f"Weather code {code}")


def heavy_rain_expected(forecast_rows: list[WeatherData]) -> bool:
    for row in forecast_rows:
        rain = row.rainfall_mm or 0
        code = row.weather_code or 0
        if rain >= 20 or code in (65, 82, 95, 96, 99):
            return True
    return False


def upsert_weather(db: Session, **kwargs) -> None:
    existing = (
        db.query(WeatherData)
        .filter(
            WeatherData.latitude == kwargs["latitude"],
            WeatherData.longitude == kwargs["longitude"],
            WeatherData.observed_at == kwargs["observed_at"],
            WeatherData.is_forecast == kwargs["is_forecast"],
        )
        .first()
    )
    if existing:
        for k, v in kwargs.items():
            setattr(existing, k, v)
        existing.ingested_at = datetime.now(timezone.utc)
        return
    db.add(WeatherData(**kwargs))


def fetch_open_meteo(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,wind_speed_10m_max",
        "timezone": "Asia/Kolkata",
        "forecast_days": 7,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.get(settings.open_meteo_forecast_url, params=params)
        response.raise_for_status()
        return response.json()


def store_weather_for_farm(db: Session, farm: Farm) -> SyncJob:
    job = SyncJob(source="Open-Meteo", status="running")
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        data = fetch_open_meteo(farm.latitude, farm.longitude)
        current = data.get("current") or {}
        now = datetime.now(timezone.utc)
        upsert_weather(
            db,
            farm_id=farm.id,
            latitude=farm.latitude,
            longitude=farm.longitude,
            observed_at=now.replace(minute=0, second=0, microsecond=0),
            is_forecast=False,
            temperature_c=current.get("temperature_2m"),
            rainfall_mm=current.get("precipitation"),
            humidity_percent=current.get("relative_humidity_2m"),
            wind_speed_kmh=current.get("wind_speed_10m"),
            weather_code=current.get("weather_code"),
            conditions=condition_from_code(current.get("weather_code")),
            source="Open-Meteo",
        )
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        for i, day in enumerate(times):
            observed = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
            upsert_weather(
                db,
                farm_id=farm.id,
                latitude=farm.latitude,
                longitude=farm.longitude,
                observed_at=observed,
                is_forecast=True,
                temperature_min_c=(daily.get("temperature_2m_min") or [None])[i] if i < len(daily.get("temperature_2m_min") or []) else None,
                temperature_max_c=(daily.get("temperature_2m_max") or [None])[i] if i < len(daily.get("temperature_2m_max") or []) else None,
                rainfall_mm=(daily.get("precipitation_sum") or [None])[i] if i < len(daily.get("precipitation_sum") or []) else None,
                wind_speed_kmh=(daily.get("wind_speed_10m_max") or [None])[i] if i < len(daily.get("wind_speed_10m_max") or []) else None,
                weather_code=(daily.get("weather_code") or [None])[i] if i < len(daily.get("weather_code") or []) else None,
                conditions=condition_from_code((daily.get("weather_code") or [None])[i] if i < len(daily.get("weather_code") or []) else None),
                source="Open-Meteo",
            )
        db.commit()
        job.status = "success"
        job.records_ok = 1 + len(times)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error_summary = str(exc)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    return job


def latest_current(db: Session, farm: Farm) -> Optional[WeatherData]:
    return (
        db.query(WeatherData)
        .filter(WeatherData.farm_id == farm.id, WeatherData.is_forecast.is_(False))
        .order_by(WeatherData.observed_at.desc())
        .first()
    )


def upcoming_forecast(db: Session, farm: Farm, days: int = 7) -> list[WeatherData]:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
    return (
        db.query(WeatherData)
        .filter(
            WeatherData.farm_id == farm.id,
            WeatherData.is_forecast.is_(True),
            WeatherData.observed_at >= start,
            WeatherData.observed_at <= end,
        )
        .order_by(WeatherData.observed_at.asc())
        .all()
    )


def geocode_place(name: str, country: str = "IN") -> list[dict]:
    params = {"name": name, "count": 8, "language": "en", "format": "json"}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(settings.open_meteo_geocode_url, params=params)
        response.raise_for_status()
        data = response.json()
    results = []
    for item in data.get("results") or []:
        if country and item.get("country_code") not in (country, "IN"):
            continue
        results.append(
            {
                "name": item.get("name"),
                "admin1": item.get("admin1"),
                "admin2": item.get("admin2"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
            }
        )
    return results
