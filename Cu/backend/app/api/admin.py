import io
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Crop,
    ImportFailure,
    Market,
    ProductionCost,
    StorageCrop,
    StorageFacility,
    SyncJob,
    TransportConfig,
    User,
)
from app.schemas import CropIn, MarketIn, ProductionCostIn, StorageIn, TransportConfigIn
from app.security import require_admin
from app.services.ingestion import fetch_agmarknet, ingest_dataframe

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _job_out(j: SyncJob) -> dict:
    return {
        "id": j.id,
        "source": j.source,
        "status": j.status,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "records_ok": j.records_ok,
        "records_failed": j.records_failed,
        "error_summary": j.error_summary,
        "details": j.details,
    }


@router.get("/sync-jobs")
def sync_jobs(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.query(SyncJob).order_by(SyncJob.id.desc()).limit(50).all()
    return [_job_out(j) for j in rows]


@router.get("/import-failures")
def import_failures(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.query(ImportFailure).order_by(ImportFailure.id.desc()).limit(200).all()
    return [
        {
            "id": r.id,
            "job_id": r.job_id,
            "reason": r.reason,
            "payload": r.payload,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/sync/mandi")
def sync_mandi(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    job = fetch_agmarknet(db)
    return _job_out(job)


@router.post("/import/prices")
async def import_prices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    raw = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw))
        elif name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            raise HTTPException(400, "Please upload a CSV or Excel file.")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Could not read file: {exc}") from exc
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    job = ingest_dataframe(db, records, source=f"upload:{file.filename}")
    return _job_out(job)


@router.get("/crops")
def admin_crops(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.query(Crop).order_by(Crop.name_en).all()
    return [
        {
            "id": c.id,
            "name_en": c.name_en,
            "name_hi": c.name_hi,
            "name_mr": c.name_mr,
            "agmarknet_names": c.agmarknet_names,
            "category": c.category,
            "spoilage_risk": c.spoilage_risk,
            "unit": c.unit,
            "is_active": c.is_active,
        }
        for c in rows
    ]


@router.post("/crops")
def create_crop(body: CropIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.query(Crop).filter(Crop.name_en == body.name_en).first():
        raise HTTPException(400, "A crop with this English name already exists.")
    crop = Crop(**body.model_dump())
    db.add(crop)
    db.commit()
    db.refresh(crop)
    return {"id": crop.id}


@router.put("/crops/{crop_id}")
def update_crop(crop_id: int, body: CropIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    crop = db.get(Crop, crop_id)
    if not crop:
        raise HTTPException(404, "Crop not found.")
    for k, v in body.model_dump().items():
        setattr(crop, k, v)
    db.commit()
    return {"ok": True}


@router.get("/markets")
def admin_markets(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.query(Market).order_by(Market.state, Market.name).all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "state": m.state,
            "district": m.district,
            "latitude": m.latitude,
            "longitude": m.longitude,
            "market_charges_percent": m.market_charges_percent,
            "storage_available": m.storage_available,
            "is_active": m.is_active,
            "source": m.source,
        }
        for m in rows
    ]


@router.post("/markets")
def create_market(body: MarketIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    market = Market(**body.model_dump(), source="admin")
    db.add(market)
    db.commit()
    db.refresh(market)
    return {"id": market.id}


@router.put("/markets/{market_id}")
def update_market(market_id: int, body: MarketIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    market = db.get(Market, market_id)
    if not market:
        raise HTTPException(404, "Market not found.")
    for k, v in body.model_dump().items():
        setattr(market, k, v)
    db.commit()
    return {"ok": True}


@router.get("/production-costs")
def list_costs(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.query(ProductionCost).all()
    return [
        {
            "id": r.id,
            "crop_id": r.crop_id,
            "crop": r.crop.name_en if r.crop else None,
            "season": r.season,
            "state": r.state,
            "seed_cost": float(r.seed_cost),
            "fertilizer_cost": float(r.fertilizer_cost),
            "pesticide_cost": float(r.pesticide_cost),
            "labour_cost": float(r.labour_cost),
            "irrigation_cost": float(r.irrigation_cost),
            "machinery_cost": float(r.machinery_cost),
            "other_cost": float(r.other_cost),
            "estimated_total": float(r.estimated_total),
            "expected_yield_quintal_per_hectare": float(r.expected_yield_quintal_per_hectare),
            "notes": r.notes,
        }
        for r in rows
    ]


@router.post("/production-costs")
def upsert_cost(body: ProductionCostIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    total = (
        body.seed_cost
        + body.fertilizer_cost
        + body.pesticide_cost
        + body.labour_cost
        + body.irrigation_cost
        + body.machinery_cost
        + body.other_cost
    )
    row = (
        db.query(ProductionCost)
        .filter(
            ProductionCost.crop_id == body.crop_id,
            ProductionCost.season == body.season,
            ProductionCost.state == body.state,
        )
        .first()
    )
    payload = body.model_dump()
    payload["estimated_total"] = total
    if row:
        for k, v in payload.items():
            setattr(row, k, v)
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(ProductionCost(**payload))
    db.commit()
    return {"ok": True, "estimated_total": total}


@router.get("/storage")
def list_storage(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.query(StorageFacility).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "state": s.state,
            "district": s.district,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "storage_type": s.storage_type,
            "capacity_quintals": float(s.capacity_quintals) if s.capacity_quintals is not None else None,
            "cost_per_day": float(s.cost_per_day),
            "availability": s.availability,
            "notes": s.notes,
            "is_active": s.is_active,
        }
        for s in rows
    ]


@router.post("/storage")
def create_storage(body: StorageIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    data = body.model_dump()
    crop_ids = data.pop("crop_ids", [])
    fac = StorageFacility(**data)
    db.add(fac)
    db.flush()
    for cid in crop_ids:
        db.add(StorageCrop(storage_id=fac.id, crop_id=cid))
    db.commit()
    return {"id": fac.id}


@router.put("/storage/{storage_id}")
def update_storage(storage_id: int, body: StorageIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    fac = db.get(StorageFacility, storage_id)
    if not fac:
        raise HTTPException(404, "Storage facility not found.")
    data = body.model_dump()
    crop_ids = data.pop("crop_ids", [])
    for k, v in data.items():
        setattr(fac, k, v)
    db.query(StorageCrop).filter(StorageCrop.storage_id == fac.id).delete()
    for cid in crop_ids:
        db.add(StorageCrop(storage_id=fac.id, crop_id=cid))
    db.commit()
    return {"ok": True}


@router.get("/transport")
def get_transport(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    cfg = db.query(TransportConfig).order_by(TransportConfig.id.asc()).first()
    if not cfg:
        return None
    return {
        "id": cfg.id,
        "cost_per_km": float(cfg.cost_per_km),
        "truck_capacity_quintals": float(cfg.truck_capacity_quintals),
        "notes": cfg.notes,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.put("/transport")
def put_transport(body: TransportConfigIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    cfg = db.query(TransportConfig).order_by(TransportConfig.id.asc()).first()
    if not cfg:
        cfg = TransportConfig()
        db.add(cfg)
    cfg.cost_per_km = body.cost_per_km
    cfg.truck_capacity_quintals = body.truck_capacity_quintals
    cfg.notes = body.notes
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
