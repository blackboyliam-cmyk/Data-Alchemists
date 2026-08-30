import pandas as pd

NUMERIC_COLS = ["min_price", "max_price", "modal_price"]

def load_and_clean(path):
    df = pd.read_csv(path)
    df["arrival_date"] = pd.to_datetime(df["arrival_date"], errors="coerce")
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["arrival_date", "modal_price", "commodity", "market"])
    df = df.drop_duplicates()
    df = df[df["modal_price"] > 0].copy()
    return df.sort_values(["commodity", "market", "arrival_date"]).reset_index(drop=True)
