"""Combine price volatility, forecast uncertainty, and demand variability into low/med/high risk."""

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Crop, MarketPrice
from app.services.forecast import linear_forecast, series_for

# Equal mix of the three farmer-facing factors.
VOL_WEIGHT = 1 / 3
PRED_WEIGHT = 1 / 3
DEMAND_WEIGHT = 1 / 3


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _std(values: list[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


def _cv(values: list[float]) -> Optional[float]:
    if not values:
        return None
    mean = sum(values) / len(values)
    std = _std(values)
    if mean is None or mean == 0 or std is None:
        return None
    return std / abs(mean)


def _cv_score(cv: Optional[float], high_cv: float) -> Optional[float]:
    if cv is None:
        return None
    return _clip(100.0 * (cv / high_cv))


def _band(score: float) -> str:
    if score < 33:
        return "low"
    if score < 67:
        return "med"
    return "high"


def _pct_changes(prices: list[float]) -> list[float]:
    out = []
    for prev, cur in zip(prices, prices[1:]):
        if prev:
            out.append(abs(cur - prev) / prev)
    return out


def _volatility_score(prices: list[float], stats: dict, min_price: Optional[float], max_price: Optional[float], latest: Optional[float]) -> Optional[float]:
    cv = None
    if stats and stats.get("volatility_ratio") is not None and (stats.get("count") or 0) >= 5:
        cv = stats["volatility_ratio"]
    elif len(prices) >= 5:
        cv = _cv(prices)
    jumps = _pct_changes(prices[-12:]) if len(prices) >= 3 else []
    jump_cv = _cv(jumps) if jumps else None
    day_range = None
    if latest and min_price is not None and max_price is not None and latest > 0:
        day_range = max(0.0, (max_price - min_price) / latest)

    pieces = []
    if cv is not None:
        pieces.append(_cv_score(cv, high_cv=0.10))
    if jump_cv is not None:
        pieces.append(_cv_score(jump_cv, high_cv=0.06))
    if day_range is not None:
        pieces.append(_clip(100.0 * (day_range / 0.12)))
    if not pieces:
        return None
    return sum(pieces) / len(pieces)


def _prediction_score(series: list, latest_price: Optional[float]) -> Optional[float]:
    prices = [p for _, p in series]
    if len(prices) < 7:
        return None
    mean = sum(prices) / len(prices)
    pred = linear_forecast(series, 7)
    xs = list(range(len(prices)))
    mean_x = sum(xs) / len(xs)
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:
        return 70.0
    cov = sum((x - mean_x) * (y - mean) for x, y in zip(xs, prices))
    slope = cov / var_x
    intercept = mean - slope * mean_x
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, prices)]
    rmse = (sum(r * r for r in residuals) / len(residuals)) ** 0.5
    rmse_ratio = rmse / mean if mean else 0.2
    latest = latest_price or prices[-1]
    forecast_gap = 0.0
    if pred and latest:
        forecast_gap = abs(pred["predicted_price"] - latest) / latest
    recent = prices[-6:]
    recent_swing = (max(recent) - min(recent)) / mean if mean else 0
    thin = 25.0 if len(prices) < 16 else 0.0
    return _clip(
        40.0 * min(1.0, forecast_gap / 0.08)
        + 35.0 * min(1.0, rmse_ratio / 0.08)
        + 25.0 * min(1.0, recent_swing / 0.10)
        + thin
    )


def _demand_score(db: Session, crop: Crop, market_id: Optional[int], prices: list[float]) -> Optional[float]:
    q = db.query(MarketPrice).filter(
        MarketPrice.crop_id == crop.id,
        MarketPrice.price_date >= date.today() - timedelta(days=180),
    )
    if market_id:
        q = q.filter(MarketPrice.market_id == market_id)
    rows = q.order_by(MarketPrice.price_date.asc()).all()
    arrivals = [float(r.arrival_quantity) for r in rows if r.arrival_quantity]
    pieces = []
    if len(arrivals) >= 4:
        pieces.append(_cv_score(_cv(arrivals), high_cv=0.20))
        recent, older = arrivals[-4:], arrivals[:-4] or arrivals[:1]
        rmean = sum(recent) / len(recent)
        omean = sum(older) / len(older)
        if omean:
            pieces.append(_clip(100.0 * min(1.0, abs(rmean - omean) / omean / 0.35)))
    jumps = _pct_changes(prices[-10:]) if len(prices) >= 6 else []
    if jumps:
        pieces.append(_cv_score(_cv(jumps), high_cv=0.05))
    if not pieces:
        return None
    return sum(pieces) / len(pieces)


def _why(level: Optional[str], parts: dict, compared: bool = False) -> Optional[str]:
    if not level:
        return None
    labels = {"low": "low", "med": "medium", "high": "high"}
    vol = labels.get((parts.get("price_volatility") or {}).get("level"), "unclear")
    pred = labels.get((parts.get("prediction_uncertainty") or {}).get("level"), "unclear")
    dem = labels.get((parts.get("demand_variability") or {}).get("level"), "unclear")
    head = f"{labels[level].capitalize()} versus the other mandis shown" if compared else labels[level].capitalize()
    return (
        f"{head}. Price swings are {vol}, forecast uncertainty is {pred}, "
        f"and demand variability is {dem}."
    )


def combine_risk(
    db: Session,
    crop: Crop,
    market_id: Optional[int],
    stats: dict,
    demand: dict,
    latest_price: Optional[float],
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> dict:
    series = series_for(db, crop.id, market_id, days=180)
    prices = [p for _, p in series]
    vol_score = _volatility_score(prices, stats or {}, min_price, max_price, latest_price)
    pred_score = _prediction_score(series, latest_price)
    dem_score = _demand_score(db, crop, market_id, prices)
    parts_raw = {
        "price_volatility": vol_score,
        "prediction_uncertainty": pred_score,
        "demand_variability": dem_score,
    }
    usable = [(k, s) for k, s in parts_raw.items() if s is not None]
    if len(usable) < 3:
        combined = None
        level = None
    else:
        combined = round(
            parts_raw["price_volatility"] * VOL_WEIGHT
            + parts_raw["prediction_uncertainty"] * PRED_WEIGHT
            + parts_raw["demand_variability"] * DEMAND_WEIGHT,
            1,
        )
        level = _band(combined)
    parts = {
        k: {"score": round(v, 1), "level": _band(v)} if v is not None else {"score": None, "level": None}
        for k, v in parts_raw.items()
    }
    return {
        "level": level,
        "score_0_to_100": combined,
        "quality": "estimated" if level else "missing",
        "needs_data": [k for k, v in parts_raw.items() if v is None],
        "parts": parts,
        "why": _why(level, parts),
    }


def apply_relative_levels(risks: list[dict]) -> None:
    """Spread Low / Medium / High across a comparison set so nearby mandis are not all the same."""
    scored = [r for r in risks if r and r.get("score_0_to_100") is not None]
    if len(scored) < 2:
        for r in scored:
            r["why"] = _why(r.get("level"), r.get("parts") or {})
        return
    ordered = sorted(scored, key=lambda r: r["score_0_to_100"])
    n = len(ordered)
    for rank, r in enumerate(ordered):
        t = rank / (n - 1)
        if t < 1 / 3:
            r["level"] = "low"
        elif t < 2 / 3:
            r["level"] = "med"
        else:
            r["level"] = "high"
        r["why"] = _why(r["level"], r.get("parts") or {}, compared=True)
