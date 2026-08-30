import json
from pathlib import Path
import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

from preprocessing import load_and_clean
from features import add_features, make_model_matrix

DATA = Path("data/raw/sample_maharashtra_mandi_demo.csv")
MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)

df = add_features(load_and_clean(DATA))
cutoff = df["arrival_date"].quantile(0.80)
train = df[df["arrival_date"] < cutoff].copy()
test = df[df["arrival_date"] >= cutoff].copy()

X_train = make_model_matrix(train)
X_test = make_model_matrix(test)
X_test = X_test.reindex(columns=X_train.columns, fill_value=0)
y_train, y_test = train["modal_price"], test["modal_price"]

model = XGBRegressor(
    n_estimators=400,
    learning_rate=0.05,
    max_depth=5,
    subsample=0.8,
    colsample_bytree=0.8,
    objective="reg:squarederror",
    random_state=42,
)
model.fit(X_train, y_train)

pred = model.predict(X_test)
metrics = {
    "MAE": float(mean_absolute_error(y_test, pred)),
    "RMSE": float(mean_squared_error(y_test, pred) ** 0.5),
    "R2": float(r2_score(y_test, pred)),
    "train_rows": int(len(train)),
    "test_rows": int(len(test)),
    "cutoff": str(cutoff.date()),
}

joblib.dump(model, MODEL_DIR / "xgboost_price_model.joblib")
joblib.dump(list(X_train.columns), MODEL_DIR / "feature_columns.joblib")
(MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

print(json.dumps(metrics, indent=2))
