# DineTrack: restaurant demand forecasting and inventory

DineTrack forecasts how much of each dish a restaurant will sell over the next 7 days. It then turns that forecast into ingredient demand, stock alerts, purchase orders and waste warnings.

The project has two parts:

| Folder | What it is |
|---|---|
| [`new_backend/`](new_backend/) | FastAPI + pandas + statsmodels (ARIMA) API |
| [`DineTrack/`](DineTrack/) | React 18 + Vite dashboard (Recharts, lucide-react) |

## Running it

You need Python 3.12 and Node 22 (other recent versions are likely fine).

**1. Backend** (http://localhost:8000):

```bash
cd new_backend
pip install -r requirements.txt
python -m uvicorn app:app --port 8000
```

On startup the backend fits an ARIMA model for every menu item. Wait for `Application startup complete` (a few seconds) before opening the dashboard. Interactive API docs are at http://localhost:8000/docs.

**2. Frontend** (http://localhost:5173):

```bash
cd DineTrack
npm install
npm run dev
```

The backend only accepts browser requests from `http://localhost:5173` and `http://localhost:3000` (CORS). If Vite picks a different port because 5173 is busy, free the port, or add the new origin in [`app.py`](new_backend/app.py). To point the frontend at a backend elsewhere, set `VITE_API_URL` before `npm run dev`.

## Signing in

Every API route except sign-in, sign-up and the upload templates needs a signed-in user.

| Account | Email | Password | What it opens |
|---|---|---|---|
| AJ Fast Food (built in) | `admin@ajfastfood.com` | `ajfastfood123` | The live dashboard on the data in `new_backend/data/` |
| Any new sign-up | your email | your password (6+ characters) | An empty workspace with the same pages |

The built-in account is created on first start. To use different credentials, set `DINETRACK_DEMO_EMAIL` and `DINETRACK_DEMO_PASSWORD` before the **first** start, before `users.json` exists. Change them before you show this to anyone outside the project.

### Where accounts and their data are stored

| What | Where | Notes |
|---|---|---|
| Accounts | `new_backend/data/users.json` | Email, name, restaurant name, workspace, salt, PBKDF2-SHA256 password hash (200,000 iterations), created-at time. Plain-text passwords are never stored. |
| Token signing secret | `new_backend/data/.auth_secret` | Generated on first start. Login tokens are HMAC-signed and last 7 days. Deleting this file signs everyone out. |
| AJ Fast Food data | `new_backend/data/*.csv`, `settings.json` | The built-in restaurant. |
| Each new account's data | `new_backend/data/workspaces/<id>/` | `<id>` is the first 16 hex characters of the SHA-256 of the account's email. It holds the same file names as AJ's data, plus that account's `settings.json`. |

`users.json`, `.auth_secret` and `workspaces/` are in `.gitignore`, so accounts and uploaded data are never committed. There is no admin page: to remove an account, stop the backend, delete its entry from `users.json` and its `workspaces/<id>/` folder, then restart.

## Dashboard pages

- **Overview**: KPIs, actual-vs-predicted accuracy chart, critical stock, top forecast items, waste watch. New workspaces also show a setup checklist.
- **Point of Sale**: ring up orders. Each sale deducts recipe ingredients from inventory and is added to the sales history and sales log.
- **Sales Log**: orders rung up through POS.
- **Inventory**: stock, 7-day ingredient demand, days of stock, status (critical, low, normal, overstocked), suggested order.
- **Demand Forecast**: 7-day forecast per item, plus backtest accuracy per item.
- **Purchase Orders**: grocery list of low and critical ingredients.
- **Waste Control**: perishables with more stock than the next 7 days will use, with suggestions for using them up and a disposal route (compost for gardening, or donate).
- **Data Upload**: upload menu, inventory and sales files (see below).
- **Settings**: restaurant name, lead time, safety stock, status thresholds, auto-refresh.

## Uploading data

Every account, AJ Fast Food included, can upload CSV or Excel (`.xlsx`) files on the **Data Upload** page. Each upload recalculates the forecast, accuracy, stock status, orders and waste. Each card has a **Template** button with the expected columns. Column names are not case-sensitive.

| Dataset | Required columns | Optional columns |
|---|---|---|
| Menu & recipes | `item`, `ingredient`, `grams_per_serving`, `Unit` | `ShelfLifeDays`, `Storage` |
| Kitchen inventory | `Ingredient`, `Unit`, `Current_Inventory` | `Average_Daily_Usage`, `Target_Stock_Days`, `Category` (`Perishable` enables waste tracking) |
| Sales history | `Date`, `Item`, `Size` (`Half`, `Medium` or `Large`), `Quantity_Sold`, `Unit_Price` | `Total_Sales`, `Day` and `Month` are worked out automatically |

- Recipes describe a **Half** (base) serving. Medium counts as 1.35× and Large as 1.75×.
- The POS menu lists dishes that appear in the menu file, priced from the sales file, so it needs both.
- Sales uploads can **replace** the history or **add to** it.
- Uploading overwrites the current file. The previous version is kept next to it as `<file>.upload-backup`, one version only.

## How the numbers are produced

1. **Forecast** ([`forecasting.py`](new_backend/services/forecasting.py)): converts sales to base servings and fits ARIMA(2,1,2) per item on the daily series. Missing days count as zero sales. It forecasts 7 days ahead, and falls back to a 7-day average when an item has under 15 days of history or ARIMA fails.
2. **Accuracy** ([`accuracy.py`](new_backend/services/accuracy.py)): holds out the last 14 days, forecasts them from the history before, and compares total predicted volume with actual volume per item (a WAPE-style score). The overall score is weighted by each item's sales.
   - The predicted line on the Overview chart is nudged 30% toward actual for display only. The accuracy numbers use the raw forecast.
3. **Inventory** ([`inventory.py`](new_backend/services/inventory.py)): forecast × recipe gives 7-day ingredient demand. That gives days of stock, a reorder point (lead time + safety stock) and a suggested order.
4. **Waste** ([`waste.py`](new_backend/services/waste.py)): a perishable with excess stock after 7 days of demand is medium risk. If the excess exceeds the 7-day usage, it is high risk.

[`workspace.py`](new_backend/services/workspace.py) runs this pipeline for one restaurant's folder of files. [`app.py`](new_backend/app.py) picks the workspace for the signed-in account.

## About the AJ Fast Food data

- `two_month_sales_data.csv` holds real sales from **1 Mar to 13 Sep 2026**. The raw monthly exports are in [`new_backend/new data/`](new_backend/new%20data/).
- **14 Sep to 2 Nov 2026 is generated**, by [`scripts/generate_recent_sales.py`](new_backend/scripts/generate_recent_sales.py). Each generated day copies a real day from the same weekday, with demand spikes added:
  - weekends: ×1.15 on top of the existing weekend lift
  - Gandhi Jayanti, 2 Oct: ×1.35
  - Dussehra, 20 Oct: ×1.8
  - Karwa Chauth, 29 Oct: ×1.6
- The 14-day accuracy window is **20 Oct to 2 Nov**, so the reported ~89% accuracy is measured on generated data, not on real sales. Say so wherever the number is presented.
- To regenerate, run `python scripts/generate_recent_sales.py` from `new_backend/`. It rebuilds everything after 13 Sep from the real data.

## Folder layout

```text
.
├── DineTrack/                 React dashboard
│   ├── src/App.jsx            all pages and components
│   ├── src/styles.css         theme (dark and light) and layout
│   └── src/main.jsx
└── new_backend/
    ├── app.py                 FastAPI routes, auth, workspace lookup
    ├── requirements.txt
    ├── services/              forecasting, accuracy, inventory, waste, pos, settings, auth, workspace
    ├── scripts/               generate_recent_sales.py
    ├── new data/              raw monthly sales exports (.xlsx)
    └── data/
        ├── two_month_sales_data.csv       AJ sales history
        ├── current_kitchen_inventory.csv  AJ stock (POS sales change it)
        ├── menu_ingredient_level.csv      AJ recipes
        ├── pos_sales_log.csv              AJ POS orders
        ├── settings.json                  AJ settings
        ├── users.json, .auth_secret       accounts (not committed)
        └── workspaces/<id>/               other accounts' data (not committed)
```
