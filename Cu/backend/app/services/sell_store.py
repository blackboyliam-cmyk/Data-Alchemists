from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Crop, Farm, StorageCrop, StorageFacility
from app.services.forecast import forecast_bundle
from app.services.geo import distance_and_cost, nearby_markets
from app.services.profit import current_season, latest_modal, production_for, profit_for_market
from app.services.scoring import evaluate_crop_market, rank_markets
from app.services.weather import heavy_rain_expected, upcoming_forecast

SPOILAGE_DAILY = {"high": 0.02, "medium": 0.005, "low": 0.001}


def nearest_storage(db: Session, farm: Farm, crop: Crop):
    rows = (
        db.query(StorageFacility)
        .join(StorageCrop, StorageCrop.storage_id == StorageFacility.id)
        .filter(StorageCrop.crop_id == crop.id, StorageFacility.is_active.is_(True))
        .all()
    )
    best = None
    best_d = None
    for fac in rows:
        if fac.latitude is None or fac.longitude is None:
            continue
        from app.services.geo import haversine_km

        d = haversine_km(farm.latitude, farm.longitude, fac.latitude, fac.longitude)
        if best_d is None or d < best_d:
            best, best_d = fac, d
    return best, best_d


def sell_or_store(db: Session, farm: Farm, crop: Crop, market_id: int | None = None, hold_days: int = 14) -> dict:
    season = current_season()
    market_rank = rank_markets(db, farm, crop, season)
    if not market_rank["markets"]:
        return {
            "decision": "INSUFFICIENT_DATA",
            "message": "We cannot compare sell-now vs store without recent mandi prices for this crop.",
            "quality": "missing",
        }

    target = market_rank["markets"][0]
    if market_id:
        target = next((m for m in market_rank["markets"] if m["market_id"] == market_id), target)

    from app.models import Market

    market = db.get(Market, target["market_id"])
    ev = evaluate_crop_market(db, farm, crop, market, season)
    if not ev:
        return {"decision": "INSUFFICIENT_DATA", "message": "Missing price or production data.", "quality": "missing"}

    sell_now = ev["profit"]
    forecast = forecast_bundle(db, crop, market.id)
    pred = None
    if forecast.get("forecast_7_day") and hold_days <= 10:
        pred = forecast["forecast_7_day"]
    elif forecast.get("forecast_30_day"):
        pred = forecast["forecast_30_day"]

    future_price = pred["predicted_price"] if pred else None
    storage, storage_km = nearest_storage(db, farm, crop)
    daily_cost = float(storage.cost_per_day) if storage else 0.0
    storage_cost = daily_cost * hold_days
    extra_transport = 0.0
    if storage and storage.latitude is not None:
        extra_transport = (storage_km or 0) * ev["geo"]["cost_per_km"]
    spoilage_rate = SPOILAGE_DAILY.get(crop.spoilage_risk, 0.005) * hold_days
    qty_after = ev["quantity_quintals"] * (1 - min(spoilage_rate, 0.5))

    rain = heavy_rain_expected(upcoming_forecast(db, farm))
    risk_haircut = 0.04 if rain and crop.spoilage_risk == "high" else 0.02

    store_case = None
    if future_price:
        store_profit = profit_for_market(
            yield_quintals=qty_after,
            modal_price=future_price * (1 - risk_haircut),
            production_cost=ev["production"]["production_cost_per_hectare"] * farm.area_hectares,
            transport_cost=(ev["geo"]["transport_cost"] or 0) + extra_transport,
            storage_cost=storage_cost,
            market_charges_percent=market.market_charges_percent or 0,
            area_hectares=farm.area_hectares,
        )
        store_case = {
            "hold_days": hold_days,
            "estimated_future_price": future_price,
            "price_quality": "predicted",
            "risk_adjustment_percent": round(risk_haircut * 100, 1),
            "estimated_spoilage_percent": round(min(spoilage_rate, 0.5) * 100, 1),
            "storage_facility": storage.name if storage else None,
            "storage_cost": round(storage_cost, 2),
            "extra_handling_transport": round(extra_transport, 2),
            "profit": store_profit,
            "disclaimer": pred["disclaimer"] if pred else "Estimated from historical trends, not a guaranteed price.",
        }

    other_better = None
    if len(market_rank["markets"]) > 1:
        second = market_rank["markets"][1]
        if second["expected_net_profit"] > sell_now["expected_net_profit"] * 1.02:
            other_better = second

    decision = "SELL NOW"
    reasons = []
    if rain and crop.spoilage_risk == "high":
        decision = "SELL NOW"
        reasons.append("Heavy rain is expected and this crop spoils quickly, so waiting is risky.")
    elif store_case and store_case["profit"]["expected_net_profit"] > sell_now["expected_net_profit"] + 500:
        if crop.spoilage_risk == "high" and not (storage and storage.storage_type == "cold_storage"):
            decision = "SELL NOW"
            reasons.append("Prices may rise, but this crop needs better storage than we found nearby.")
        else:
            decision = "STORE"
            extra = store_case["profit"]["expected_net_profit"] - sell_now["expected_net_profit"]
            reasons.append(
                f"Storing about {hold_days} days is estimated to leave you ₹{extra:,.0f} better off after storage cost and likely spoilage."
            )
    elif other_better and other_better["expected_net_profit"] > sell_now["expected_net_profit"] + 1000:
        decision = "CONSIDER ANOTHER MARKET"
        reasons.append(
            f"{other_better['market']} is expected to give about ₹{other_better['expected_net_profit'] - sell_now['expected_net_profit']:,.0f} more profit after transport."
        )
    else:
        reasons.append(
            f"Selling now at {target['market']} is expected to give about ₹{sell_now['expected_net_profit']:,.0f} after costs."
        )
        if store_case:
            delta = store_case["profit"]["expected_net_profit"] - sell_now["expected_net_profit"]
            if delta <= 0:
                reasons.append("Holding the crop is not expected to pay enough extra to cover storage and spoilage.")

    return {
        "decision": decision,
        "reasons": reasons,
        "plain_language": " ".join(reasons),
        "sell_now": {
            "market": target["market"],
            "current_modal_price": ev["modal_price"],
            "price_quality": "actual" if ev["price_quality"] == "actual" else ev["price_quality"],
            "profit": sell_now,
            "freshness": {
                "source": ev["price_source"],
                "last_updated": ev["price_updated"],
                "quality": ev["price_quality"],
                "price_date": ev["price_date"],
            },
        },
        "store": store_case,
        "other_markets": market_rank["markets"][:5],
        "weather_warning": rain,
        "disclaimer": "These figures are estimates based on recent mandi prices and costs. They are not a guaranteed price.",
    }
