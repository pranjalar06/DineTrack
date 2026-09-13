# DineTrack Dashboard

A responsive React + Vite dashboard for the supplied FastAPI restaurant inventory backend.

## What it connects to

The UI consumes the existing endpoints:

- `GET /api/dashboard`
- `GET /api/inventory`
- `GET /api/forecast`
- `GET /api/orders`
- `GET /api/waste`

The backend already enables CORS for `http://localhost:5173`, so this frontend is ready for the intended local setup.

## Run

### 1. Start the FastAPI backend

From the backend project root:

```bash
uvicorn app:app --reload --port 8000
```

### 2. Start DineTrack

Inside this folder:

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

If the API runs elsewhere:

```bash
# Windows PowerShell
$env:VITE_API_URL="http://localhost:8000"
npm run dev
```

## Dashboard design

- Overview: KPIs, 7-day demand curve, critical-stock alerts, top demand items, waste watch.
- Inventory: searchable stock table, coverage meters, status breakdown and recommended replenishment.
- Demand Forecast: daily forecast chart and item selector.
- Purchase Orders: selectable replenishment recommendations.
- Waste Control: high/medium risk ingredients and the backend-generated reduction suggestions.
- Responsive mobile navigation.
- Refresh/sync state and API connection error handling.

## Important backend note

The supplied `forecasting.py` accepts a `path` parameter in `load_sales(path)` but currently reads the hard-coded `data/two_month_sales_data.csv`. The dashboard does not modify that behavior; it simply consumes the resulting API data.
