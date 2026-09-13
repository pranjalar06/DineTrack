import pandas as pd
import numpy as np

from statsmodels.tsa.arima.model import ARIMA

# SIZE MULTIPLIERS
# The ingredient dataset represents the base/half serving.
# We convert all historical sales into equivalent base servings.

SIZE_MULTIPLIER = {
    "Half": 1.0,
    "Medium": 1.35,
    "Large": 1.75
}


# ---------------------------------------------------------
# LOAD SALES
# ---------------------------------------------------------

def load_sales(path="data/two_month_sales_data.csv"):

    df = pd.read_csv(path)

    df["Date"] = pd.to_datetime(df["Date"])

    df["Scale"] = (
        df["Size"]
        .map(SIZE_MULTIPLIER)
        .fillna(1.0)
    )

    # Convert different sizes to equivalent base servings
    df["Equivalent_Sales"] = (
        df["Quantity_Sold"] * df["Scale"]
    )

    return df


# ---------------------------------------------------------
# TRIM SPARSE TRAILING DAYS
# ---------------------------------------------------------
#
# Live POS sales get appended to the sales file with today's date,
# which can land days after the last full trading day in the bulk
# historical data. A handful of POS test rows then read as a near-
# empty trailing day, and prepare_daily_series() zero-fills the gap
# in between — which corrupts both the forecast and the accuracy
# backtest if that gap falls inside their lookback window. Trim any
# trailing days that don't look like a real, fully-logged trading day
# before feeding data into forecasting/backtesting.

def trim_sparse_trailing_days(df, min_rows_per_day=20):

    if df.empty:
        return df

    daily_counts = df.groupby("Date").size()

    good_dates = daily_counts[
        daily_counts >= min_rows_per_day
    ].index

    if len(good_dates) == 0:
        return df

    cutoff = good_dates.max()

    return df[df["Date"] <= cutoff].copy()


# PREPARE DAILY SERIES

def prepare_daily_series(sales, item):

    item_data = sales[
        sales["Item"] == item
    ]

    daily = (
        item_data
        .groupby("Date")["Equivalent_Sales"]
        .sum()
    )

    # Create complete daily index
    # Missing sales = zero sales
    full_index = pd.date_range(
        sales["Date"].min(),
        sales["Date"].max(),
        freq="D"
    )

    daily = (
        daily
        .reindex(full_index, fill_value=0)
    )

    daily.index.name = "Date"

    return daily


# ---------------------------------------------------------
# ARIMA FORECAST
# ---------------------------------------------------------

def arima_forecast(series, days=7):

    # Very small datasets can cause ARIMA instability.
    # Fallback to moving average in that situation.

    if len(series) < 15:

        avg = series.tail(7).mean()

        return np.repeat(avg, days)

    try:

        model = ARIMA(
            series,
            order=(2, 1, 2)
        )

        model_fit = model.fit()

        forecast = model_fit.forecast(
            steps=days
        )

        forecast = np.maximum(
            forecast,
            0
        )

        return forecast.values

    except Exception:

        # Safe fallback
        avg = series.tail(7).mean()

        return np.repeat(
            max(avg, 0),
            days
        )


# ---------------------------------------------------------
# FORECAST ALL ITEMS
# ---------------------------------------------------------

def forecast_all_items(
    sales,
    days=7
):

    items = sales["Item"].unique()

    results = []

    last_date = sales["Date"].max()

    future_dates = pd.date_range(
        last_date + pd.Timedelta(days=1),
        periods=days,
        freq="D"
    )

    for item in items:

        series = prepare_daily_series(
            sales,
            item
        )

        forecast = arima_forecast(
            series,
            days
        )

        for date, value in zip(
            future_dates,
            forecast
        ):

            results.append({

                "date":
                    date.strftime("%Y-%m-%d"),

                "item":
                    item,

                "forecast_quantity":
                    round(float(value), 2)

            })

    return pd.DataFrame(results)