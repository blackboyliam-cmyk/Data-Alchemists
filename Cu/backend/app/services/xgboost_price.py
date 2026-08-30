"""Optional XGBoost price forecasting used by the existing forecast service.

The application falls back to its existing linear trend forecast until a real
model has been trained from MarketPrice history. No synthetic data is used here.
"""
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import joblib
import pandas as pd
from sqlalchemy.orm import Session

from app.models import Crop, Market, MarketPrice

MODEL_DIR = Path(__file__).resolve().parents[2] / "ml" / "models"
MODEL_PATH = MODEL_DIR / "xgboost_price_model.joblib"
FEATURES_PATH = MODEL_DIR / "feature_columns.joblib"


def available() -> bool:
    return MODEL_PATH.exists() and FEATURES_PATH.exists()


def predict(db: Session, crop: Crop, market_id: int, horizon_days: int = 7) -> Optional[dict]:
    if not available():
        return None
    market = db.get(Market, market_id)
    if not market:
        return None
    rows = (
        db.query(MarketPrice)
        .filter(
            MarketPrice.crop_id == crop.id,
            MarketPrice.market_id == market_id,
            MarketPrice.modal_price.is_not(None),
        )
        .order_by(MarketPrice.price_date.asc())
        .all()
    )
    if len(rows) < 5:
        return None
    prices = [float(r.modal_price) for r in rows]
    target_date = rows[-1].price_date + timedelta(days=horizon_days)
    frame = pd.DataFrame([{
        "commodity": crop.name_en,
        "market": market.name,
        "year": target_date.year,
        "month": target_date.month,
        "day_of_week": target_date.weekday(),
        "lag_1": prices[-1],
        "lag_2": prices[-2],
        "lag_4": prices[-4],
        "rolling_mean_4": sum(prices[-4:]) / 4,
        "rolling_std_4": float(pd.Series(prices[-4:]).std(ddof=1)),
    }])
    columns = joblib.load(FEATURES_PATH)
    x = pd.get_dummies(frame, columns=["commodity", "market"], dtype=int)
    x = x.reindex(columns=columns, fill_value=0)
    model = joblib.load(MODEL_PATH)
    value = max(0.0, float(model.predict(x)[0]))
    return {
        "predicted_price": round(value, 2),
        "horizon_days": horizon_days,
        "method": "xgboost_regressor",
        "quality": "predicted",
        "disclaimer": "Prediction is based on historical market observations and is not guaranteed.",
    }
