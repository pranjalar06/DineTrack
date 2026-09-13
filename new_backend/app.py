import os
import threading
import uuid
from datetime import date, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import pandas as pd

from services.forecasting import (
    load_sales,
    forecast_all_items,
    trim_sparse_trailing_days,
    SIZE_MULTIPLIER
)

from services.inventory import (
    calculate_inventory_status
)

from services.waste import (
    calculate_waste
)

from services.accuracy import (
    backtest_accuracy
)

from services.pos import (
    build_menu,
    compute_consumption
)

from services.settings import (
    load_settings,
    save_settings
)


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title="Food Demand & Inventory API",
    description=(
        "ARIMA-based food demand forecasting, "
        "inventory monitoring and waste reduction API"
    ),
    version="1.0.0"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173"
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"]
)


# =========================================================
# FILE PATHS
# =========================================================

SALES_FILE = (
    "data/two_month_sales_data.csv"
)

INVENTORY_FILE = (
    "data/current_kitchen_inventory.csv"
)

RECIPES_FILE = (
    "data/menu_ingredient_level.csv"
)

RAW_SALES_COLUMNS = [
    "Date", "Item", "Size", "Quantity_Sold",
    "Unit_Price", "Total_Sales", "Day", "Month"
]

POS_LOG_FILE = (
    "data/pos_sales_log.csv"
)

POS_LOG_COLUMNS = [
    "OrderId", "Timestamp", "Item", "Size",
    "Quantity", "Unit_Price", "Line_Total"
]

SETTINGS_FILE = (
    "data/settings.json"
)


# =========================================================
# LOAD DATA
# =========================================================

sales = load_sales(
    SALES_FILE
)

inventory = pd.read_csv(
    INVENTORY_FILE
)

recipes = pd.read_csv(
    RECIPES_FILE
)

# Ingredient -> menu items that use it, for surfacing "push these dishes"
# suggestions on the waste control page.
ingredient_dishes = (
    recipes
    .groupby("ingredient")["item"]
    .apply(lambda s: sorted(set(s)))
    .to_dict()
)

if os.path.exists(POS_LOG_FILE):

    pos_log = pd.read_csv(POS_LOG_FILE)

else:

    pos_log = pd.DataFrame(columns=POS_LOG_COLUMNS)
    pos_log.to_csv(POS_LOG_FILE, index=False)

settings = load_settings(SETTINGS_FILE)


# =========================================================
# FORECAST
# =========================================================

# Forecasting/backtesting run only over clean, fully-logged trading
# days — see trim_sparse_trailing_days(). `sales` itself stays the
# full history (including any live POS-appended rows) for everything
# else (dashboard sales period, sales log, etc).
history_sales = trim_sparse_trailing_days(sales)

forecast = forecast_all_items(
    history_sales,
    days=7
)


# =========================================================
# INVENTORY ANALYSIS
# =========================================================

def build_inventory_status():

    return calculate_inventory_status(
        inventory,
        forecast,
        recipes,
        lead_time_days=settings["lead_time_days"],
        safety_stock_days=settings["safety_stock_days"],
        critical_days=settings["critical_days"],
        low_days=settings["low_days"],
        normal_days=settings["normal_days"]
    )


inventory_status = build_inventory_status()


# =========================================================
# WASTE ANALYSIS
# =========================================================

waste_analysis = (
    calculate_waste(
        inventory_status,
        forecast
    )
)


# =========================================================
# MODEL ACCURACY (BACKTEST)
# =========================================================

model_accuracy = backtest_accuracy(
    history_sales,
    holdout_days=13
)


# =========================================================
# POS MENU
# =========================================================

menu = build_menu(sales)


# =========================================================
# POS SALE LOCK
# =========================================================

sale_lock = threading.Lock()


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    return {

        "message":
            "Food Forecasting API",

        "status":
            "running",

        "docs":
            "/docs"

    }


# =========================================================
# FORECAST API
# =========================================================

@app.get("/api/forecast")
def get_forecast():

    data = forecast.copy()

    return {

        "forecast_days": 7,

        "last_historical_date":
            sales["Date"].max()
            .strftime("%Y-%m-%d"),

        "forecast": data.to_dict(
            orient="records"
        )

    }


