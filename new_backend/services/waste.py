import pandas as pd
import numpy as np


# ---------------------------------------------------------
# WASTE REDUCTION SUGGESTIONS
# ---------------------------------------------------------

def generate_suggestion(
    ingredient
):

    name = ingredient.lower()

    if "potato" in name:

        return (
            "Increase promotion of fries/chilli potato, "
            "or use excess potatoes in combo meals."
        )

    if "paneer" in name:

        return (
            "Promote paneer-based items such as "
            "paneer noodles, paneer fried rice or pizza."
        )

    if "cheese" in name:

        return (
            "Offer cheese add-ons or cheese-heavy "
            "combo meals to consume excess stock."
        )

    if "capsicum" in name:

        return (
            "Use in noodles, fried rice, pizza and "
            "chilli potato as an additional topping."
        )

    if "onion" in name:

        return (
            "Increase onion-based noodles, pizza and "
            "fried rice combinations."
        )

    if "tomato" in name:

        return (
            "Use excess tomatoes in red sauce pasta "
            "or gravy preparations."
        )

    if "cabbage" in name:

        return (
            "Increase preparation of chowmein, "
            "spring rolls and momos."
        )

    if "mushroom" in name:

        return (
            "Promote mushroom cheese pizza as a "
            "limited-time special."
        )

    if "milk" in name or "cream" in name:

        return (
            "Prioritize white sauce pasta and "
            "other creamy preparations."
        )

    if "pizza" in name:

        return (
            "Promote pizza combinations or "
            "limited-time offers."
        )

    if "noodle" in name:

        return (
            "Use excess noodles in chowmein, "
            "garlic noodles and paneer noodles."
        )

    if "rice" in name:

        return (
            "Increase fried rice or rice + Manchurian "
            "combo sales."
        )

    return (
        "Reduce next purchase quantity and prioritize "
        "this ingredient in upcoming menu preparation."
    )


# ---------------------------------------------------------
# PREDICTED WASTE
# ---------------------------------------------------------

def calculate_waste(
    inventory,
    forecast_demand
):

    result = inventory.copy()

    # -----------------------------------------------------
    # Expected usage during next 7 days
    # -----------------------------------------------------

    result["Expected_7_Day_Usage"] = (
        result["Forecast_7_Day_Demand"]
    )

    # -----------------------------------------------------
    # Excess stock after predicted demand
    # -----------------------------------------------------

    result["Expected_Excess"] = np.maximum(

        0,

        result["Current_Inventory"]
        -
        result["Expected_7_Day_Usage"]
    )

    # -----------------------------------------------------
    # Determine whether excess is dangerous
    # -----------------------------------------------------

    result["Waste_Risk"] = "LOW"

    result.loc[
        (
            result["Expected_Excess"] > 0
        )
        &
        (
            result["Category"]
            == "Perishable"
        ),
        "Waste_Risk"
    ] = "MEDIUM"

    result.loc[
        (
            result["Expected_Excess"]
            >
            result["Expected_7_Day_Usage"]
        )
        &
        (
            result["Category"]
            == "Perishable"
        ),
        "Waste_Risk"
    ] = "HIGH"

    # -----------------------------------------------------
    # Suggestions
    # -----------------------------------------------------

    result["Waste_Reduction_Suggestion"] = (
        result["Ingredient"]
        .apply(generate_suggestion)
    )

    return result