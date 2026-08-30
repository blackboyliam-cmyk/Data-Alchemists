"""Train the XGBoost price model from the application's MarketPrice database table.

Run from the backend directory:
    python -m ml.train_from_db

The script refuses to train when there is not enough real/ingested price history.
It never fabricates training observations.
"""
from pathlib import Path
import json
import joblib
import pandas as pd
from sqlalchemy import select
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from app.database import SessionLocal
from app.models import Crop, Market, MarketPrice

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(exist_ok=True)


def load_prices() -> pd.DataFrame:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                MarketPrice.price_date,
                MarketPrice.modal_price,
                MarketPrice.arrival_quantity,
                Crop.name_en.label("commodity"),
                Market.name.label("market"),
            )
            .join(Crop, Crop.id == MarketPrice.crop_id)
            .join(Market, Market.id == MarketPrice.market_id)
            .where(MarketPrice.modal_price.is_not(None))
            .order_by(MarketPrice.price_date.asc())
        ).all()
    return pd.DataFrame(rows, columns=["arrival_date", "modal_price", "arrival_quantity", "commodity", "market"])


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["arrival_date"] = pd.to_datetime(df["arrival_date"], errors="coerce")
    df["modal_price"] = pd.to_numeric(df["modal_price"], errors="coerce")
    df["arrival_quantity"] = pd.to_numeric(df["arrival_quantity"], errors="coerce")
    df = df.dropna(subset=["arrival_date", "modal_price", "commodity", "market"])
    df = df[df["modal_price"] > 0].sort_values(["commodity", "market", "arrival_date"])
    g = df.groupby(["commodity", "market"], group_keys=False)
    df["year"] = df["arrival_date"].dt.year
    df["month"] = df["arrival_date"].dt.month
    df["day_of_week"] = df["arrival_date"].dt.dayofweek
    df["lag_1"] = g["modal_price"].shift(1)
    df["lag_2"] = g["modal_price"].shift(2)
    df["lag_4"] = g["modal_price"].shift(4)
    df["rolling_mean_4"] = g["modal_price"].transform(lambda s: s.shift(1).rolling(4).mean())
    df["rolling_std_4"] = g["modal_price"].transform(lambda s: s.shift(1).rolling(4).std())
    return df.dropna(subset=["lag_1", "lag_2", "lag_4", "rolling_mean_4", "rolling_std_4"]).reset_index(drop=True)


def matrix(df: pd.DataFrame, columns=None):
    cols = ["commodity", "market", "year", "month", "day_of_week", "lag_1", "lag_2", "lag_4", "rolling_mean_4", "rolling_std_4"]
    x = pd.get_dummies(df[cols], columns=["commodity", "market"], dtype=int)
    if columns is not None:
        x = x.reindex(columns=columns, fill_value=0)
    return x


def main():
    df = make_features(load_prices())
    if len(df) < 50:
        raise SystemExit(f"Not enough price observations to train safely: {len(df)} rows. Import more official mandi history first.")
    cutoff = df["arrival_date"].quantile(0.80)
    train, test = df[df["arrival_date"] < cutoff], df[df["arrival_date"] >= cutoff]
    if train.empty or test.empty:
        raise SystemExit("Chronological train/test split could not be created.")
    x_train = matrix(train)
    x_test = matrix(test, list(x_train.columns))
    y_train, y_test = train["modal_price"], test["modal_price"]
    model = XGBRegressor(
        n_estimators=400, learning_rate=0.05, max_depth=5,
        subsample=0.8, colsample_bytree=0.8,
        objective="reg:squarederror", random_state=42,
    )
    model.fit(x_train, y_train)
    pred = model.predict(x_test)
    metrics = {
        "MAE": float(mean_absolute_error(y_test, pred)),
        "RMSE": float(mean_squared_error(y_test, pred) ** 0.5),
        "R2": float(r2_score(y_test, pred)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "cutoff": str(cutoff.date()),
        "source": "application MarketPrice table",
    }
    joblib.dump(model, MODEL_DIR / "xgboost_price_model.joblib")
    joblib.dump(list(x_train.columns), MODEL_DIR / "feature_columns.joblib")
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
