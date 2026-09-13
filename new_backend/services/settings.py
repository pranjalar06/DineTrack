import json
import os

DEFAULT_SETTINGS = {
    "restaurant_name": "AJ Fast Food",
    "lead_time_days": 2,
    "safety_stock_days": 2,
    "critical_days": 2,
    "low_days": 4,
    "normal_days": 7,
    "refresh_interval_seconds": 0
}


def load_settings(path):

    if os.path.exists(path):

        with open(path, "r") as f:
            saved = json.load(f)

    else:

        saved = {}

    settings = {**DEFAULT_SETTINGS, **saved}

    save_settings(path, settings)

    return settings


def save_settings(path, settings):

    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
