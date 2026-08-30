import math
from datetime import datetime, timezone
from typing import Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Farm, Market, TransportConfig, TransportRoute

settings = get_settings()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def road_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    url = f"{settings.osrm_base_url.rstrip('/')}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.get(url, params={"overview": "false"})
            if response.status_code != 200:
                return None
            data = response.json()
            routes = data.get("routes") or []
            if not routes:
                return None
            meters = routes[0].get("distance")
            if meters is None:
                return None
            return round(meters / 1000.0, 2)
    except Exception:  # noqa: BLE001
        return None


def get_transport_config(db: Session) -> TransportConfig:
    cfg = db.query(TransportConfig).order_by(TransportConfig.id.asc()).first()
    if cfg:
        return cfg
    cfg = TransportConfig()
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def distance_and_cost(
    db: Session, farm: Farm, market: Market, quantity_quintals: float = 0
) -> dict:
    if market.latitude is None or market.longitude is None:
        return {
            "distance_km": None,
            "distance_type": "unknown",
            "distance_label": "Distance unknown — market location not set",
            "transport_cost": 0.0,
            "trips": 1,
            "cost_per_km": float(get_transport_config(db).cost_per_km),
        }
    cfg = get_transport_config(db)
    cached = (
        db.query(TransportRoute)
        .filter(TransportRoute.farm_id == farm.id, TransportRoute.market_id == market.id)
        .first()
    )
    distance = None
    dtype = "estimate"
    computed = cached.computed_at if cached else None
    if computed is not None and computed.tzinfo is None:
        computed = computed.replace(tzinfo=timezone.utc)
    if cached and computed and (datetime.now(timezone.utc) - computed).days < 14:
        distance = cached.distance_km
        dtype = cached.distance_type
    else:
        road = road_distance_km(farm.latitude, farm.longitude, market.latitude, market.longitude)
        if road is not None:
            distance = road
            dtype = "road"
        else:
            distance = round(haversine_km(farm.latitude, farm.longitude, market.latitude, market.longitude), 2)
            dtype = "estimate"
        cost_placeholder = distance * float(cfg.cost_per_km)
        if cached:
            cached.distance_km = distance
            cached.distance_type = dtype
            cached.cost = cost_placeholder
            cached.computed_at = datetime.now(timezone.utc)
        else:
            db.add(
                TransportRoute(
                    farm_id=farm.id,
                    market_id=market.id,
                    distance_km=distance,
                    distance_type=dtype,
                    cost=cost_placeholder,
                )
            )
        db.commit()

    capacity = float(cfg.truck_capacity_quintals) or 80
    trips = max(1, math.ceil(quantity_quintals / capacity)) if quantity_quintals else 1
    per_trip = distance * float(cfg.cost_per_km)
    total = per_trip * trips
    label = (
        f"Road distance {distance:.1f} km"
        if dtype == "road"
        else f"Estimated straight-line distance {distance:.1f} km (not actual road distance)"
    )
    return {
        "distance_km": distance,
        "distance_type": dtype,
        "distance_label": label,
        "transport_cost": round(total, 2),
        "trips": trips,
        "cost_per_km": float(cfg.cost_per_km),
        "formula": "Distance × ₹/km × number of trips",
    }


def nearby_markets(db: Session, farm: Farm, radius_km: float = 250, limit: int = 20) -> list[Tuple[Market, dict]]:
    markets = db.query(Market).filter(Market.is_active.is_(True)).all()
    ranked = []
    for market in markets:
        info = distance_and_cost(db, farm, market)
        if info["distance_km"] is None:
            continue
        if info["distance_km"] <= radius_km:
            ranked.append((market, info))
    ranked.sort(key=lambda x: x[1]["distance_km"])
    return ranked[:limit]
