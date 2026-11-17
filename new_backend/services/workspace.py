import io
import os
import shutil
import threading
import uuid
from datetime import date, datetime

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
    DEFAULT_SETTINGS,
    load_settings,
    save_settings
)


# =========================================================
# FILE LAYOUT (same inside every workspace directory)
# =========================================================

SALES_FILE = "two_month_sales_data.csv"
INVENTORY_FILE = "current_kitchen_inventory.csv"
RECIPES_FILE = "menu_ingredient_level.csv"
POS_LOG_FILE = "pos_sales_log.csv"
SETTINGS_FILE = "settings.json"

RAW_SALES_COLUMNS = [
    "Date", "Item", "Size", "Quantity_Sold",
    "Unit_Price", "Total_Sales", "Day", "Month"
]

INVENTORY_COLUMNS = [
    "Ingredient", "Unit", "Average_Daily_Usage", "Target_Stock_Days",
    "Current_Inventory", "Estimated_Days_of_Stock", "Category"
]

RECIPE_COLUMNS = [
    "item", "ingredient", "grams_per_serving", "Unit",
    "ShelfLifeDays", "Storage"
]

POS_LOG_COLUMNS = [
    "OrderId", "Timestamp", "Item", "Size",
    "Quantity", "Unit_Price", "Line_Total"
]

FORECAST_COLUMNS = ["date", "item", "forecast_quantity"]

HOLDOUT_DAYS = 14


# =========================================================
# UPLOADS
# =========================================================
#
# What each uploadable dataset must contain. Optional columns are
# filled with defaults so a restaurant can start with the minimum.

UPLOADS = {

    "menu": {
        "file": RECIPES_FILE,
        "label": "Menu & recipes",
        "required": ["item", "ingredient", "grams_per_serving", "Unit"],
        "columns": RECIPE_COLUMNS,
        "template": [
            ["Veg Chowmein", "Noodles", 100, "g", 180, "Airtight, dry"],
            ["Veg Chowmein", "Cabbage", 30, "g", 7, "Refrigerated"],
            ["French Fries", "Potato", 150, "g", 14, "Cool, dry"]
        ]
    },

    "inventory": {
        "file": INVENTORY_FILE,
        "label": "Kitchen inventory",
        "required": ["Ingredient", "Unit", "Current_Inventory"],
        "columns": INVENTORY_COLUMNS,
        "template": [
            ["Noodles", "g", 3000, 10, 30000, 10, "Dry/Long-life"],
            ["Cabbage", "g", 1500, 7, 9000, 6, "Perishable"],
            ["Potato", "g", 4000, 7, 25000, 6, "Perishable"]
        ]
    },

    "sales": {
        "file": SALES_FILE,
        "label": "Sales history",
        "required": ["Date", "Item", "Size", "Quantity_Sold", "Unit_Price"],
        "columns": RAW_SALES_COLUMNS,
        "template": [
            ["2026-10-01", "Veg Chowmein", "Half", 6, 40, 240, "Thursday", "2026-10"],
            ["2026-10-01", "Veg Chowmein", "Large", 2, 80, 160, "Thursday", "2026-10"],
            ["2026-10-01", "French Fries", "Medium", 5, 60, 300, "Thursday", "2026-10"]
        ]
    }
}


def template_csv(kind):

    spec = UPLOADS[kind]

    return pd.DataFrame(
        spec["template"],
        columns=spec["columns"]
    ).to_csv(index=False)


def read_upload(filename, content):

    name = (filename or "").lower()

    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content))

    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content))

    raise ValueError("Upload a .csv or .xlsx file")


def _match_columns(df, columns, required):

    # Match column names case- and whitespace-insensitively so
    # "quantity sold" or "Quantity_Sold " are both accepted.
    lookup = {
        str(c).strip().lower().replace(" ", "_"): c
        for c in df.columns
    }

    renames = {
        lookup[col.lower()]: col
        for col in columns
        if col.lower() in lookup
    }

    missing = [col for col in required if col not in renames.values()]

    if missing:
        raise ValueError("Missing column(s): " + ", ".join(missing))

    return df.rename(columns=renames)


