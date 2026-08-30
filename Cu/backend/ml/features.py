import pandas as pd

def add_features(df):
    out = df.copy().sort_values(["commodity", "market", "arrival_date"])
    g = out.groupby(["commodity", "market"], group_keys=False)

    out["year"] = out["arrival_date"].dt.year
    out["month"] = out["arrival_date"].dt.month
    out["day_of_week"] = out["arrival_date"].dt.dayofweek

    out["lag_1"] = g["modal_price"].shift(1)
    out["lag_2"] = g["modal_price"].shift(2)
    out["lag_4"] = g["modal_price"].shift(4)
    out["rolling_mean_4"] = g["modal_price"].transform(lambda s: s.shift(1).rolling(4).mean())
    out["rolling_std_4"] = g["modal_price"].transform(lambda s: s.shift(1).rolling(4).std())

    # One-hot encoding is done after the chronological split.
    return out.dropna().reset_index(drop=True)

def make_model_matrix(df):
    features = [
        "commodity", "market", "year", "month", "day_of_week",
        "lag_1", "lag_2", "lag_4", "rolling_mean_4", "rolling_std_4"
    ]
    X = pd.get_dummies(df[features], columns=["commodity", "market"], dtype=int)
    return X
