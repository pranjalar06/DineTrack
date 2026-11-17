import pandas as pd
import numpy as np



def calculate_inventory_status(
    inventory,
    forecast,
    recipes,
    lead_time_days=2,
    safety_stock_days=2,
    critical_days=2,
    low_days=4,
    normal_days=7
):

    # -----------------------------------------------------
    # Calculate average daily ingredient usage
    # from historical inventory dataset
    # -----------------------------------------------------

    inventory = inventory.copy()

    inventory["Average_Daily_Usage"] = (
        inventory["Average_Daily_Usage"]
        .astype(float)
    )

    # -----------------------------------------------------
    # Calculate next 7 days ingredient demand
    # -----------------------------------------------------

    forecast_demand = []

    for _, forecast_row in forecast.iterrows():

        item = forecast_row["item"]

        quantity = (
            forecast_row["forecast_quantity"]
        )

        item_recipe = recipes[
            recipes["item"] == item
        ]

        for _, recipe in item_recipe.iterrows():

            ingredient = recipe["ingredient"]

            grams = float(
                recipe["grams_per_serving"]
            )

            unit = recipe["Unit"]

            required = (
                quantity * grams
            )

            forecast_demand.append({

                "ingredient":
                    ingredient,

                "unit":
                    unit,

                "required":
                    required

            })

    demand_df = pd.DataFrame(
        forecast_demand,
        columns=["ingredient", "unit", "required"]
    )

    # No forecast yet (e.g. no sales uploaded): every ingredient
    # simply gets zero forecast demand below.
    demand_df = (
        demand_df
        .groupby(
            ["ingredient", "unit"],
            as_index=False
        )["required"]
        .sum()
    )

    demand_df.rename(
        columns={
            "required":
                "Forecast_7_Day_Demand"
        },
        inplace=True
    )

    # -----------------------------------------------------
    # Merge inventory + forecast demand
    # -----------------------------------------------------

    result = inventory.merge(
        demand_df,
        left_on=["Ingredient", "Unit"],
        right_on=["ingredient", "unit"],
        how="left"
    )

    result["Forecast_7_Day_Demand"] = (
        result["Forecast_7_Day_Demand"]
        .fillna(0)
    )

    # -----------------------------------------------------
    # Average forecast consumption
    # -----------------------------------------------------

    result["Forecast_Daily_Demand"] = (
        result["Forecast_7_Day_Demand"] / 7
    )

    # -----------------------------------------------------
    # Days of stock remaining
    # -----------------------------------------------------

    result["Days_of_Stock"] = np.where(

        result["Forecast_Daily_Demand"] > 0,

        result["Current_Inventory"] /
        result["Forecast_Daily_Demand"],

        999
    )

    # -----------------------------------------------------
    # Required safety stock
    # -----------------------------------------------------

    result["Safety_Stock"] = (
        result["Forecast_Daily_Demand"]
        * safety_stock_days
    )

    # -----------------------------------------------------
    # Reorder point
    # -----------------------------------------------------

    result["Reorder_Point"] = (

        result["Forecast_Daily_Demand"]
        * lead_time_days

        +

        result["Safety_Stock"]
    )

    # -----------------------------------------------------
    # Suggested order quantity
    # -----------------------------------------------------

    result["Suggested_Order"] = np.maximum(

        0,

        result["Reorder_Point"]
        - result["Current_Inventory"]
    )

    # -----------------------------------------------------
    # Inventory status
    # -----------------------------------------------------

    def status(row):

        days = row["Days_of_Stock"]

        if days <= critical_days:
            return "CRITICAL"

        elif days <= low_days:
            return "LOW"

        elif days <= normal_days:
            return "NORMAL"

        else:
            return "OVERSTOCKED"

    result["Status"] = result.apply(
        status,
        axis=1
    )

    return result