from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Crop, Farm, FarmerCostOverride, MarketPrice, ProductionCost
from app.services import decimal_or_none


def current_season(today: Optional[date] = None) -> str:
    today = today or date.today()
    m = today.month
    if m in (6, 7, 8, 9, 10):
        return "kharif"
    if m in (11, 12, 1, 2, 3):
        return "rabi"
    return "zaid"


def latest_modal(db: Session, crop: Crop, market_id: Optional[int] = None, days: int = 14):
    q = db.query(MarketPrice).filter(
        MarketPrice.crop_id == crop.id,
        MarketPrice.modal_price.isnot(None),
        MarketPrice.price_date >= date.today() - timedelta(days=days),
    )
    if market_id:
        q = q.filter(MarketPrice.market_id == market_id)
    return q.order_by(MarketPrice.price_date.desc(), MarketPrice.ingested_at.desc()).first()


def historical_stats(db: Session, crop_id: int, market_id: Optional[int], days: int = 90) -> dict:
    q = db.query(MarketPrice).filter(
        MarketPrice.crop_id == crop_id,
        MarketPrice.modal_price.isnot(None),
        MarketPrice.price_date >= date.today() - timedelta(days=days),
    )
    if market_id:
        q = q.filter(MarketPrice.market_id == market_id)
    rows = q.order_by(MarketPrice.price_date.asc()).all()
    prices = [float(r.modal_price) for r in rows if r.modal_price is not None]
    if not prices:
        return {
            "count": 0,
            "average": None,
            "min": None,
            "max": None,
            "volatility": None,
            "latest_date": None,
            "latest_price": None,
        }
    mean = sum(prices) / len(prices)
    var = sum((p - mean) ** 2 for p in prices) / len(prices)
    std = var ** 0.5
    return {
        "count": len(prices),
        "average": round(mean, 2),
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "volatility": round(std, 2),
        "volatility_ratio": round(std / mean, 4) if mean else None,
        "latest_date": rows[-1].price_date.isoformat(),
        "latest_price": prices[-1],
        "source": rows[-1].source,
        "updated": rows[-1].ingested_at.isoformat() if rows[-1].ingested_at else None,
    }


def production_for(db: Session, farm: Farm, crop: Crop, season: Optional[str] = None) -> dict:
    season = season or current_season()
    override = (
        db.query(FarmerCostOverride)
        .filter(
            FarmerCostOverride.farm_id == farm.id,
            FarmerCostOverride.crop_id == crop.id,
            FarmerCostOverride.season == season,
        )
        .first()
    )
    template = (
        db.query(ProductionCost)
        .filter(ProductionCost.crop_id == crop.id, ProductionCost.state == farm.state, ProductionCost.season == season)
        .first()
    )
    if not template:
        template = db.query(ProductionCost).filter(ProductionCost.crop_id == crop.id).first()
    default_total = float(template.estimated_total) if template else 0.0
    default_yield = float(template.expected_yield_quintal_per_hectare) if template else 0.0
    total = decimal_or_none(override.total_production_cost) if override and override.total_production_cost is not None else default_total
    yld = (
        decimal_or_none(override.expected_yield_quintal_per_hectare)
        if override and override.expected_yield_quintal_per_hectare is not None
        else default_yield
    )
    yield_source = "farmer-entered" if override and override.expected_yield_quintal_per_hectare is not None else "admin estimate"
    ignored_yield = None
    # Typical Indian yields are well below 400 q/ha even for potato/tomato. A value like 10,000 is not a harvest.
    if yld and yld > 400:
        ignored_yield = yld
        yld = default_yield if default_yield and default_yield <= 400 else min(yld, 400)
        yield_source = "admin estimate (farmer yield ignored as unrealistic)"
    cost_source = "farmer-entered" if override and override.total_production_cost is not None else "admin estimate"
    breakdown = None
    if template:
        breakdown = {
            "seed": float(template.seed_cost),
            "fertilizer": float(template.fertilizer_cost),
            "pesticide": float(template.pesticide_cost),
            "labour": float(template.labour_cost),
            "irrigation": float(template.irrigation_cost),
            "machinery": float(template.machinery_cost),
            "other": float(template.other_cost),
        }
    return {
        "season": season,
        "production_cost_per_hectare": total,
        "expected_yield_quintal_per_hectare": yld,
        "farmer_override": bool(override),
        "source": cost_source if not ignored_yield else yield_source,
        "yield_source": yield_source,
        "ignored_unrealistic_yield": ignored_yield,
        "breakdown": breakdown,
        "notes": template.notes if template else "",
    }


def profit_for_market(
    yield_quintals: float,
    modal_price: float,
    production_cost: float,
    transport_cost: float,
    storage_cost: float,
    market_charges_percent: float,
    other_costs: float = 0.0,
    area_hectares: float = 1.0,
) -> dict:
    revenue = yield_quintals * modal_price
    charges = revenue * (market_charges_percent / 100.0)
    total_cost = production_cost + transport_cost + storage_cost + charges + other_costs
    net = revenue - total_cost
    profit_per_acre = net / (area_hectares * 2.47105) if area_hectares else None
    profit_per_quintal = net / yield_quintals if yield_quintals else None
    breakeven = total_cost / yield_quintals if yield_quintals else None
    roi = (net / total_cost * 100.0) if total_cost else None
    return {
        "expected_revenue": round(revenue, 2),
        "production_cost": round(production_cost, 2),
        "transport_cost": round(transport_cost, 2),
        "storage_cost": round(storage_cost, 2),
        "market_charges": round(charges, 2),
        "other_costs": round(other_costs, 2),
        "total_cost": round(total_cost, 2),
        "expected_net_profit": round(net, 2),
        "profit_per_acre": round(profit_per_acre, 2) if profit_per_acre is not None else None,
        "profit_per_hectare": round(net / area_hectares, 2) if area_hectares else None,
        "profit_per_quintal": round(profit_per_quintal, 2) if profit_per_quintal is not None else None,
        "break_even_price": round(breakeven, 2) if breakeven is not None else None,
        "expected_roi_percent": round(roi, 1) if roi is not None else None,
        "price_used": round(modal_price, 2),
        "price_kind": "modal",
        "quantity_quintals": round(yield_quintals, 2),
    }
