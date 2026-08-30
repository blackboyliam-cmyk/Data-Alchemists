from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Crop, CropSeason, Farm, Market, ScoringWeights, StorageCrop, StorageFacility
from app.services.forecast import demand_estimate
from app.services.geo import distance_and_cost, nearby_markets
from app.services.profit import current_season, historical_stats, latest_modal, production_for, profit_for_market
from app.services.risk import apply_relative_levels, combine_risk
from app.services.weather import heavy_rain_expected, upcoming_forecast


def crop_name(crop: Crop, lang: str) -> str:
    if lang == "hi" and crop.name_hi:
        return crop.name_hi
    if lang == "mr" and crop.name_mr:
        return crop.name_mr
    return crop.name_en


def weather_suitability(crop: Crop, farm: Farm, db: Session, season: str) -> dict:
    seasons = [s for s in crop.seasons if s.season == season] or crop.seasons
    in_season = False
    month = date.today().month
    for s in seasons:
        start, end = s.sowing_month_start, s.sowing_month_end
        if start <= end:
            in_season = start <= month <= end
        else:
            in_season = month >= start or month <= end
        if in_season:
            break
    forecast = upcoming_forecast(db, farm)
    rain = heavy_rain_expected(forecast)
    score = 0.7 if in_season else 0.35
    reasons = []
    if in_season:
        reasons.append(f"{crop.name_en} is usually sown in the current {season} window")
    else:
        reasons.append(f"{crop.name_en} is not in its main sowing window right now")
    if rain and crop.spoilage_risk == "high":
        score -= 0.25
        reasons.append("Heavy rain is expected, which is risky for this perishable crop")
    elif rain:
        score -= 0.05
        reasons.append("Rain is expected; field work may be delayed")
    return {"score": max(0.0, min(1.0, score)), "in_season": in_season, "heavy_rain": rain, "reasons": reasons}


