import pandas as pd

from services.forecasting import SIZE_MULTIPLIER


# ---------------------------------------------------------
# MENU
# ---------------------------------------------------------

SIZE_ORDER = {"Half": 0, "Medium": 1, "Large": 2}


def build_menu(sales):

    priced = (
        sales[["Item", "Size", "Unit_Price"]]
        .drop_duplicates()
    )

    menu = []

    for item, group in priced.groupby("Item"):

        sizes = [
            {
                "size": row.Size,
                "price": float(row.Unit_Price)
            }
            for row in group.itertuples()
        ]

        sizes.sort(
            key=lambda s: SIZE_ORDER.get(s["size"], 99)
        )

        menu.append({
            "item": item,
            "sizes": sizes
        })

    menu.sort(key=lambda m: m["item"])

    return menu


# ---------------------------------------------------------
# CART -> INGREDIENT CONSUMPTION
# ---------------------------------------------------------

def compute_consumption(cart, recipes):

    lines = []

    for line in cart:

        item = line.get("item")
        size = line.get("size")
        quantity = float(line.get("quantity", 0))

        if quantity <= 0:
            continue

        item_recipe = recipes[recipes["item"] == item]

        if item_recipe.empty:
            raise ValueError(f"Unknown menu item: {item}")

        scale = SIZE_MULTIPLIER.get(size)

        if scale is None:
            raise ValueError(f"Unknown size '{size}' for item: {item}")

        equivalent = quantity * scale

        for _, recipe in item_recipe.iterrows():

            required = equivalent * float(recipe["grams_per_serving"])

            lines.append({
                "ingredient": recipe["ingredient"],
                "unit": recipe["Unit"],
                "required": required
            })

    if not lines:
        return pd.DataFrame(
            columns=["ingredient", "unit", "required"]
        )

    consumption = (
        pd.DataFrame(lines)
        .groupby(["ingredient", "unit"], as_index=False)["required"]
        .sum()
    )

    return consumption
