from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Crop, MarketPrice
from app.services.xgboost_price import predict as xgboost_predict


def series_for(db: Session, crop_id: int, market_id: Optional[int] = None, days: int = 180) -> list[tuple[date, float]]:
    q = (
        db.query(MarketPrice)
        .filter(
            MarketPrice.crop_id == crop_id,
            MarketPrice.modal_price.isnot(None),
            MarketPrice.price_date >= date.today() - timedelta(days=days),
        )
        .order_by(MarketPrice.price_date.asc())
    )
    if market_id:
        q = q.filter(MarketPrice.market_id == market_id)
    by_day: dict[date, list[float]] = {}
    for row in q.all():
        by_day.setdefault(row.price_date, []).append(float(row.modal_price))
    return [(d, sum(v) / len(v)) for d, v in sorted(by_day.items())]


def moving_average(values: list[float], window: int) -> Optional[float]:
    if len(values) < window:
        return None
    chunk = values[-window:]
    return round(sum(chunk) / len(chunk), 2)


def linear_forecast(series: list[tuple[date, float]], horizon_days: int = 7) -> Optional[dict]:
    """Ordinary least squares on day index. Not a guarantee — labelled as predicted."""
    if len(series) < 7:
        return None
    xs = list(range(len(series)))
    ys = [p for _, p in series]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = cov / var_x
    intercept = mean_y - slope * mean_x
    future_x = n - 1 + horizon_days
    predicted = intercept + slope * future_x
    if predicted <= 0:
        predicted = ys[-1]
    return {
        "predicted_price": round(predicted, 2),
        "horizon_days": horizon_days,
        "daily_slope": round(slope, 4),
        "method": "linear_regression_on_historical_modal_prices",
        "quality": "predicted",
        "disclaimer": "This is an estimated price based on recent historical trends, not a guaranteed price.",
    }


def forecast_bundle(db: Session, crop: Crop, market_id: Optional[int] = None) -> dict:
    series = series_for(db, crop.id, market_id)
    prices = [p for _, p in series]
    last7 = [p for d, p in series if d >= date.today() - timedelta(days=7)]
    last30 = [p for d, p in series if d >= date.today() - timedelta(days=30)]

    def trend(vals: list[float]) -> Optional[str]:
        if len(vals) < 3:
            return None
        change = vals[-1] - vals[0]
        pct = change / vals[0] * 100 if vals[0] else 0
        if pct > 3:
            return "up"
        if pct < -3:
            return "down"
        return "stable"

    ma7 = moving_average(prices, min(7, len(prices))) if prices else None
    ma30 = moving_average(prices, min(30, len(prices))) if prices else None
    vol = None
    if len(prices) >= 5:
        mean = sum(prices) / len(prices)
        vol = round((sum((p - mean) ** 2 for p in prices) / len(prices)) ** 0.5, 2)

    seasonal = None
    this_month = date.today().month
    month_prices = [p for d, p in series if d.month == this_month]
    if month_prices:
        seasonal = {
            "month": this_month,
            "average_this_month_in_history": round(sum(month_prices) / len(month_prices), 2),
            "observations": len(month_prices),
        }

    pred7 = xgboost_predict(db, crop, market_id, 7) if market_id else None
    if pred7 is None:
        pred7 = linear_forecast(series, 7)
    pred30 = xgboost_predict(db, crop, market_id, 30) if market_id else None
    if pred30 is None and len(series) >= 20:
        pred30 = linear_forecast(series, 30)

    latest = series[-1] if series else None
    return {
        "crop": crop.name_en,
        "observations": len(series),
        "latest_actual_modal_price": latest[1] if latest else None,
        "latest_actual_date": latest[0].isoformat() if latest else None,
        "trend_7_day": trend(last7),
        "trend_30_day": trend(last30),
        "change_7_day_percent": round((last7[-1] - last7[0]) / last7[0] * 100, 1) if len(last7) >= 2 and last7[0] else None,
        "change_30_day_percent": round((last30[-1] - last30[0]) / last30[0] * 100, 1) if len(last30) >= 2 and last30[0] else None,
        "moving_average_7": ma7,
        "moving_average_30": ma30,
        "volatility": vol,
        "seasonal_pattern": seasonal,
        "forecast_7_day": pred7,
        "forecast_30_day": pred30,
        "insufficient_history": len(series) < 7,
        "message": None
        if series
        else "Not enough historical market prices yet. Import AGMARKNET data or wait for a successful sync.",
    }


def demand_estimate(db: Session, crop: Crop, market_id: Optional[int] = None) -> dict:
    series = series_for(db, crop.id, market_id, days=60)
    q = (
        db.query(MarketPrice)
        .filter(
            MarketPrice.crop_id == crop.id,
            MarketPrice.price_date >= date.today() - timedelta(days=60),
        )
    )
    if market_id:
        q = q.filter(MarketPrice.market_id == market_id)
    rows = q.all()
    arrivals = [float(r.arrival_quantity) for r in rows if r.arrival_quantity]
    prices = [p for _, p in series]
    indicators = []
    score = 50.0
    if arrivals:
        avg_arr = sum(arrivals) / len(arrivals)
        recent = arrivals[-5:] if len(arrivals) >= 5 else arrivals
        recent_avg = sum(recent) / len(recent)
        indicators.append(f"Market arrivals (average {avg_arr:.1f} units in the last 60 days)")
        if recent_avg < avg_arr * 0.8:
            score += 15
            indicators.append("Recent arrivals are lower than usual, which can mean tighter supply")
        elif recent_avg > avg_arr * 1.2:
            score -= 10
            indicators.append("Recent arrivals are higher than usual, which can mean more supply in the mandi")
    else:
        indicators.append("Arrival quantities were not present in the government dataset for this crop")
    if len(prices) >= 5:
        indicators.append("Recent modal price movement")
        if prices[-1] > prices[0]:
            score += 10
            indicators.append("Prices have been rising, which can reflect stronger buying")
        elif prices[-1] < prices[0]:
            score -= 10
            indicators.append("Prices have been falling, which can reflect weaker buying")
    month = date.today().month
    indicators.append(f"Seasonal month indicator (month {month})")
    score = max(0, min(100, score))
    if score >= 65:
        label = "Higher estimated demand"
    elif score <= 40:
        label = "Lower estimated demand"
    else:
        label = "Average estimated demand"
    return {
        "label": "Estimated Demand",
        "band": label,
        "score_0_to_100": round(score, 1),
        "quality": "estimated",
        "indicators_used": indicators,
        "disclaimer": "This is estimated from measurable market indicators (arrivals, prices, season). It is not official demand data.",
        "has_arrival_data": bool(arrivals),
    }
