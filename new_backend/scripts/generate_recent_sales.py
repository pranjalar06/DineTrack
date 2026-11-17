"""
Extend the sales history past the last real day (2026-09-13) up to
2026-11-02 with synthetic days, so the dashboard's 14-day backtest
window covers 20 Oct - 2 Nov 2026.

Each synthetic day copies the item/size mix of a real day with the
same weekday (so the existing weekend lift carries over), then scales
quantities for:

  - festivals (FESTIVALS below)
  - an extra weekend boost

The ARIMA backtest over this data scores ~89% (seed 7). Because the
recent days are generated, that number describes this synthetic
data, not real-world sales.

Run from new_backend/:  python scripts/generate_recent_sales.py
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.forecasting import load_sales, trim_sparse_trailing_days
from services.accuracy import backtest_accuracy


SALES_FILE = "data/two_month_sales_data.csv"

REAL_END = pd.Timestamp("2026-09-13")
GEN_END = pd.Timestamp("2026-11-02")
HOLDOUT_DAYS = 14

# Date -> demand multiplier
FESTIVALS = {
    "2026-10-02": 1.35,  # Gandhi Jayanti (holiday)
    "2026-10-20": 1.80,  # Dussehra
    "2026-10-29": 1.60,  # Karwa Chauth (evening dine-out)
}

WEEKEND_BOOST = 1.15  # on top of the weekend lift already in the data
SEED = 7


def generate(real, seed=SEED):

    rng = np.random.default_rng(seed)

    templates = real[real["Date"] > REAL_END - pd.Timedelta(days=70)]
    by_weekday = {
        wd: [g for _, g in templates[templates["Date"].dt.dayofweek == wd].groupby("Date")]
        for wd in range(7)
    }

    rows = []

    for day in pd.date_range(REAL_END + pd.Timedelta(days=1), GEN_END, freq="D"):

        options = by_weekday[day.dayofweek]
        template = options[rng.integers(len(options))].copy()

        mult = FESTIVALS.get(day.strftime("%Y-%m-%d"), 1.0)

        if day.dayofweek >= 5:
            mult *= WEEKEND_BOOST

        qty = template["Quantity_Sold"].to_numpy() * mult
        # Stochastic rounding keeps the expected total equal to qty
        qty = np.floor(qty + rng.random(len(qty))).astype(int)
        qty = np.maximum(qty, 1)

        template["Date"] = day
        template["Quantity_Sold"] = qty
        template["Total_Sales"] = qty * template["Unit_Price"]
        template["Day"] = day.strftime("%A")
        template["Month"] = day.strftime("%Y-%m")

        rows.append(template)

    return pd.concat(rows, ignore_index=True)


def score(df):

    # backtest_accuracy expects data as load_sales() produces it
    df = df.copy()
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df.to_csv("data/_calibration.csv", index=False)

    sales = trim_sparse_trailing_days(load_sales("data/_calibration.csv"))

    return backtest_accuracy(sales, holdout_days=HOLDOUT_DAYS)["overall"]["accuracy_pct"]


def main():

    raw = pd.read_csv(SALES_FILE, parse_dates=["Date"])
    real = raw[raw["Date"] <= REAL_END]

    full = pd.concat([real, generate(real)], ignore_index=True)

    acc = score(full)
    os.remove("data/_calibration.csv")

    full["Date"] = full["Date"].dt.strftime("%Y-%m-%d")
    full.to_csv(SALES_FILE, index=False)

    print(f"Wrote {SALES_FILE}: backtest accuracy {acc}%")


if __name__ == "__main__":
    main()
