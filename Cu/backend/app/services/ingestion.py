import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Crop, ImportFailure, Market, MarketPrice, SyncJob
from app.services import validate_price_row

logger = logging.getLogger("farmdss.ingestion")
settings = get_settings()

FILTER_KEYS = {
    "9ef84268-d588-465a-a308-a864a43d0070": {
        "state": "filters[state]",
        "date": "filters[arrival_date]",
        "commodity": "filters[commodity]",
        "fields": {
            "state": "state",
            "district": "district",
            "market": "market",
            "commodity": "commodity",
            "variety": "variety",
            "grade": "grade",
            "arrival_date": "arrival_date",
            "min_price": "min_price",
            "max_price": "max_price",
            "modal_price": "modal_price",
        },
    },
    "35985678-0d79-46b4-9ed6-6f13308a1d24": {
        "state": "filters[State]",
        "date": "filters[Arrival_Date]",
        "commodity": "filters[Commodity]",
        "fields": {
            "state": "State",
            "district": "District",
            "market": "Market",
            "commodity": "Commodity",
            "variety": "Variety",
            "grade": "Grade",
            "arrival_date": "Arrival_Date",
            "min_price": "Min_x0020_Price",
            "max_price": "Max_x0020_Price",
            "modal_price": "Modal_x0020_Price",
        },
    },
}


def _map_record(resource_id: str, raw: dict) -> dict:
    fields = FILTER_KEYS.get(resource_id, FILTER_KEYS["9ef84268-d588-465a-a308-a864a43d0070"])["fields"]
    mapped = {}
    for our, theirs in fields.items():
        mapped[our] = raw.get(theirs, raw.get(theirs.replace("_x0020_", " ")))
    if mapped.get("min_price") is None:
        mapped["min_price"] = raw.get("Min Price") or raw.get("min_price")
    if mapped.get("max_price") is None:
        mapped["max_price"] = raw.get("Max Price") or raw.get("max_price")
    if mapped.get("modal_price") is None:
        mapped["modal_price"] = raw.get("Modal Price") or raw.get("modal_price")
    mapped["arrival_quantity"] = raw.get("arrivals") or raw.get("Arrival") or raw.get("arrival")
    return mapped


def match_crop(db: Session, commodity: str) -> Optional[Crop]:
    name = (commodity or "").strip().lower()
    if not name:
        return None
    crops = db.query(Crop).filter(Crop.is_active.is_(True)).all()
    for crop in crops:
        aliases = [crop.name_en.lower()]
        aliases.extend([a.strip().lower() for a in (crop.agmarknet_names or "").split(",") if a.strip()])
        for alias in aliases:
            if alias and (alias == name or alias in name or name in alias):
                return crop
    return None


def get_or_create_market(db: Session, state: str, district: str, name: str) -> Market:
    existing = (
        db.query(Market)
        .filter(Market.name == name, Market.district == district, Market.state == state)
        .first()
    )
    if existing:
        return existing
    market = Market(name=name, state=state, district=district, source="agmarknet")
    db.add(market)
    db.flush()
    return market


def upsert_price(db: Session, cleaned: dict, source: str) -> str:
    crop = match_crop(db, cleaned["commodity"])
    market = get_or_create_market(db, cleaned["state"], cleaned["district"], cleaned["market"])
    existing = (
        db.query(MarketPrice)
        .filter(
            MarketPrice.market_id == market.id,
            MarketPrice.commodity_raw == cleaned["commodity"],
            MarketPrice.variety == cleaned["variety"],
            MarketPrice.grade == cleaned["grade"],
            MarketPrice.price_date == cleaned["price_date"],
        )
        .first()
    )
    fields = dict(
        crop_id=crop.id if crop else None,
        grade=cleaned["grade"],
        min_price=cleaned["min_price"],
        max_price=cleaned["max_price"],
        modal_price=cleaned["modal_price"],
        arrival_quantity=cleaned["arrival_quantity"],
        source=source,
        data_quality=cleaned["data_quality"],
        ingested_at=datetime.now(timezone.utc),
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        return "updated"
    db.add(
        MarketPrice(
            market_id=market.id,
            commodity_raw=cleaned["commodity"],
            variety=cleaned["variety"],
            price_date=cleaned["price_date"],
            unit="Rs/quintal",
            **fields,
        )
    )
    return "inserted"


def ingest_records(db: Session, records: list[dict], source: str, job: SyncJob) -> None:
    ok = fail = 0
    for raw in records:
        cleaned, error = validate_price_row(raw)
        if error:
            fail += 1
            db.add(ImportFailure(job_id=job.id, payload=raw if isinstance(raw, dict) else {"raw": str(raw)}, reason=error))
            continue
        try:
            upsert_price(db, cleaned, source)
            db.commit()
            ok += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            fail += 1
            logger.warning("Failed to upsert price: %s", exc)
            db.add(ImportFailure(job_id=job.id, payload=cleaned, reason=str(exc)[:500]))
            db.commit()
    job.records_ok += ok
    job.records_failed += fail
    db.commit()


def _http_client() -> httpx.Client:
    key = settings.data_gov_in_api_key
    return httpx.Client(
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 FarmDSS/1.0",
            "Authorization": key,
        },
        timeout=httpx.Timeout(90.0, connect=20.0),
        follow_redirects=True,
    )


