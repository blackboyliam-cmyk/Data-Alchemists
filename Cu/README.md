# Farm-to-Market Decision Support System

A working, data-driven platform for small and marginal farmers in India. It helps decide **which crop to grow**, **which nearby mandi is most profitable after transport**, **when to sell vs store**, and **what price range to expect**.

This is not a static demo. Recommendations are computed from stored mandi prices, weather, distances, and costs. If live prices are missing, the UI says so instead of inventing numbers.

## Architecture

```
Government APIs / CSV uploads
        ↓
Data ingestion + validation
        ↓
PostgreSQL on Supabase (SQLite only if no URL is set)
        ↓
Profit / scoring / forecast engines
        ↓
REST API (FastAPI)
        ↓
Farmer + admin dashboards (React, mobile-first)
```

## What is real vs estimated vs predicted

| Data | Source | Label |
|---|---|---|
| Mandi min / max / modal price, arrivals | [data.gov.in AGMARKNET resource](https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070) or official CSV/Excel import | **Actual** |
| Current weather + 7-day forecast | [Open-Meteo](https://open-meteo.com/) (no key required) | Actual / **forecast** |
| Road distance | [OSRM](https://router.project-osrm.org) when reachable | Road |
| Straight-line distance | Haversine | **Estimated** (clearly labelled) |
| Production costs | Admin templates; farmers can override | Admin estimate or farmer-entered |
| Price forecast | Moving averages + linear trend on historical modal prices | **Predicted** (not guaranteed) |
| Demand | Arrivals, price change, season | **Estimated Demand** |

Crop ranking uses a **transparent weighted score**, not machine learning.

Market ranking uses **expected net profit**, not the highest raw mandi price.

## Quick start (this machine: Python + Node, no Docker)

The production database is **Supabase PostgreSQL**. If `SUPABASE_DB_URL` is empty, the API falls back to local SQLite so the UI can still start.

1. Copy environment file:

```powershell
copy .env.example .env
copy .env.example backend\.env
```

2. Get a free **data.gov.in API key** (required for live mandi sync): https://data.gov.in  
   Put it in `.env` as `DATA_GOV_IN_API_KEY`.  
   Do not invent keys or endpoints. The resource ID in `.env.example` is the official AGMARKNET daily-price dataset.

   If you cannot get a key yet, download an official AGMARKNET / data.gov.in CSV and upload it in the **Admin** screen. Column names should match `data/agmarknet_template.csv`.

3. Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

4. Frontend (another terminal):

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

Demo accounts (change after first login):

- Farmer: `farmer@farmdss.local` / `ChangeMeFarmer1!`
- Admin: `admin@farmdss.local` / `ChangeMeAdmin1!`

On first login, save **My farm** (search a village or keep the Panvel default) so nearby mandis and weather can be attached to a location.

## Database: Supabase Postgres

1. Open Supabase → **Project Settings → Database → Connection string → URI**
2. Put it in `backend/.env` as `SUPABASE_DB_URL` (paste the URI as copied; the app converts it for SQLAlchemy and enables SSL)
3. Prefer **Direct** (`db.<project-ref>.supabase.co:5432`) or **Session pooler** the first time, so tables can be created
4. Restart `uvicorn`. Startup creates tables and seeds crop/market metadata (not live mandi prices)

Alternatively:

```
SUPABASE_PROJECT_REF=your-project-ref
SUPABASE_DB_PASSWORD=your-database-password
```

Never put the database password in the frontend.

## Scheduled jobs

While the API process is running:

- Mandi sync every `SYNC_INTERVAL_MINUTES` (default 180)
- Weather refresh every `WEATHER_SYNC_INTERVAL_MINUTES` (default 60)

Admins can also click **Fetch latest mandi prices**.

## Main APIs

- `POST /api/auth/register` `POST /api/auth/login` `GET /api/auth/me`
- `GET/POST /api/farms`
- `GET /api/markets` `GET /api/markets/nearby`
- `GET /api/market-prices`
- `GET /api/weather`
- `GET /api/crops`
- `GET /api/crop-recommendations`
- `GET /api/market-recommendations?crop_id=`
- `GET /api/sell-recommendation?crop_id=`
- `GET /api/price-forecast?crop_id=`
- `GET /api/storage`
- `GET /api/transport-cost?market_id=`
- `GET /api/dashboard`
- Admin: `/api/admin/sync/mandi`, `/api/admin/import/prices`, crops, markets, production costs, storage, transport, sync jobs, import failures

## Tests

```powershell
cd backend
python -m pytest -q
```

## Languages

English, Hindi, and Marathi are wired from the first screen (UI + crop names). Add more strings in `frontend/src/i18n.js`.

## Security

API keys stay in environment variables. The React app never receives `DATA_GOV_IN_API_KEY`. JWT auth is required for farmer and admin routes. Uploaded files are validated before insert (dates, negative/unrealistic prices, duplicates upserted).

## XGBoost price prediction

The existing forecast service can use an XGBoost regressor when a model has been trained from real `MarketPrice` history. Until then, the existing linear-trend forecast remains the safe fallback, so the application does not fail just because no ML model exists yet.

Train from the backend database after importing enough official mandi history:

```powershell
cd backend
python -m ml.train_from_db
```

The trained artifacts are written to `backend/ml/models/` and are intentionally ignored by Git. The backend then uses the XGBoost prediction automatically for market-specific price forecasts when the artifacts are present.