def normalise_upload(kind, df):

    spec = UPLOADS[kind]

    df = _match_columns(df, spec["columns"], spec["required"])

    df = df.dropna(subset=spec["required"]).copy()

    if df.empty:
        raise ValueError("The file has no data rows")

    if kind == "menu":

        df["grams_per_serving"] = pd.to_numeric(df["grams_per_serving"], errors="raise")
        df["ShelfLifeDays"] = df.get("ShelfLifeDays", 7)
        df["Storage"] = df.get("Storage", "")

    elif kind == "inventory":

        df["Current_Inventory"] = pd.to_numeric(df["Current_Inventory"], errors="raise")
        df["Average_Daily_Usage"] = pd.to_numeric(df.get("Average_Daily_Usage", 0), errors="coerce")
        df["Target_Stock_Days"] = df.get("Target_Stock_Days", 7)
        df["Category"] = df.get("Category", "Perishable")
        df["Average_Daily_Usage"] = df["Average_Daily_Usage"].fillna(0)

        usage = df["Average_Daily_Usage"].where(df["Average_Daily_Usage"] > 0)
        df["Estimated_Days_of_Stock"] = (
            df["Current_Inventory"] / usage
        ).round(1).fillna(0)

    elif kind == "sales":

        df["Date"] = pd.to_datetime(df["Date"], errors="raise")
        df["Quantity_Sold"] = pd.to_numeric(df["Quantity_Sold"], errors="raise")
        df["Unit_Price"] = pd.to_numeric(df["Unit_Price"], errors="raise")
        df["Total_Sales"] = df["Quantity_Sold"] * df["Unit_Price"]
        df["Day"] = df["Date"].dt.strftime("%A")
        df["Month"] = df["Date"].dt.strftime("%Y-%m")
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        unknown = sorted(set(df["Size"]) - set(SIZE_MULTIPLIER))

        if unknown:
            raise ValueError(
                "Unknown size(s): " + ", ".join(map(str, unknown))
                + ". Use " + ", ".join(SIZE_MULTIPLIER)
            )

    return df[spec["columns"]]


# =========================================================
# WORKSPACE
# =========================================================

