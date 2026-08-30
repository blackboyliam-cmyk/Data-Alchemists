from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_farm
from app.database import get_db
from app.models import Crop, Recommendation, StorageFacility, User
from app.security import get_current_user
from app.services.forecast import demand_estimate, forecast_bundle
from app.services.scoring import rank_crops, rank_markets
from app.services.sell_store import sell_or_store
from app.services.weather import store_weather_for_farm

router = APIRouter(tags=["recommendations"])


@router.get("/api/crop-recommendations")
def crop_recommendations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farm = get_farm(db, user)
    store_weather_for_farm(db, farm)
    data = rank_crops(db, farm, lang=user.preferred_language)
    db.add(Recommendation(farm_id=farm.id, rec_type="crop", payload={"best": data.get("best")}))
    db.commit()
    return data


@router.get("/api/market-recommendations")
def market_recommendations(crop_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farm = get_farm(db, user)
    crop = db.get(Crop, crop_id)
    if not crop:
        raise HTTPException(404, "Crop not found.")
    data = rank_markets(db, farm, crop)
    db.add(Recommendation(farm_id=farm.id, crop_id=crop.id, rec_type="market", payload={"best": data.get("best")}))
    db.commit()
    return data


@router.get("/api/sell-recommendation")
def sell_recommendation(
    crop_id: int,
    market_id: int | None = None,
    hold_days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    farm = get_farm(db, user)
    crop = db.get(Crop, crop_id)
    if not crop:
        raise HTTPException(404, "Crop not found.")
    data = sell_or_store(db, farm, crop, market_id=market_id, hold_days=hold_days)
    db.add(Recommendation(farm_id=farm.id, crop_id=crop.id, rec_type="sell_store", payload={"decision": data.get("decision")}))
    db.commit()
    return data


@router.get("/api/price-forecast")
def price_forecast(crop_id: int, market_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    crop = db.get(Crop, crop_id)
    if not crop:
        raise HTTPException(404, "Crop not found.")
    data = forecast_bundle(db, crop, market_id)
    data["demand"] = demand_estimate(db, crop, market_id)
    return data


@router.get("/api/storage")
def storage(crop_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(StorageFacility).filter(StorageFacility.is_active.is_(True))
    rows = q.all()
    out = []
    for s in rows:
        out.append(
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
            }
        )
    return out


@router.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farm = get_farm(db, user)
    store_weather_for_farm(db, farm)
    crops = rank_crops(db, farm, lang=user.preferred_language)
    best = crops.get("best")
    if not best:
        return {
            "has_data": False,
            "message": crops.get("message")
            or "No recommendation yet. We need mandi prices near your farm.",
            "crop_ranking": crops,
        }
    crop = db.get(Crop, best["crop_id"])
    markets = rank_markets(db, farm, crop)
    sell = sell_or_store(db, farm, crop)
    forecast = forecast_bundle(db, crop)
    price_lo = best.get("modal_price")
    price_hi = best.get("modal_price")
    if forecast.get("latest_actual_modal_price"):
        vol = forecast.get("volatility") or 0
        price_lo = max(0, forecast["latest_actual_modal_price"] - vol)
        price_hi = forecast["latest_actual_modal_price"] + vol
    return {
        "has_data": True,
        "today": {
            "best_crop": best["crop"],
            "best_crop_id": best["crop_id"],
            "best_market": best["best_market"],
            "best_market_id": best["best_market_id"],
            "expected_price_min": round(price_lo, 0) if price_lo else None,
            "expected_price_max": round(price_hi, 0) if price_hi else None,
            "expected_net_profit": best["expected_net_profit"],
            "profit_per_hectare": best.get("profit_per_hectare"),
            "area_hectares": best.get("area_hectares") or farm.area_hectares,
            "farm_village": best.get("farm_village") or farm.village,
            "farm_district": best.get("farm_district") or farm.district,
            "yield_quintal_per_hectare": best.get("yield_quintal_per_hectare"),
            "quantity_quintals": best.get("quantity_quintals"),
            "expected_revenue": best.get("expected_revenue"),
            "production_cost": best.get("production_cost"),
            "transport_cost": best.get("transport_cost"),
            "yield_source": best.get("yield_source"),
            "risk": best.get("risk"),
            "recommendation": sell.get("decision"),
            "reason": best["reason"],
            "sell_reason": sell.get("plain_language"),
            "freshness": best.get("freshness"),
        },
        "crop_ranking": crops,
        "market_ranking": markets,
        "sell": sell,
        "forecast": forecast,
    }