# =========================================================
# ITEM FORECAST
# =========================================================

@app.get("/api/forecast/{item_name}")
def get_item_forecast(
    item_name: str
):

    result = forecast[
        forecast["item"].str.lower()
        ==
        item_name.lower()
    ]

    if result.empty:

        raise HTTPException(
            status_code=404,
            detail="Item not found"
        )

    return {
        "item": item_name,
        "forecast": result.to_dict(
            orient="records"
        )
    }


# =========================================================
# INVENTORY
# =========================================================

@app.get("/api/inventory")
def get_inventory():

    # waste_analysis is inventory_status plus the waste-risk columns
    # (Waste_Risk, Expected_Excess, Waste_Reduction_Suggestion), so
    # returning it gives the Inventory tab reorder status and waste
    # flags in one call.
    return {

        "inventory":
            waste_analysis.to_dict(
                orient="records"
            )

    }


# =========================================================
# CRITICAL INVENTORY
# =========================================================

@app.get("/api/inventory/critical")
def get_critical_inventory():

    critical = inventory_status[
        inventory_status["Status"]
        == "CRITICAL"
    ]

    return {

        "count":
            len(critical),

        "items":
            critical.to_dict(
                orient="records"
            )

    }


# =========================================================
# LOW INVENTORY
# =========================================================

@app.get("/api/inventory/low")
def get_low_inventory():

    low = inventory_status[
        inventory_status["Status"].isin(
            ["CRITICAL", "LOW"]
        )
    ]

    return {

        "count":
            len(low),

        "items":
            low.to_dict(
                orient="records"
            )

    }


# =========================================================
# ORDER RECOMMENDATIONS
# =========================================================

@app.get("/api/orders")
def get_order_recommendations():

    orders = inventory_status[
        inventory_status["Status"].isin(["CRITICAL", "LOW"])
        | (inventory_status["Suggested_Order"] > 0)
    ].copy()

    return {

        "orders":
            orders[
                [
                    "Ingredient",
                    "Unit",
                    "Current_Inventory",
                    "Forecast_7_Day_Demand",
                    "Days_of_Stock",
                    "Status",
                    "Suggested_Order"
                ]
            ].to_dict(
                orient="records"
            )

    }


# =========================================================
# WASTE
# =========================================================

@app.get("/api/waste")
def get_waste():

    waste = waste_analysis[
        waste_analysis["Waste_Risk"]
        != "LOW"
    ].copy()

    waste["Used_In"] = waste["Ingredient"].map(
        lambda name: ingredient_dishes.get(name, [])
    )

    return {

        "count":
            len(waste),

        "waste_risk":
            waste[
                [
                    "Ingredient",
                    "Unit",
                    "Current_Inventory",
                    "Expected_7_Day_Usage",
                    "Expected_Excess",
                    "Waste_Risk",
                    "Waste_Reduction_Suggestion",
                    "Used_In"
                ]
            ].to_dict(
                orient="records"
            )

    }


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/api/dashboard")
def get_dashboard():

    critical = inventory_status[
        inventory_status["Status"]
        == "CRITICAL"
    ]

    low = inventory_status[
        inventory_status["Status"]
        == "LOW"
    ]

    orders = inventory_status[
        inventory_status["Status"].isin(["CRITICAL", "LOW"])
        | (inventory_status["Suggested_Order"] > 0)
    ]

    waste = waste_analysis[
        waste_analysis["Waste_Risk"]
        != "LOW"
    ]

    return {

        "sales_period": {

            "start":
                sales["Date"]
                .min()
                .strftime("%Y-%m-%d"),

            "end":
                sales["Date"]
                .max()
                .strftime("%Y-%m-%d")
        },

        "forecast": {

            "days": 7,

            "total_expected_units":
                round(
                    forecast[
                        "forecast_quantity"
                    ].sum(),
                    2
                )
        },

        "inventory": {

            "total_ingredients":
                len(inventory_status),

            "critical":
                len(critical),

            "low":
                len(low),

            "orders_required":
                len(orders),

            "waste_risk_items":
                len(waste)
        },

        "model_accuracy":
            model_accuracy["overall"],

        "critical_items":
            critical[
                [
                    "Ingredient",
                    "Current_Inventory",
                    "Days_of_Stock"
                ]
            ].to_dict(
                orient="records"
            ),

        "orders":
            orders[
                [
                    "Ingredient",
                    "Unit",
                    "Suggested_Order"
                ]
            ].to_dict(
                orient="records"
            ),

        "waste":
            waste[
                [
                    "Ingredient",
                    "Expected_Excess",
                    "Waste_Risk"
                ]
            ].to_dict(
                orient="records"
            )
    }


