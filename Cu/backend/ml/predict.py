from pathlib import Path
import joblib
import pandas as pd

MODEL_DIR = Path("models")

def predict_price(commodity, market, date, lag_1, lag_2, lag_4, rolling_mean_4, rolling_std_4):
    model = joblib.load(MODEL_DIR / "xgboost_price_model.joblib")
    columns = joblib.load(MODEL_DIR / "feature_columns.joblib")

    row = pd.DataFrame([{
        "commodity": commodity,
        "market": market,
        "year": pd.Timestamp(date).year,
        "month": pd.Timestamp(date).month,
        "day_of_week": pd.Timestamp(date).dayofweek,
        "lag_1": lag_1,
        "lag_2": lag_2,
        "lag_4": lag_4,
        "rolling_mean_4": rolling_mean_4,
        "rolling_std_4": rolling_std_4,
    }])

    X = pd.get_dummies(row, columns=["commodity", "market"], dtype=int)
    X = X.reindex(columns=columns, fill_value=0)
    return float(model.predict(X)[0])
