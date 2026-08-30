from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_farm
from app.database import get_db
from app.models import Crop, Market, MarketPrice, User
from app.security import get_current_user
from app.services.geo import distance_and_cost, nearby_markets

router = APIRouter(tags=["markets"])


@router.get("/api/markets")
def list_markets(state: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Market).filter(Market.is_active.is_(True))
    if state:
        q = q.filter(Market.state.ilike(state))
    markets = q.order_by(Market.state, Market.district, Market.name).all()
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
            "source": m.source,
        }
        for m in markets
    ]


@router.get("/api/markets/nearby")
def markets_nearby(
    radius_km: float = Query(250, gt=0, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    farm = get_farm(db, user)
    rows = nearby_markets(db, farm, radius_km=radius_km)
    return {
        "farm": {"id": farm.id, "latitude": farm.latitude, "longitude": farm.longitude},
        "markets": [
            {
                "id": m.id,
                "name": m.name,
                "state": m.state,
                "district": m.district,
                "latitude": m.latitude,
                "longitude": m.longitude,
                **geo,
            }
            for m, geo in rows
        ],
    }


@router.get("/api/market-prices")
def market_prices(
    crop_id: int | None = None,
    market_id: int | None = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(MarketPrice).order_by(MarketPrice.price_date.desc(), MarketPrice.id.desc())
    if crop_id:
        q = q.filter(MarketPrice.crop_id == crop_id)
    if market_id:
        q = q.filter(MarketPrice.market_id == market_id)
    rows = q.limit(limit).all()
    if not rows:
        return {
            "prices": [],
            "message": "No mandi prices stored yet. Sync from data.gov.in or upload a CSV in the admin panel.",
            "freshness": {"quality": "missing", "source": "none", "last_updated": None, "stale": True},
        }
    return {
        "prices": [
            {
                "id": r.id,
                "market_id": r.market_id,
                "market": r.market.name if r.market else None,
                "crop_id": r.crop_id,
                "commodity": r.commodity_raw,
                "variety": r.variety,
                "date": r.price_date.isoformat(),
                "min_price": float(r.min_price) if r.min_price is not None else None,
                "max_price": float(r.max_price) if r.max_price is not None else None,
                "modal_price": float(r.modal_price) if r.modal_price is not None else None,
                "arrival_quantity": float(r.arrival_quantity) if r.arrival_quantity is not None else None,
                "unit": r.unit,
                "source": r.source,
                "quality": r.data_quality,
                "updated": r.ingested_at.isoformat() if r.ingested_at else None,
            }
            for r in rows
        ],
        "freshness": {
            "quality": rows[0].data_quality,
            "source": rows[0].source,
            "last_updated": rows[0].ingested_at.isoformat() if rows[0].ingested_at else None,
            "stale": False,
        },
    }


@router.get("/api/transport-cost")
def transport_cost(
    market_id: int,
    crop_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    farm = get_farm(db, user)
    market = db.get(Market, market_id)
    if not market:
        raise HTTPException(404, "Market not found.")
    qty = 0.0
    if crop_id:
        crop = db.get(Crop, crop_id)
        if crop:
            from app.services.profit import production_for

            prod = production_for(db, farm, crop)
            qty = (prod["expected_yield_quintal_per_hectare"] or 0) * farm.area_hectares
    return distance_and_cost(db, farm, market, qty)