def _fetch_page(client: httpx.Client, resource_id: str, params: dict) -> dict:
    url = f"{settings.data_gov_in_api_base.rstrip('/')}/{resource_id}"
    last_error = None
    for attempt in range(3):
        try:
            response = client.get(url, params=params)
            if response.status_code == 429:
                time.sleep(2 ** attempt)
                last_error = "Rate limited by data.gov.in"
                continue
            if response.status_code >= 500:
                time.sleep(2 ** attempt)
                last_error = f"Server error {response.status_code}"
                continue
            if response.status_code in (400, 401, 403):
                raise RuntimeError(
                    "data.gov.in rejected the request. Check DATA_GOV_IN_API_KEY at https://data.gov.in."
                )
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as exc:
            last_error = f"Network error: {exc}"
            time.sleep(2 ** attempt)
    raise RuntimeError(last_error or "Failed to fetch data.gov.in")


def fetch_agmarknet(db: Session, states: Optional[list[str]] = None) -> SyncJob:
    job = SyncJob(source="data.gov.in/AGMARKNET", status="running", details={})
    db.add(job)
    db.commit()
    db.refresh(job)

    if not settings.data_gov_in_api_key:
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.error_summary = (
            "No DATA_GOV_IN_API_KEY configured. Get a free key from https://data.gov.in "
            "or upload an official AGMARKNET CSV/Excel file in the admin panel."
        )
        db.commit()
        return job

    states = states or settings.mandi_states
    resource_ids = [settings.data_gov_in_resource_id]
    if settings.data_gov_in_fallback_resource_id:
        resource_ids.append(settings.data_gov_in_fallback_resource_id)

    collected: list[dict] = []
    used_resource = None
    errors: list[str] = []
    page_size = 50

    try:
        with _http_client() as client:
            for resource_id in resource_ids:
                keys = FILTER_KEYS.get(resource_id, FILTER_KEYS["9ef84268-d588-465a-a308-a864a43d0070"])
                try:
                    offset = 0
                    while len(collected) < settings.mandi_sync_max_records:
                        params = {
                            "api-key": settings.data_gov_in_api_key,
                            "format": "json",
                            "offset": offset,
                            "limit": min(page_size, settings.mandi_sync_max_records - len(collected)),
                        }
                        data = _fetch_page(client, resource_id, params)
                        records = data.get("records") or []
                        if not records:
                            break
                        mapped = [_map_record(resource_id, rec) for rec in records]
                        ingest_records(db, mapped, f"data.gov.in / AGMARKNET ({resource_id})", job)
                        collected.extend(mapped)
                        used_resource = resource_id
                        offset += len(records)
                        if len(records) < params["limit"]:
                            break
                    if collected:
                        break
                    for state in states:
                        if len(collected) >= settings.mandi_sync_max_records:
                            break
                        offset = 0
                        while len(collected) < settings.mandi_sync_max_records:
                            params = {
                                "api-key": settings.data_gov_in_api_key,
                                "format": "json",
                                "offset": offset,
                                "limit": min(page_size, settings.mandi_sync_max_records - len(collected)),
                                keys["state"]: state,
                            }
                            data = _fetch_page(client, resource_id, params)
                            records = data.get("records") or []
                            if not records:
                                break
                            mapped = [_map_record(resource_id, rec) for rec in records]
                            ingest_records(db, mapped, f"data.gov.in / AGMARKNET ({resource_id})", job)
                            collected.extend(mapped)
                            used_resource = resource_id
                            offset += len(records)
                            if len(records) < params["limit"]:
                                break
                    if collected:
                        break
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    errors.append(f"{resource_id}: {exc}")
                    logger.warning("Resource %s failed: %s", resource_id, exc)
                    continue
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.error_summary = str(exc)
        db.commit()
        return job

    if not collected:
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        job.error_summary = "No records returned. " + " | ".join(errors)
        job.details = {"errors": errors}
        db.commit()
        return job

    job.status = "success" if job.records_failed == 0 else "partial"
    job.finished_at = datetime.now(timezone.utc)
    job.details = {"resource_id": used_resource, "states": states, "fetched": len(collected), "errors": errors}
    if errors:
        job.error_summary = " | ".join(errors)[:2000]
    db.commit()
    return job


def ingest_dataframe(db: Session, records: list[dict], source: str) -> SyncJob:
    job = SyncJob(source=source, status="running")
    db.add(job)
    db.commit()
    db.refresh(job)
    ingest_records(db, records, source, job)
    job.status = "success" if job.records_failed == 0 else "partial"
    if job.records_ok == 0:
        job.status = "failed"
        job.error_summary = "No valid rows imported. Check column names (State, District, Market, Commodity, Arrival_Date, Min_Price, Max_Price, Modal_Price)."
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    return job