class Workspace:
    """One restaurant's data files plus everything derived from them
    (forecast, inventory status, waste, backtest, POS menu)."""

    def __init__(self, data_dir, restaurant_name=None):

        self.dir = data_dir
        self.lock = threading.Lock()

        os.makedirs(self.dir, exist_ok=True)

        settings_path = self.path(SETTINGS_FILE)

        if restaurant_name and not os.path.exists(settings_path):
            save_settings(settings_path, {
                **DEFAULT_SETTINGS,
                "restaurant_name": restaurant_name
            })

        self.settings = load_settings(settings_path)

        self.sales = self._read_sales()
        self.inventory = self._read(INVENTORY_FILE, INVENTORY_COLUMNS)
        self.recipes = self._read(RECIPES_FILE, RECIPE_COLUMNS)

        if os.path.exists(self.path(POS_LOG_FILE)):
            self.pos_log = pd.read_csv(self.path(POS_LOG_FILE))
        else:
            self.pos_log = pd.DataFrame(columns=POS_LOG_COLUMNS)
            self.pos_log.to_csv(self.path(POS_LOG_FILE), index=False)

        self.recompute()

    # -----------------------------------------------------
    # Loading
    # -----------------------------------------------------

    def path(self, name):

        return os.path.join(self.dir, name)

    def _read(self, name, columns):

        if os.path.exists(self.path(name)):
            return pd.read_csv(self.path(name))

        return pd.DataFrame(columns=columns)

    def _read_sales(self):

        if os.path.exists(self.path(SALES_FILE)):
            return load_sales(self.path(SALES_FILE))

        empty = pd.DataFrame(columns=RAW_SALES_COLUMNS + ["Scale", "Equivalent_Sales"])
        empty["Date"] = pd.to_datetime(empty["Date"])

        return empty

    def has(self, kind):

        return {
            "menu": not self.recipes.empty,
            "inventory": not self.inventory.empty,
            "sales": not self.sales.empty
        }[kind]

    def data_status(self):

        return {kind: self.has(kind) for kind in UPLOADS}

    # -----------------------------------------------------
    # Derived state
    # -----------------------------------------------------

    def recompute(self):

        # Forecasting/backtesting run only over clean, fully-logged
        # trading days — see trim_sparse_trailing_days(). `sales`
        # itself stays the full history (including any live
        # POS-appended rows) for everything else.
        if self.sales.empty:

            self.forecast = pd.DataFrame(columns=FORECAST_COLUMNS)
            self.model_accuracy = backtest_accuracy(self.sales, holdout_days=HOLDOUT_DAYS)

        else:

            history = trim_sparse_trailing_days(self.sales)

            self.forecast = forecast_all_items(history, days=7)

            self.model_accuracy = backtest_accuracy(
                history,
                holdout_days=HOLDOUT_DAYS
            )

        self.menu = build_menu(
            self.sales[self.sales["Item"].isin(self.recipes["item"])]
        )

        # Ingredient -> menu items that use it, for surfacing "push
        # these dishes" suggestions on the waste control page.
        self.ingredient_dishes = (
            self.recipes
            .groupby("ingredient")["item"]
            .apply(lambda s: sorted(set(s)))
            .to_dict()
        )

        self.refresh_inventory()

    def refresh_inventory(self):

        s = self.settings

        if self.inventory.empty:

            self.inventory_status = pd.DataFrame(columns=INVENTORY_COLUMNS + [
                "Forecast_7_Day_Demand", "Days_of_Stock", "Status", "Suggested_Order"
            ])
            self.waste_analysis = self.inventory_status.reindex(columns=[
                *self.inventory_status.columns, "Expected_7_Day_Usage",
                "Expected_Excess", "Waste_Risk", "Waste_Reduction_Suggestion",
                "Disposal_Route", "Disposal_Note"
            ])
            return

        self.inventory_status = calculate_inventory_status(
            self.inventory,
            self.forecast,
            self.recipes,
            lead_time_days=s["lead_time_days"],
            safety_stock_days=s["safety_stock_days"],
            critical_days=s["critical_days"],
            low_days=s["low_days"],
            normal_days=s["normal_days"]
        )

        self.waste_analysis = calculate_waste(
            self.inventory_status,
            self.forecast
        )

    # -----------------------------------------------------
    # Views
    # -----------------------------------------------------

    def _order_rows(self):

        status = self.inventory_status

        return status[
            status["Status"].isin(["CRITICAL", "LOW"])
            | (status["Suggested_Order"] > 0)
        ]

    def _waste_rows(self):

        return self.waste_analysis[
            self.waste_analysis["Waste_Risk"] != "LOW"
        ]

    def dashboard(self):

        status = self.inventory_status

        critical = status[status["Status"] == "CRITICAL"]
        low = status[status["Status"] == "LOW"]
        orders = self._order_rows()
        waste = self._waste_rows()

        if self.sales.empty:
            period = {"start": "", "end": ""}
        else:
            period = {
                "start": self.sales["Date"].min().strftime("%Y-%m-%d"),
                "end": self.sales["Date"].max().strftime("%Y-%m-%d")
            }

        return {

            "sales_period": period,

            "data_status": self.data_status(),

            "forecast": {
                "days": 7,
                "total_expected_units": round(
                    float(self.forecast["forecast_quantity"].sum()), 2
                )
            },

            "inventory": {
                "total_ingredients": len(status),
                "critical": len(critical),
                "low": len(low),
                "orders_required": len(orders),
                "waste_risk_items": len(waste)
            },

            "model_accuracy": self.model_accuracy["overall"],

            "critical_items": critical[
                ["Ingredient", "Current_Inventory", "Days_of_Stock"]
            ].to_dict(orient="records"),

            "orders": orders[
                ["Ingredient", "Unit", "Suggested_Order"]
            ].to_dict(orient="records"),

            "waste": waste[
                ["Ingredient", "Expected_Excess", "Waste_Risk"]
            ].to_dict(orient="records")
        }

    def forecast_view(self):

        return {
            "forecast_days": 7,
            "last_historical_date": (
                None if self.sales.empty
                else self.sales["Date"].max().strftime("%Y-%m-%d")
            ),
            "forecast": self.forecast.to_dict(orient="records")
        }

    def item_forecast(self, item_name):

        return self.forecast[
            self.forecast["item"].str.lower() == item_name.lower()
        ]

    def inventory_view(self):

        # waste_analysis is inventory_status plus the waste-risk columns
        # (Waste_Risk, Expected_Excess, Waste_Reduction_Suggestion), so
        # returning it gives the Inventory tab reorder status and waste
        # flags in one call.
        return {"inventory": self.waste_analysis.to_dict(orient="records")}

    def inventory_with_status(self, statuses):

        rows = self.inventory_status[
            self.inventory_status["Status"].isin(statuses)
        ]

        return {"count": len(rows), "items": rows.to_dict(orient="records")}

    def orders_view(self):

        return {
            "orders": self._order_rows()[
                [
                    "Ingredient",
                    "Unit",
                    "Current_Inventory",
                    "Forecast_7_Day_Demand",
                    "Days_of_Stock",
                    "Status",
                    "Suggested_Order"
                ]
            ].to_dict(orient="records")
        }

    def waste_view(self):

        waste = self._waste_rows().copy()

        waste["Used_In"] = waste["Ingredient"].map(
            lambda name: self.ingredient_dishes.get(name, [])
        )

        return {
            "count": len(waste),
            "waste_risk": waste[
                [
                    "Ingredient",
                    "Unit",
                    "Current_Inventory",
                    "Expected_7_Day_Usage",
                    "Expected_Excess",
                    "Waste_Risk",
                    "Waste_Reduction_Suggestion",
                    "Disposal_Route",
                    "Disposal_Note",
                    "Used_In"
                ]
            ].to_dict(orient="records")
        }

    def sales_log(self, limit=100):

        if self.pos_log.empty:
            return {"orders": [], "today_total": 0, "today_orders": 0}

        grouped = []

        for order_id, group in self.pos_log.groupby("OrderId", sort=False):

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
                "timestamp": group["Timestamp"].iloc[0],
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
            "today_total": round(sum(o["total"] for o in today_orders), 2),
            "today_orders": len(today_orders)
        }

    # -----------------------------------------------------
    # Mutations
    # -----------------------------------------------------

    def update_settings(self, updates):

        merged = {**self.settings, **updates}

        if not (
            merged["critical_days"]
            < merged["low_days"]
            < merged["normal_days"]
        ):
            raise ValueError(
                "Thresholds must increase: "
                "critical_days < low_days < normal_days"
            )

        with self.lock:

            self.settings = merged
            save_settings(self.path(SETTINGS_FILE), merged)
            self.refresh_inventory()

        return merged

    def upload(self, kind, df, mode="replace"):

        spec = UPLOADS[kind]
        target = self.path(spec["file"])

        with self.lock:

            if mode == "append" and kind == "sales" and os.path.exists(target):
                existing = pd.read_csv(target)
                df = pd.concat([existing, df], ignore_index=True)

            # Keep the previous version next to the new one
            if os.path.exists(target):
                shutil.copyfile(target, target + ".upload-backup")

            df.to_csv(target, index=False)

            if kind == "sales":
                self.sales = load_sales(target)
            elif kind == "inventory":
                self.inventory = pd.read_csv(target)
            else:
                self.recipes = pd.read_csv(target)

            self.recompute()

        return {"rows": len(df), "data_status": self.data_status()}

    def record_sale(self, cart):

        if self.recipes.empty or not self.menu:
            raise ValueError(
                "Your menu is empty. Upload your menu and sales history "
                "on the Data page before ringing up sales."
            )

        consumption = compute_consumption(cart, self.recipes)

        menu_lookup = {
            (m["item"], s["size"]): s["price"]
            for m in self.menu
            for s in m["sizes"]
        }

        for line in cart:
            if (line["item"], line["size"]) not in menu_lookup:
                raise ValueError(
                    f"{line['item']} ({line['size']}) is not on the menu"
                )

        with self.lock:

            # ---------------------------------------------
            # Deduct consumption from inventory
            # ---------------------------------------------

            updated_inventory = self.inventory.copy()
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
                self.path(POS_LOG_FILE),
                mode="a",
                header=False,
                index=False
            )

            self.pos_log = pd.concat(
                [self.pos_log, new_log_rows],
                ignore_index=True
            )

            # ---------------------------------------------
            # Persist to disk (raw schema only — no derived
            # Scale / Equivalent_Sales columns)
            # ---------------------------------------------

            updated_inventory.to_csv(
                self.path(INVENTORY_FILE),
                index=False
            )

            persisted_new_rows = new_sales_rows.copy()
            persisted_new_rows["Date"] = persisted_new_rows["Date"].dt.strftime("%Y-%m-%d")
            persisted_new_rows.to_csv(
                self.path(SALES_FILE),
                mode="a",
                header=not os.path.exists(self.path(SALES_FILE)),
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

            self.inventory = updated_inventory
            self.sales = pd.concat(
                [self.sales, new_sales_rows],
                ignore_index=True
            )

            self.refresh_inventory()

            touched = [c["ingredient"] for c in consumed]

            updated_rows = self.inventory_status[
                self.inventory_status["Ingredient"].isin(touched)
            ].to_dict(orient="records")

        return {
            "ok": True,
            "order": order,
            "consumed": consumed,
            "shortfalls": shortfalls,
            "inventory": updated_rows
        }