def _minmax(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    lo, hi = min(values), max(values)
    if hi == lo:
        return lo, lo + 1.0
    return lo, hi


def scale(value: Optional[float], lo: float, hi: float, invert: bool = False) -> float:
    if value is None:
        return 0.4
    x = (value - lo) / (hi - lo)
    x = max(0.0, min(1.0, x))
    return 1 - x if invert else x


def evaluate_crop_market(db: Session, farm: Farm, crop: Crop, market: Market, season: str) -> Optional[dict]:
    prod = production_for(db, farm, crop, season)
    yld_ha = prod["expected_yield_quintal_per_hectare"]
    if not yld_ha:
        return None
    qty = yld_ha * farm.area_hectares
    price_row = latest_modal(db, crop, market.id, days=21)
    if not price_row or price_row.modal_price is None:
        return None
    modal = float(price_row.modal_price)
    min_p = float(price_row.min_price) if price_row.min_price is not None else None
    max_p = float(price_row.max_price) if price_row.max_price is not None else None
    geo = distance_and_cost(db, farm, market, qty)
    profit = profit_for_market(
        yield_quintals=qty,
        modal_price=modal,
        production_cost=prod["production_cost_per_hectare"] * farm.area_hectares,
        transport_cost=geo["transport_cost"] or 0,
        storage_cost=0,
        market_charges_percent=market.market_charges_percent or 0,
        area_hectares=farm.area_hectares,
    )
    stats = historical_stats(db, crop.id, market.id)
    demand = demand_estimate(db, crop, market.id)
    risk = combine_risk(db, crop, market.id, stats, demand, modal, min_p, max_p)
    return {
        "crop": crop,
        "market": market,
        "modal_price": modal,
        "min_price": min_p,
        "max_price": max_p,
        "price_date": price_row.price_date.isoformat(),
        "price_source": price_row.source,
        "price_quality": price_row.data_quality,
        "price_updated": price_row.ingested_at.isoformat() if price_row.ingested_at else None,
        "geo": geo,
        "profit": profit,
        "stats": stats,
        "demand": demand,
        "risk": risk,
        "production": prod,
        "quantity_quintals": qty,
    }


def rank_markets(db: Session, farm: Farm, crop: Crop, season: Optional[str] = None) -> dict:
    season = season or current_season()
    nearby = nearby_markets(db, farm)
    rows = []
    for market, _geo in nearby:
        ev = evaluate_crop_market(db, farm, crop, market, season)
        if ev:
            rows.append(ev)
    rows.sort(key=lambda r: r["profit"]["expected_net_profit"], reverse=True)
    if not rows:
        return {
            "crop": crop.name_en,
            "season": season,
            "markets": [],
            "message": "No nearby market has a recent modal price for this crop. Sync government data or import a CSV.",
            "best": None,
        }
    best = rows[0]
    apply_relative_levels([r["risk"] for r in rows])
    out = []
    for i, r in enumerate(rows):
        rec = "Best net profit after costs" if i == 0 else ""
        if i > 0 and r["modal_price"] > best["modal_price"]:
            rec = "Higher raw price, but lower profit after transport"
        out.append(
            {
                "market_id": r["market"].id,
                "market": r["market"].name,
                "district": r["market"].district,
                "state": r["market"].state,
                "modal_price": r["modal_price"],
                "price_range": {"min": r["min_price"], "max": r["max_price"]},
                "price_date": r["price_date"],
                "distance_km": r["geo"]["distance_km"],
                "distance_label": r["geo"]["distance_label"],
                "transport_cost": r["geo"]["transport_cost"],
                "market_charges": r["profit"]["market_charges"],
                "total_cost": r["profit"]["total_cost"],
                "expected_net_profit": r["profit"]["expected_net_profit"],
                "expected_revenue": r["profit"]["expected_revenue"],
                "production_cost": r["profit"]["production_cost"],
                "profit_per_hectare": r["profit"]["profit_per_hectare"],
                "area_hectares": farm.area_hectares,
                "farm_village": farm.village,
                "farm_district": farm.district,
                "yield_quintal_per_hectare": r["production"]["expected_yield_quintal_per_hectare"],
                "quantity_quintals": r["profit"]["quantity_quintals"],
                "break_even_price": r["profit"]["break_even_price"],
                "roi_percent": r["profit"]["expected_roi_percent"],
                "risk": r["risk"],
                "recommendation": rec or ("Consider" if i < 3 else ""),
                "freshness": {
                    "source": r["price_source"],
                    "last_updated": r["price_updated"],
                    "quality": r["price_quality"],
                    "price_date": r["price_date"],
                },
            }
        )
    gap = None
    if len(rows) > 1:
        gap = round(best["profit"]["expected_net_profit"] - rows[1]["profit"]["expected_net_profit"], 2)
    reason = (
        f"{best['market'].name} is expected to give you more money after transport and mandi charges"
        + (f" (about ₹{gap:,.0f} more than the next market)" if gap and gap > 0 else "")
        + f". Current modal price is ₹{best['modal_price']:,.0f} per quintal."
    )
    return {"crop": crop.name_en, "season": season, "markets": out, "best": out[0], "reason": reason}


def rank_crops(db: Session, farm: Farm, lang: str = "en", season: Optional[str] = None) -> dict:
    season = season or current_season()
    weights = db.query(ScoringWeights).order_by(ScoringWeights.id.asc()).first() or ScoringWeights()
    crops = db.query(Crop).filter(Crop.is_active.is_(True)).all()
    nearby = nearby_markets(db, farm)
    evaluations = []
    for crop in crops:
        best_ev = None
        for market, _ in nearby:
            ev = evaluate_crop_market(db, farm, crop, market, season)
            if ev and (best_ev is None or ev["profit"]["expected_net_profit"] > best_ev["profit"]["expected_net_profit"]):
                best_ev = ev
        if not best_ev:
            continue
        weather = weather_suitability(crop, farm, db, season)
        storage_ok = (
            db.query(StorageFacility)
            .join(StorageCrop, StorageCrop.storage_id == StorageFacility.id)
            .filter(StorageCrop.crop_id == crop.id, StorageFacility.is_active.is_(True))
            .count()
            > 0
        )
        evaluations.append({**best_ev, "weather": weather, "storage_ok": storage_ok})

    apply_relative_levels([e["risk"] for e in evaluations])

    if not evaluations:
        return {
            "season": season,
            "method": "weighted_score",
            "method_note": "Transparent weighted score. This is not a machine-learning model.",
            "crops": [],
            "message": "We do not have recent mandi prices for crops near your farm yet. Ask an administrator to sync government data or upload a CSV.",
        }

    profits = [e["profit"]["expected_net_profit"] for e in evaluations]
    prices = [e["modal_price"] for e in evaluations]
    hist = [e["stats"]["average"] or e["modal_price"] for e in evaluations]
    vols = [e["stats"]["volatility_ratio"] if e["stats"]["volatility_ratio"] is not None else 0.2 for e in evaluations]
    demands = [e["demand"]["score_0_to_100"] for e in evaluations]
    yields = [e["production"]["expected_yield_quintal_per_hectare"] for e in evaluations]
    costs = [e["production"]["production_cost_per_hectare"] for e in evaluations]
    trans = [e["geo"]["transport_cost"] or 0 for e in evaluations]
    plo, phi = _minmax(profits)
    prlo, prhi = _minmax(prices)
    hlo, hhi = _minmax(hist)
    vlo, vhi = _minmax(vols)
    dlo, dhi = _minmax(demands)
    ylo, yhi = _minmax(yields)
    clo, chi = _minmax(costs)
    tlo, thi = _minmax(trans)

    ranked = []
    for e in evaluations:
        parts = {
            "expected_profit": scale(e["profit"]["expected_net_profit"], plo, phi),
            "historical_price": scale(e["stats"]["average"] or e["modal_price"], hlo, hhi),
            "current_price": scale(e["modal_price"], prlo, prhi),
            "volatility": scale(e["stats"]["volatility_ratio"] if e["stats"]["volatility_ratio"] is not None else 0.2, vlo, vhi, invert=True),
            "demand": scale(e["demand"]["score_0_to_100"], dlo, dhi),
            "expected_yield": scale(e["production"]["expected_yield_quintal_per_hectare"], ylo, yhi),
            "production_cost": scale(e["production"]["production_cost_per_hectare"], clo, chi, invert=True),
            "weather": e["weather"]["score"],
            "transport": scale(e["geo"]["transport_cost"] or 0, tlo, thi, invert=True),
            "storage": 1.0 if e["storage_ok"] else 0.4,
        }
        score = (
            parts["expected_profit"] * weights.expected_profit
            + parts["historical_price"] * weights.historical_price
            + parts["current_price"] * weights.current_price
            + parts["volatility"] * weights.volatility
            + parts["demand"] * weights.demand
            + parts["expected_yield"] * weights.expected_yield
            + parts["production_cost"] * weights.production_cost
            + parts["weather"] * weights.weather
            + parts["transport"] * weights.transport
            + parts["storage"] * weights.storage
        )
        why = []
        if parts["expected_profit"] >= 0.7:
            why.append("expected profit is high")
        if parts["current_price"] >= 0.7:
            why.append("nearby market prices are favourable")
        if e["weather"]["in_season"]:
            why.append("weather / season conditions are suitable")
        if parts["transport"] >= 0.7:
            why.append("transport cost to a nearby mandi is low")
        if e["demand"]["score_0_to_100"] >= 65:
            why.append("estimated demand indicators look stronger")
        if not why:
            why.append("it is a reasonable option among crops with available mandi prices")
        name = crop_name(e["crop"], lang)
        reason = f"{name} is recommended because " + ", ".join(why) + "."
        ranked.append(
            {
                "crop_id": e["crop"].id,
                "crop": name,
                "crop_en": e["crop"].name_en,
                "score": round(score * 100, 1),
                "score_parts": {k: round(v, 3) for k, v in parts.items()},
                "weights": {
                    "expected_profit": weights.expected_profit,
                    "historical_price": weights.historical_price,
                    "current_price": weights.current_price,
                    "volatility": weights.volatility,
                    "demand": weights.demand,
                    "expected_yield": weights.expected_yield,
                    "production_cost": weights.production_cost,
                    "weather": weights.weather,
                    "transport": weights.transport,
                    "storage": weights.storage,
                },
                "best_market": e["market"].name,
                "best_market_id": e["market"].id,
                "modal_price": e["modal_price"],
                "expected_net_profit": e["profit"]["expected_net_profit"],
                "expected_revenue": e["profit"]["expected_revenue"],
                "production_cost": e["profit"]["production_cost"],
                "transport_cost": e["profit"]["transport_cost"],
                "profit_per_hectare": e["profit"]["profit_per_hectare"],
                "area_hectares": farm.area_hectares,
                "farm_village": farm.village,
                "farm_district": farm.district,
                "yield_quintal_per_hectare": e["production"]["expected_yield_quintal_per_hectare"],
                "quantity_quintals": e["profit"]["quantity_quintals"],
                "yield_source": e["production"].get("yield_source") or e["production"].get("source"),
                "profit_per_acre": e["profit"]["profit_per_acre"],
                "distance_km": e["geo"]["distance_km"],
                "risk": e["risk"],
                "reason": reason,
                "weather_notes": e["weather"]["reasons"],
                "demand": e["demand"],
                "freshness": {
                    "source": e["price_source"],
                    "last_updated": e["price_updated"],
                    "quality": e["price_quality"],
                    "price_date": e["price_date"],
                },
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return {
        "season": season,
        "method": "weighted_score",
        "method_note": "Transparent weighted score from profit, prices, weather, transport and other factors. This is not a machine-learning model.",
        "crops": ranked,
        "best": ranked[0] if ranked else None,
    }
