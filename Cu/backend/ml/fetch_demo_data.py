import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

# Keep the demo small. Change these only after the pipeline works.
COMMODITIES = ["Tomato", "Onion", "Potato", "Soyabean", "Wheat"]
LIMIT_PER_COMMODITY = 100

def fetch_one(commodity):
    key = os.getenv("DATA_GOV_API_KEY")
    if not key:
        raise RuntimeError("Set DATA_GOV_API_KEY in .env")

    params = {
        "api-key": key,
        "format": "json",
        "limit": LIMIT_PER_COMMODITY,
        "filters[state.keyword]": "Maharashtra",
        "filters[commodity]": commodity,
    }
    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("records", [])

rows = []
for commodity in COMMODITIES:
    rows.extend(fetch_one(commodity))

df = pd.DataFrame(rows)
if df.empty:
    raise RuntimeError("No records returned. Check API key and exact commodity names.")

Path = "data/raw/maharashtra_mandi_demo.csv"
df.to_csv(Path, index=False)
print(f"Saved {len(df)} rows to {Path}")
