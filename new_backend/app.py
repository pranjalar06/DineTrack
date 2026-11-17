import hashlib
import os
import threading

from fastapi import Depends, FastAPI, File, Header, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.auth import (
    UserStore,
    public_user,
    DEMO_WORKSPACE
)

from services.workspace import (
    UPLOADS,
    Workspace,
    normalise_upload,
    read_upload,
    template_csv
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

# AJ Fast Food's data lives directly in data/; every other account
# gets its own directory under data/workspaces/ with the same files.
DEMO_DATA_DIR = "data"

WORKSPACES_DIR = (
    "data/workspaces"
)

USERS_FILE = (
    "data/users.json"
)

AUTH_SECRET_FILE = (
    "data/.auth_secret"
)


# =========================================================
# WORKSPACES
# =========================================================

users = UserStore(USERS_FILE, AUTH_SECRET_FILE)

workspaces = {
    DEMO_WORKSPACE: Workspace(DEMO_DATA_DIR)
}

workspaces_lock = threading.Lock()


def workspace_for(user):

    if user["workspace"] == DEMO_WORKSPACE:
        return workspaces[DEMO_WORKSPACE]

    key = hashlib.sha256(user["email"].encode()).hexdigest()[:16]

    with workspaces_lock:

        if key not in workspaces:
            workspaces[key] = Workspace(
                os.path.join(WORKSPACES_DIR, key),
                restaurant_name=user["restaurant_name"]
            )

        return workspaces[key]


# =========================================================
# AUTH
# =========================================================

def current_user(authorization: str | None = Header(default=None)):

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not signed in")

    user = users.user_for_token(authorization.removeprefix("Bearer "))

    if user is None:
        raise HTTPException(status_code=401, detail="Session expired, please sign in again")

    return user


def current_workspace(user: dict = Depends(current_user)):

    return workspace_for(user)


class SignupRequest(BaseModel):
    name: str
    restaurant_name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/signup")
def signup(request: SignupRequest):

    if not request.name.strip() or not request.restaurant_name.strip():
        raise HTTPException(status_code=400, detail="Name and restaurant name are required")

    if "@" not in request.email or "." not in request.email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address")

    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    try:
        user = users.create(
            request.name,
            request.restaurant_name,
            request.email,
            request.password
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "token": users.issue_token(user),
        "user": public_user(user)
    }


@app.post("/api/auth/login")
def login(request: LoginRequest):

    user = users.authenticate(request.email, request.password)

    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    return {
        "token": users.issue_token(user),
        "user": public_user(user)
    }


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):

    return public_user(user)


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
def get_forecast(ws: Workspace = Depends(current_workspace)):

    return ws.forecast_view()


# =========================================================
# ITEM FORECAST
# =========================================================

@app.get("/api/forecast/{item_name}")
def get_item_forecast(
    item_name: str,
    ws: Workspace = Depends(current_workspace)
):

    result = ws.item_forecast(item_name)

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
def get_inventory(ws: Workspace = Depends(current_workspace)):

    return ws.inventory_view()


@app.get("/api/inventory/critical")
def get_critical_inventory(ws: Workspace = Depends(current_workspace)):

    return ws.inventory_with_status(["CRITICAL"])


@app.get("/api/inventory/low")
def get_low_inventory(ws: Workspace = Depends(current_workspace)):

    return ws.inventory_with_status(["CRITICAL", "LOW"])


# =========================================================
# ORDER RECOMMENDATIONS
# =========================================================

@app.get("/api/orders")
def get_order_recommendations(ws: Workspace = Depends(current_workspace)):

    return ws.orders_view()


# =========================================================
# WASTE
# =========================================================

@app.get("/api/waste")
def get_waste(ws: Workspace = Depends(current_workspace)):

    return ws.waste_view()


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/api/dashboard")
def get_dashboard(ws: Workspace = Depends(current_workspace)):

    return ws.dashboard()


# =========================================================
# MODEL ACCURACY
# =========================================================

@app.get("/api/accuracy")
def get_accuracy(ws: Workspace = Depends(current_workspace)):

    return ws.model_accuracy


# =========================================================
# POS MENU
# =========================================================

@app.get("/api/menu")
def get_menu(ws: Workspace = Depends(current_workspace)):

    return {
        "menu": ws.menu
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
    request: SaleRequest,
    ws: Workspace = Depends(current_workspace)
):

    cart = [line.model_dump() for line in request.cart]

    if not cart:
        raise HTTPException(
            status_code=400,
            detail="Cart is empty"
        )

    try:
        return ws.record_sale(cart)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )


# =========================================================
# SALES LOG
# =========================================================

@app.get("/api/sales/log")
def get_sales_log(limit: int = 100, ws: Workspace = Depends(current_workspace)):

    return ws.sales_log(limit)


# =========================================================
# DATA UPLOADS
# =========================================================

@app.get("/api/data/status")
def get_data_status(ws: Workspace = Depends(current_workspace)):

    return {
        kind: {
            "label": spec["label"],
            "uploaded": ws.has(kind),
            "required_columns": spec["required"],
            "columns": spec["columns"]
        }
        for kind, spec in UPLOADS.items()
    }


@app.get("/api/data/template/{kind}")
def get_template(kind: str):

    if kind not in UPLOADS:
        raise HTTPException(status_code=404, detail="Unknown dataset")

    return Response(
        content=template_csv(kind),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{kind}_template.csv"'}
    )


@app.post("/api/data/upload/{kind}")
async def upload_data(
    kind: str,
    mode: str = "replace",
    file: UploadFile = File(...),
    ws: Workspace = Depends(current_workspace)
):

    if kind not in UPLOADS:
        raise HTTPException(status_code=404, detail="Unknown dataset")

    if mode not in ("replace", "append"):
        raise HTTPException(status_code=400, detail="mode must be replace or append")

    try:
        df = normalise_upload(kind, read_upload(file.filename, await file.read()))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read {file.filename}: {exc}")

    # Re-fitting the forecast takes a few seconds; keep it off the event loop
    return await run_in_threadpool(ws.upload, kind, df, mode)


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
def get_settings(ws: Workspace = Depends(current_workspace)):

    return ws.settings


@app.put("/api/settings")
def update_settings(update: SettingsUpdate, ws: Workspace = Depends(current_workspace)):

    updates = {
        k: v for k, v in update.model_dump().items()
        if v is not None
    }

    try:
        return ws.update_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