# =========================================================
# MODEL ACCURACY
# =========================================================

@app.get("/api/accuracy")
def get_accuracy():

    return model_accuracy


# =========================================================
# POS MENU
# =========================================================

@app.get("/api/menu")
def get_menu():

    return {
        "menu": menu
    }


# =========================================================
# POS SALE
# =========================================================

class SaleLine(BaseModel):
    item: str
    size: str
    quantity: float


class SaleRequest(BaseModel):
    cart: list[SaleLine]


@app.post("/api/pos/sale")
def post_sale(
    request: SaleRequest
):

    global inventory, sales, inventory_status, waste_analysis, pos_log

    cart = [line.model_dump() for line in request.cart]

    if not cart:
        raise HTTPException(
            status_code=400,
            detail="Cart is empty"
        )

    try:

        consumption = compute_consumption(
            cart,
            recipes
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    menu_lookup = {
        (m["item"], s["size"]): s["price"]
        for m in menu
        for s in m["sizes"]
    }

    for line in cart:
        key = (line["item"], line["size"])
        if key not in menu_lookup:
            raise HTTPException(
                status_code=400,
                detail=f"{line['item']} ({line['size']}) is not on the menu"
            )

    with sale_lock:

        # ---------------------------------------------
        # Deduct consumption from inventory
        # ---------------------------------------------

        updated_inventory = inventory.copy()
        shortfalls = []
        consumed = []

        for _, row in consumption.iterrows():

            mask = (
                (updated_inventory["Ingredient"] == row["ingredient"])
                &
                (updated_inventory["Unit"] == row["unit"])
            )

            if not mask.any():
                continue

            idx = updated_inventory[mask].index[0]

            current = float(updated_inventory.loc[idx, "Current_Inventory"])
            new_value = current - float(row["required"])

            consumed.append({
                "ingredient": row["ingredient"],
                "unit": row["unit"],
                "consumed": round(float(row["required"]), 2),
                "remaining": round(max(new_value, 0), 2)
            })

            if new_value < 0:
                shortfalls.append({
                    "ingredient": row["ingredient"],
                    "unit": row["unit"],
                    "short_by": round(abs(new_value), 2)
                })

            updated_inventory.loc[idx, "Current_Inventory"] = max(new_value, 0)

        # ---------------------------------------------
        # Append sale rows to sales history
        # ---------------------------------------------

        today = date.today()

        new_rows = []

        for line in cart:

            price = menu_lookup[(line["item"], line["size"])]
            quantity = line["quantity"]

            new_rows.append({
                "Date": pd.Timestamp(today),
                "Item": line["item"],
                "Size": line["size"],
                "Quantity_Sold": quantity,
                "Unit_Price": price,
                "Total_Sales": price * quantity,
                "Day": today.strftime("%A"),
                "Month": today.strftime("%Y-%m")
            })

        new_sales_rows = pd.DataFrame(new_rows)[RAW_SALES_COLUMNS]

        # ---------------------------------------------
        # Record the order in the POS sales log
        # (kept separate from the raw sales history —
        # this is what the Sales Log tab reads from)
        # ---------------------------------------------

        order_id = uuid.uuid4().hex[:10]
        timestamp = datetime.now().isoformat(timespec="seconds")

        order_items = []
        log_rows = []

        for line in cart:

            price = menu_lookup[(line["item"], line["size"])]
            quantity = line["quantity"]
            line_total = round(price * quantity, 2)

            order_items.append({
                "item": line["item"],
                "size": line["size"],
                "quantity": quantity,
                "price": price,
                "line_total": line_total
            })

            log_rows.append({
                "OrderId": order_id,
                "Timestamp": timestamp,
                "Item": line["item"],
                "Size": line["size"],
                "Quantity": quantity,
                "Unit_Price": price,
                "Line_Total": line_total
            })

        order = {
            "order_id": order_id,
            "timestamp": timestamp,
            "items": order_items,
            "total": round(sum(i["line_total"] for i in order_items), 2)
        }

        new_log_rows = pd.DataFrame(log_rows)[POS_LOG_COLUMNS]

        new_log_rows.to_csv(
            POS_LOG_FILE,
            mode="a",
            header=False,
            index=False
        )

        pos_log = pd.concat(
            [pos_log, new_log_rows],
            ignore_index=True
        )

        # ---------------------------------------------
        # Persist to disk (raw schema only — no derived
        # Scale / Equivalent_Sales columns)
        # ---------------------------------------------

        updated_inventory.to_csv(
            INVENTORY_FILE,
            index=False
        )

        persisted_new_rows = new_sales_rows.copy()
        persisted_new_rows["Date"] = persisted_new_rows["Date"].dt.strftime("%Y-%m-%d")
        persisted_new_rows.to_csv(
            SALES_FILE,
            mode="a",
            header=False,
            index=False
        )

        # ---------------------------------------------
        # Recompute derived state
        # ---------------------------------------------

        new_sales_rows["Scale"] = (
            new_sales_rows["Size"].map(SIZE_MULTIPLIER).fillna(1.0)
        )
        new_sales_rows["Equivalent_Sales"] = (
            new_sales_rows["Quantity_Sold"] * new_sales_rows["Scale"]
        )

        inventory = updated_inventory
        sales = pd.concat(
            [sales, new_sales_rows],
            ignore_index=True
        )

        inventory_status = build_inventory_status()

        waste_analysis = calculate_waste(
            inventory_status,
            forecast
        )

        touched = [c["ingredient"] for c in consumed]

        updated_rows = inventory_status[
            inventory_status["Ingredient"].isin(touched)
        ].to_dict(orient="records")

    return {

        "ok": True,

        "order": order,

        "consumed": consumed,

        "shortfalls": shortfalls,

        "inventory": updated_rows
    }


# =========================================================
# SALES LOG
# =========================================================

@app.get("/api/sales/log")
def get_sales_log(limit: int = 100):

    if pos_log.empty:

        return {
            "orders": [],
            "today_total": 0,
            "today_orders": 0
        }

    grouped = []

    for order_id, group in pos_log.groupby("OrderId", sort=False):

        timestamp = group["Timestamp"].iloc[0]

        items = [
            {
                "item": row["Item"],
                "size": row["Size"],
                "quantity": float(row["Quantity"]),
                "price": float(row["Unit_Price"]),
                "line_total": float(row["Line_Total"])
            }
            for _, row in group.iterrows()
        ]

        grouped.append({
            "order_id": order_id,
            "timestamp": timestamp,
            "items": items,
            "item_count": len(items),
            "total": round(float(group["Line_Total"].sum()), 2)
        })

    grouped.sort(key=lambda o: o["timestamp"], reverse=True)

    today_str = date.today().isoformat()

    today_orders = [
        o for o in grouped
        if o["timestamp"].startswith(today_str)
    ]

    return {

        "orders": grouped[:limit],

        "today_total": round(
            sum(o["total"] for o in today_orders), 2
        ),

        "today_orders": len(today_orders)
    }


# =========================================================
# SETTINGS
# =========================================================

class SettingsUpdate(BaseModel):
    restaurant_name: str | None = None
    lead_time_days: float | None = None
    safety_stock_days: float | None = None
    critical_days: float | None = None
    low_days: float | None = None
    normal_days: float | None = None
    refresh_interval_seconds: int | None = None


@app.get("/api/settings")
def get_settings():

    return settings


@app.put("/api/settings")
def update_settings(update: SettingsUpdate):

    global settings, inventory_status, waste_analysis

    updates = {
        k: v for k, v in update.model_dump().items()
        if v is not None
    }

    merged = {**settings, **updates}

    if not (
        merged["critical_days"]
        < merged["low_days"]
        < merged["normal_days"]
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Thresholds must increase: "
                "critical_days < low_days < normal_days"
            )
        )

    settings = merged

    save_settings(SETTINGS_FILE, settings)

    inventory_status = build_inventory_status()

    waste_analysis = calculate_waste(
        inventory_status,
        forecast
    )

    return settings