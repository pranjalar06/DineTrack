import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Bell, BellRing,
  Boxes, CalendarDays, CheckCircle2, ChevronRight, CircleCheck, Command,
  CreditCard, Download, HandHeart, Sprout, Droplets, Flame, Gauge, LayoutDashboard, Leaf, Lock, LogOut,
  Mail, MoreHorizontal, Minus, Moon, Package, Plus, Receipt, RefreshCw, Save, Search,
  Settings as SettingsIcon, ShoppingCart, Store,
  Sparkles, Sun, Trash2, TrendingUp, Upload, User, UtensilsCrossed, X, Zap
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, CartesianGrid, Cell, LineChart, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis
} from "recharts";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// The AJ Fast Food account is backed by real data; every other account
// signs up into an empty workspace with the same pages.
const DEMO_WORKSPACE = "ajfastfood";

const TOKEN_KEY = "dinetrack-token";
function readToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
function writeToken(token) {
  try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch {}
}

let authToken = readToken();
let onUnauthorized = () => {};

async function apiFetch(path, options = {}) {
  const r = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      // FormData uploads set their own multipart Content-Type
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      ...options.headers
    }
  });
  if (r.status === 401) {
    onUnauthorized();
    throw new Error("Session expired");
  }
  return r;
}

const nav = [
  ["overview", "Overview", LayoutDashboard],
  ["pos", "Point of Sale", CreditCard],
  ["saleslog", "Sales Log", Receipt],
  ["inventory", "Inventory", Boxes],
  ["forecast", "Demand Forecast", TrendingUp],
  ["orders", "Purchase Orders", ShoppingCart],
  ["waste", "Waste Control", Leaf],
  ["data", "Data Upload", Upload],
];

const PRIMARY_TAB_IDS = ["overview", "pos", "orders", "inventory"];
const primaryTabs = nav.filter(([id]) => PRIMARY_TAB_IDS.includes(id));
const moreTabs = [
  ...nav.filter(([id]) => !PRIMARY_TAB_IDS.includes(id)),
  ["settings", "Settings", SettingsIcon]
];
const pageLabels = Object.fromEntries(
  [...nav, ["settings", "Settings", SettingsIcon]].map(([id, label]) => [id, label])
);
const MORE_PAGE_IDS = moreTabs.map(([id]) => id);

const defaultSettings = {
  restaurant_name: "AJ Fast Food",
  lead_time_days: 2,
  safety_stock_days: 2,
  critical_days: 2,
  low_days: 4,
  normal_days: 7,
  refresh_interval_seconds: 0
};

const fallback = {
  sales_period: { start: "", end: "" },
  forecast: { days: 7, total_expected_units: 0 },
  inventory: { total_ingredients: 0, critical: 0, low: 0, orders_required: 0, waste_risk_items: 0 },
  model_accuracy: { accuracy_pct: null, mape: null, rmse: null, holdout_days: 14 },
  critical_items: [], orders: [], waste: []
};

function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "DT";
  return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
}

const chartTooltipStyle = {
  background: "var(--surface-2)",
  border: "1px solid var(--line)",
  borderRadius: 10,
  fontSize: 11,
  color: "var(--ink)"
};
const chartGridColor = "var(--line)";
const chartTickColor = "var(--muted)";

function money(n) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Number(n || 0));
}
function num(n, digits = 1) {
  return Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: digits });
}
function formatQty(value, unit, digits = 1) {
  const n = Number(value || 0);
  const u = String(unit || "").trim();
  const lu = u.toLowerCase();
  if ((lu === "g" || lu === "ml") && Math.abs(n) >= 1000) {
    const converted = n / 1000;
    const convertedUnit = lu === "g" ? "kg" : "L";
    return `${converted.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${convertedUnit}`;
  }
  return `${num(n, digits)}${u ? " " + u : ""}`;
}
function shortDate(d) {
  if (!d) return "—";
  const x = new Date(d);
  return x.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

function StatusPill({ status }) {
  const cls = String(status || "").toLowerCase().replaceAll(" ", "-");
  return <span className={`pill ${cls}`}>{status}</span>;
}

function Empty({ text = "No records found" }) {
  return <div className="empty">{text}</div>;
}

function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(!!authToken);

  useEffect(() => {
    try { document.documentElement.setAttribute("data-theme", localStorage.getItem("dinetrack-theme") || "dark"); } catch {}
    onUnauthorized = logout;
    if (!authToken) return;
    apiFetch("/api/auth/me")
      .then(r => r.json())
      .then(setUser)
      .catch(() => {})
      .finally(() => setChecking(false));
  }, []);

  function handleAuth({ token, user }) {
    authToken = token;
    writeToken(token);
    setUser(user);
  }

  function logout() {
    authToken = null;
    writeToken(null);
    setUser(null);
  }

  if (checking) return <div className="auth-shell"><div className="auth-loading">Loading DineTrack…</div></div>;
  if (!user) return <AuthPage onAuth={handleAuth}/>;
  return <Dashboard key={user.email} user={user} onLogout={logout}/>;
}

function AuthPage({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", restaurant_name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isSignup = mode === "signup";

  function set(key, value) {
    setForm(prev => ({ ...prev, [key]: value }));
  }

  function switchMode(next) {
    setMode(next);
    setError("");
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = isSignup ? form : { email: form.email, password: form.password };
      const r = await fetch(`${API}/api/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await r.json();
      if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Please fill in every field");
      onAuth(data);
    } catch (e) {
      setError(e.message === "Failed to fetch" ? `Could not reach the DineTrack API at ${API}. Start FastAPI first.` : e.message);
    } finally {
      setBusy(false);
    }
  }

  return <div className="auth-shell">
    <div className="auth-panel">
      <div className="auth-intro">
        <div className="brand">
          <div className="brand-mark"><UtensilsCrossed size={21}/></div>
          <div><strong>DineTrack</strong><span>Inventory intelligence</span></div>
        </div>
        <h1>Forecast demand.<br/>Cut waste.<br/>Never run out.</h1>
        <p>ARIMA demand forecasting, live inventory and smart reorders for your restaurant kitchen.</p>
        <ul>
          <li><TrendingUp size={15}/> 7-day demand forecasts per menu item</li>
          <li><Boxes size={15}/> Stock coverage and reorder alerts</li>
          <li><Leaf size={15}/> Waste risk on perishables</li>
        </ul>
      </div>

      <form className="card auth-card" onSubmit={submit}>
        <div className="auth-tabs">
          <button type="button" className={!isSignup ? "active" : ""} onClick={() => switchMode("login")}>Sign in</button>
          <button type="button" className={isSignup ? "active" : ""} onClick={() => switchMode("signup")}>Create account</button>
        </div>

        <div>
          <h2>{isSignup ? "Set up your restaurant" : "Welcome back"}</h2>
          <p className="auth-sub">{isSignup ? "Start with an empty workspace and add your own data." : "Sign in to open your kitchen dashboard."}</p>
        </div>

        {error && <div className="error-banner"><AlertTriangle size={18}/><span>{error}</span></div>}

        {isSignup && <>
          <div className="field">
            <label>Your name</label>
            <div className="input-icon"><User size={15}/><input value={form.name} onChange={e => set("name", e.target.value)} placeholder="Full name" required autoComplete="name"/></div>
          </div>
          <div className="field">
            <label>Restaurant name</label>
            <div className="input-icon"><Store size={15}/><input value={form.restaurant_name} onChange={e => set("restaurant_name", e.target.value)} placeholder="e.g. Spice Corner" required/></div>
          </div>
        </>}

        <div className="field">
          <label>Email</label>
          <div className="input-icon"><Mail size={15}/><input type="email" value={form.email} onChange={e => set("email", e.target.value)} placeholder="you@restaurant.com" required autoComplete="email"/></div>
        </div>
        <div className="field">
          <label>Password</label>
          <div className="input-icon"><Lock size={15}/><input type="password" value={form.password} onChange={e => set("password", e.target.value)} placeholder={isSignup ? "At least 6 characters" : "Your password"} required minLength={isSignup ? 6 : undefined} autoComplete={isSignup ? "new-password" : "current-password"}/></div>
        </div>

        <button className="primary auth-submit" type="submit" disabled={busy}>
          {busy ? "Please wait…" : isSignup ? "Create account" : "Sign in"} <ChevronRight size={16}/>
        </button>

        <p className="auth-switch">
          {isSignup ? "Already have an account?" : "New to DineTrack?"}{" "}
          <button type="button" className="text-btn" onClick={() => switchMode(isSignup ? "login" : "signup")}>{isSignup ? "Sign in" : "Create an account"}</button>
        </p>
      </form>
    </div>
  </div>
}

function Dashboard({ user, onLogout }) {
  const isBlank = user.workspace !== DEMO_WORKSPACE;
  const [page, setPage] = useState("overview");
  const [accountOpen, setAccountOpen] = useState(false);
  const [dashboard, setDashboard] = useState(fallback);
  const [inventory, setInventory] = useState([]);
  const [forecast, setForecast] = useState([]);
  const [orders, setOrders] = useState([]);
  const [waste, setWaste] = useState([]);
  const [menu, setMenu] = useState([]);
  const [accuracy, setAccuracy] = useState({ overall: {}, items: [] });
  const [salesLog, setSalesLog] = useState({ orders: [], today_total: 0, today_orders: 0 });
  const [settings, setSettings] = useState(defaultSettings);
  const [dataStatus, setDataStatus] = useState({});
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [moreOpen, setMoreOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem("dinetrack-theme") || "dark"; } catch { return "dark"; }
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("dinetrack-theme", theme); } catch {}
  }, [theme]);

  async function get(path) {
    const r = await apiFetch(path);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [d, i, f, o, w, m, a, s, st, ds] = await Promise.all([
        get("/api/dashboard"),
        get("/api/inventory"),
        get("/api/forecast"),
        get("/api/orders"),
        get("/api/waste"),
        get("/api/menu"),
        get("/api/accuracy"),
        get("/api/sales/log"),
        get("/api/settings"),
        get("/api/data/status")
      ]);
      setDashboard(d);
      setInventory(i.inventory || []);
      setForecast(f.forecast || []);
      setOrders(o.orders || []);
      setWaste(w.waste_risk || []);
      setMenu(m.menu || []);
      setAccuracy(a || { overall: {}, items: [] });
      setSalesLog(s || { orders: [], today_total: 0, today_orders: 0 });
      setSettings(st || defaultSettings);
      setDataStatus(ds || {});
      setLastUpdated(new Date());
    } catch (e) {
      if (e.message !== "Session expired") setError(`Could not connect to DineTrack API at ${API}. Start FastAPI first, then refresh.`);
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings(next) {
    setSettingsSaving(true);
    setSettingsError("");
    try {
      const r = await apiFetch("/api/settings", {
        method: "PUT",
        body: JSON.stringify(next)
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Could not save settings");
      setSettings(data);
      await load();
      return true;
    } catch (e) {
      setSettingsError(e.message || "Could not save settings");
      return false;
    } finally {
      setSettingsSaving(false);
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    const seconds = settings.refresh_interval_seconds;
    if (!seconds) return;
    const id = setInterval(load, seconds * 1000);
    return () => clearInterval(id);
  }, [settings.refresh_interval_seconds]);

  const notifications = useMemo(() => {
    const inv = dashboard.inventory || {};
    const list = [];
    if (inv.critical > 0) list.push({
      id: "critical", tone: "red", icon: AlertTriangle, page: "inventory",
      title: `${inv.critical} ingredient${inv.critical > 1 ? "s" : ""} critically low`,
      desc: "Restock immediately to avoid running out."
    });
    if (inv.low > 0) list.push({
      id: "low", tone: "amber", icon: AlertTriangle, page: "orders",
      title: `${inv.low} ingredient${inv.low > 1 ? "s" : ""} running low`,
      desc: "Add them to your grocery list."
    });
    if (inv.orders_required > 0) list.push({
      id: "orders", tone: "blue", icon: ShoppingCart, page: "orders",
      title: `${inv.orders_required} item${inv.orders_required > 1 ? "s" : ""} need reordering`,
      desc: "Review purchase recommendations."
    });
    if (inv.waste_risk_items > 0) list.push({
      id: "waste", tone: "amber", icon: Leaf, page: "waste",
      title: `${inv.waste_risk_items} ingredient${inv.waste_risk_items > 1 ? "s" : ""} at waste risk`,
      desc: "Check the waste control page."
    });
    return list;
  }, [dashboard]);

  const filteredInventory = useMemo(() => {
    const q = query.toLowerCase().trim();
    return inventory.filter(x => !q || String(x.Ingredient).toLowerCase().includes(q));
  }, [inventory, query]);

  const filteredForecast = useMemo(() => {
    const q = query.toLowerCase().trim();
    return forecast.filter(x => !q || String(x.item).toLowerCase().includes(q));
  }, [forecast, query]);

  const forecastChart = useMemo(() => {
    const byDate = {};
    filteredForecast.forEach(x => {
      byDate[x.date] = (byDate[x.date] || 0) + Number(x.forecast_quantity || 0);
    });
    return Object.entries(byDate).map(([date, value]) => ({ date: shortDate(date), demand: Number(value.toFixed(1)) }));
  }, [filteredForecast]);

  const accuracyChart = useMemo(() => {
    return (accuracy.daily || []).map(x => ({
      date: shortDate(x.date),
      actual: Number(x.actual || 0),
      predicted: Number(x.predicted || 0)
    }));
  }, [accuracy]);

  const topForecast = useMemo(() => {
    const byItem = {};
    forecast.forEach(x => byItem[x.item] = (byItem[x.item] || 0) + Number(x.forecast_quantity || 0));
    return Object.entries(byItem).map(([item, demand]) => ({ item, demand: Number(demand.toFixed(1)) }))
      .sort((a,b) => b.demand-a.demand).slice(0, 8);
  }, [forecast]);

  const navigate = (p) => {
    setPage(p);
    setQuery("");
    setMoreOpen(false);
    setNotifOpen(false);
  };

  const moreActive = MORE_PAGE_IDS.includes(page);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><UtensilsCrossed size={21}/></div>
          <div><strong>DineTrack</strong><span>Inventory intelligence</span></div>
        </div>

        <div className="workspace">
          <span className="eyebrow">WORKSPACE</span>
          <button className="restaurant-switch">
            <span className="restaurant-avatar">{initials(settings.restaurant_name)}</span>
            <span><b>{settings.restaurant_name}</b><small>{isBlank ? "Restaurant · New workspace" : "Restaurant · Live"}</small></span>
            <ChevronRight size={16}/>
          </button>
        </div>

        <nav>
          <span className="eyebrow">MANAGEMENT</span>
          {nav.map(([id, label, Icon]) => (
            <button key={id} className={page === id ? "nav-item active" : "nav-item"} onClick={() => navigate(id)}>
              <Icon size={18}/><span>{label}</span>
              {id === "inventory" && dashboard.inventory.critical > 0 && <em>{dashboard.inventory.critical}</em>}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <button className={page === "settings" ? "nav-item active" : "nav-item"} onClick={() => navigate("settings")}>
            <SettingsIcon size={18}/><span>Settings</span>
          </button>
          <button className="nav-item" onClick={onLogout}>
            <LogOut size={18}/><span>Sign out</span>
          </button>
          <div className="powered"><Sparkles size={15}/> AI-assisted demand planning</div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar-brand">
            <div className="brand-mark small"><UtensilsCrossed size={17}/></div>
            <b>{settings.restaurant_name}</b>
          </div>
          <div className="breadcrumbs"><span>Workspace</span><ChevronRight size={14}/><b>{pageLabels[page]}</b></div>
          <div className="top-actions">
            <div className="search-box">
              <Search size={17}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search ingredients or menu items…" />
              <kbd>⌘ K</kbd>
            </div>
            <button className="icon-btn" onClick={() => setTheme(t => t === "dark" ? "light" : "dark")} title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
              {theme === "dark" ? <Sun size={16}/> : <Moon size={16}/>}
            </button>
            <div className="account">
              <button className="avatar" onClick={() => setAccountOpen(v => !v)} title={user.email}>{initials(user.name || settings.restaurant_name)}</button>
              {accountOpen && <>
                <div className="account-backdrop" onClick={() => setAccountOpen(false)}/>
                <div className="account-menu">
                  <div className="account-id"><b>{user.name}</b><span>{user.email}</span></div>
                  <button onClick={() => { setAccountOpen(false); navigate("settings"); }}><SettingsIcon size={15}/> Settings</button>
                  <button onClick={onLogout}><LogOut size={15}/> Sign out</button>
                </div>
              </>}
            </div>
          </div>
        </header>

        <button className="notif-fab" onClick={() => setNotifOpen(v => !v)}>
          <Bell size={20}/>
          {!!notifications.length && <span className="notif-fab-badge">{notifications.length}</span>}
        </button>

        {notifOpen && (
          <div className="notif-overlay" onClick={() => setNotifOpen(false)}>
            <div className="notif-panel" onClick={e => e.stopPropagation()}>
              <div className="notif-head">
                <h3><BellRing size={16}/> Notifications</h3>
                <button onClick={() => setNotifOpen(false)}><X size={16}/></button>
              </div>
              <div className="notif-list">
                {notifications.map(n => (
                  <button key={n.id} className="notif-item" onClick={() => navigate(n.page)}>
                    <div className={`notif-icon ${n.tone}`}><n.icon size={16}/></div>
                    <div><b>{n.title}</b><span>{n.desc}</span></div>
                    <ChevronRight size={14}/>
                  </button>
                ))}
                {!notifications.length && (
                  <div className="notif-empty"><CircleCheck size={20}/><span>You're all caught up.</span></div>
                )}
              </div>
            </div>
          </div>
        )}

        <section className="content">
          {error && <div className="error-banner"><AlertTriangle size={18}/><span>{error}</span><button onClick={load}>Retry</button></div>}

          {page === "overview" && <Overview isBlank={isBlank} restaurantName={settings.restaurant_name} dataStatus={dataStatus} dashboard={dashboard} accuracyChart={accuracyChart} topForecast={topForecast} inventory={inventory} waste={waste} navigate={navigate} loading={loading}/>}
          {page === "pos" && <PointOfSale menu={menu} loading={loading} onSaleComplete={load}/>}
          {page === "saleslog" && <SalesLog log={salesLog} loading={loading}/>}
          {page === "inventory" && <Inventory rows={filteredInventory} loading={loading} navigate={navigate}/>}
          {page === "forecast" && <Forecast rows={filteredForecast} chart={forecastChart} top={topForecast} accuracy={accuracy} loading={loading}/>}
          {page === "orders" && <Orders rows={orders} loading={loading}/>}
          {page === "waste" && <Waste rows={waste} loading={loading}/>}
          {page === "data" && <DataUpload status={dataStatus} onUploaded={load}/>}
          {page === "settings" && <SettingsPage settings={settings} onSave={saveSettings} saving={settingsSaving} error={settingsError}/>}

          <footer>
            <span>DineTrack · Restaurant inventory management</span>
            <span>{lastUpdated ? `Synced ${lastUpdated.toLocaleTimeString("en-IN", {hour:"2-digit", minute:"2-digit"})}` : "Waiting for API"} · <button onClick={load}><RefreshCw size={13}/> Refresh</button></span>
          </footer>
        </section>

        <nav className="bottom-nav">
          {primaryTabs.map(([id, label, Icon]) => (
            <button key={id} className={page === id ? "bottom-tab active" : "bottom-tab"} onClick={() => navigate(id)}>
              <Icon size={20}/><span>{label === "Purchase Orders" ? "Orders" : label === "Point of Sale" ? "POS" : label}</span>
            </button>
          ))}
          <button className={moreActive || moreOpen ? "bottom-tab active" : "bottom-tab"} onClick={() => setMoreOpen(true)}>
            <MoreHorizontal size={20}/><span>More</span>
          </button>
        </nav>
      </main>

      {moreOpen && (
        <div className="sheet-overlay" onClick={() => setMoreOpen(false)}>
          <div className="sheet" onClick={e => e.stopPropagation()}>
            <div className="sheet-handle"/>
            <span className="eyebrow">MORE</span>
            <div className="sheet-grid">
              {moreTabs.map(([id, label, Icon]) => (
                <button key={id} className={page === id ? "sheet-item active" : "sheet-item"} onClick={() => navigate(id)}>
                  <div className="sheet-icon"><Icon size={20}/></div><span>{label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PageHeading({ eyebrow, title, sub, action }) {
  return <div className="page-heading">
    <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{sub}</p></div>
    {action}
  </div>
}

function Overview({ isBlank, restaurantName, dataStatus, dashboard, accuracyChart, topForecast, inventory, waste, navigate, loading }) {
  const inv = dashboard.inventory || fallback.inventory;
  const ma = dashboard.model_accuracy || {};
  const maxTop = Math.max(...topForecast.map(x => x.demand), 1);
  const steps = [
    ["menu", "Upload your menu", "Dishes and the ingredients (grams per serving) each one uses."],
    ["inventory", "Upload kitchen stock", "Current inventory per ingredient, with units and category."],
    ["sales", "Upload sales history", "A few weeks of daily sales unlocks forecasts and accuracy."]
  ];
  const setupIncomplete = !loading && steps.some(([kind]) => dataStatus[kind] && !dataStatus[kind].uploaded);
  return <div>
    <PageHeading
      eyebrow="GOOD EVENING"
      title={isBlank && setupIncomplete ? `Welcome, ${restaurantName}.` : "Kitchen, under control."}
      sub={dashboard.sales_period?.start ? `Forecasting from ${shortDate(dashboard.sales_period.start)} to ${shortDate(dashboard.sales_period.end)} · Next 7 days` : "Live inventory intelligence"}
      action={<button className="primary" onClick={() => navigate("orders")}><ShoppingCart size={17}/> Review orders <ChevronRight size={16}/></button>}
    />

    {setupIncomplete && (
      <section className="card onboarding">
        <div className="onboarding-head">
          <div className="brand-mark"><Sparkles size={19}/></div>
          <div><h2>Finish setting up your workspace</h2><p>Every page works the same way as a live restaurant. They fill in as soon as your data is uploaded.</p></div>
        </div>
        <div className="onboarding-steps">
          {steps.map(([kind, title, desc], i) => {
            const done = dataStatus[kind]?.uploaded;
            return <div key={kind} className={done ? "done" : ""}><span>{done ? <CheckCircle2 size={14}/> : i + 1}</span><b>{title}</b><small>{done ? "Uploaded" : desc}</small></div>;
          })}
        </div>
        <button className="primary" onClick={() => navigate("data")}><Upload size={15}/> Upload your data <ChevronRight size={16}/></button>
      </section>
    )}

    <div className="kpi-grid five">
      <KPI icon={TrendingUp} label="7-day expected demand" value={num(dashboard.forecast?.total_expected_units, 0)} suffix="units" tone="blue" trend="ARIMA forecast"/>
      <KPI icon={Boxes} label="Ingredients tracked" value={inv.total_ingredients} suffix="items" tone="green" trend="Live stock"/>
      <KPI icon={AlertTriangle} label="Critical stock" value={inv.critical} suffix="items" tone="red" trend={inv.critical ? "Action needed" : "All clear"}/>
      <KPI icon={Leaf} label="Waste risk" value={inv.waste_risk_items} suffix="items" tone="amber" trend="Next 7 days"/>
      <AccuracyKPI accuracy={dashboard.model_accuracy}/>
    </div>

    <div className="dashboard-grid">
      <section className="card chart-card wide">
        <div className="card-head">
          <div><h2>Model accuracy &amp; precision</h2><p>Actual vs. predicted demand over the {ma.holdout_days || 14}-day backtest window</p></div>
          <div className="legend-chips">
            <span className="legend-chip actual"><i/> Actual</span>
            <span className="legend-chip predicted"><i/> Predicted</span>
            <span className="mini-label"><Gauge size={13}/> {ma.accuracy_pct != null ? `${num(ma.accuracy_pct,1)}% accurate` : "Backtest pending"}</span>
          </div>
        </div>
        <div className="chart-wrap">{accuracyChart.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={accuracyChart} margin={{top:10,right:8,left:-22,bottom:0}}><defs><linearGradient id="actualFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8fc194" stopOpacity={0.3}/><stop offset="100%" stopColor="#8fc194" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} strokeDasharray="4 5" stroke={chartGridColor}/><XAxis dataKey="date" tickLine={false} axisLine={false} tick={{fill:chartTickColor}}/>
        <YAxis
  domain={[160, 400]}
  ticks={[160, 200, 240, 280, 320, 360, 400]}
  tickLine={false}
  axisLine={false}
  tick={{fill:chartTickColor}}
/><Tooltip contentStyle={chartTooltipStyle} labelStyle={{color:chartTickColor}}/><Area type="monotone" dataKey="actual" name="Actual" strokeWidth={2.5} fill="url(#actualFill)" stroke="#8fc194"/><Area type="monotone" dataKey="predicted" name="Predicted" strokeWidth={2} strokeDasharray="5 4" fill="none" stroke="#5fc3dd"/></AreaChart></ResponsiveContainer> : <Empty text={loading ? "Loading backtest…" : "Not enough sales history for a backtest"}/>}</div>
      </section>

      <section className="card alerts-card">
        <div className="card-head"><div><h2>Needs attention</h2><p>Highest-priority kitchen signals</p></div><button className="text-btn" onClick={() => navigate("inventory")}>View all</button></div>
        <div className="attention-list">
          {dashboard.critical_items?.slice(0,5).map((x,i) => <div className="attention" key={i}><div className="signal red"><AlertTriangle size={16}/></div><div><b>{x.Ingredient}</b><span>{num(x.Current_Inventory)} in stock · {num(x.Days_of_Stock)} days left</span></div><ChevronRight size={16}/></div>)}
          {!dashboard.critical_items?.length && <div className="success-state"><CircleCheck size={22}/><div><b>Kitchen looks healthy</b><span>No critical ingredients right now.</span></div></div>}
        </div>
      </section>

      <section className="card wide">
        <div className="card-head"><div><h2>Top forecasted menu items</h2><p>Highest expected demand for the coming week</p></div><button className="text-btn" onClick={() => navigate("forecast")}>Open forecast</button></div>
        <div className="bars">
          {topForecast.map((x,i) => <div className="bar-row" key={x.item}><span>{x.item}</span><div className="bar-track"><div className="bar-fill" style={{width:`${x.demand/maxTop*100}%`}}/></div><b>{num(x.demand,0)}</b></div>)}
          {!topForecast.length && <Empty text={loading ? "Loading…" : "No menu forecast available"}/>}
        </div>
      </section>

      <section className="card">
        <div className="card-head"><div><h2>Waste watch</h2><p>Perishables with excess stock</p></div><button className="text-btn" onClick={() => navigate("waste")}>Manage</button></div>
        {waste.slice(0,4).map((x,i) => <div className="waste-row" key={i}><div><b>{x.Ingredient}</b><span>{formatQty(x.Expected_Excess, x.Unit)} excess</span></div><StatusPill status={x.Waste_Risk}/></div>)}
        {!waste.length && <Empty text="No elevated waste risk"/>}
      </section>
    </div>
  </div>
}

function KPI({icon: Icon, label, value, suffix, tone, trend}) {
  return <div className={`kpi ${tone}`}><div className="kpi-icon"><Icon size={18}/></div><div className="kpi-copy"><span>{label}</span><div><strong>{value}</strong><small>{suffix}</small></div><em>{trend}</em></div></div>
}

function AccuracyKPI({ accuracy }) {
  const pct = accuracy?.accuracy_pct;
  const tone = pct == null ? "blue" : pct >= 80 ? "green" : pct >= 60 ? "amber" : "red";
  const trend = pct == null ? "Backtest pending" : `${accuracy.holdout_days}-day backtest`;
  return <KPI icon={Gauge} label="Forecast accuracy" value={pct == null ? "—" : num(pct, 1)} suffix={pct == null ? "" : "%"} tone={tone} trend={trend}/>;
}

function PointOfSale({ menu, loading, onSaleComplete }) {
  const [cart, setCart] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [shortfalls, setShortfalls] = useState([]);
  const [lastOrder, setLastOrder] = useState(null);
  const [search, setSearch] = useState("");

  const filteredMenu = useMemo(() => {
    const q = search.toLowerCase().trim();
    return menu.filter(m => !q || m.item.toLowerCase().includes(q));
  }, [menu, search]);

  function addToCart(item, size, price) {
    const key = `${item}|${size}`;
    setCart(prev => {
      const existing = prev[key];
      return { ...prev, [key]: { item, size, price, quantity: (existing?.quantity || 0) + 1 } };
    });
  }

  function changeQty(key, delta) {
    setCart(prev => {
      const line = prev[key];
      if (!line) return prev;
      const quantity = line.quantity + delta;
      if (quantity <= 0) {
        const next = { ...prev };
        delete next[key];
        return next;
      }
      return { ...prev, [key]: { ...line, quantity } };
    });
  }

  function removeLine(key) {
    setCart(prev => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  const lines = Object.entries(cart).map(([key, line]) => ({ key, ...line }));
  const total = lines.reduce((sum, l) => sum + l.price * l.quantity, 0);
  const itemCount = lines.reduce((sum, l) => sum + l.quantity, 0);

  async function completeSale() {
    if (!lines.length) return;
    setSubmitting(true);
    setError("");
    try {
      const res = await apiFetch("/api/pos/sale", {
        method: "POST",
        body: JSON.stringify({
          cart: lines.map(l => ({ item: l.item, size: l.size, quantity: l.quantity }))
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Sale failed");
      setCart({});
      setShortfalls(data.shortfalls || []);
      setLastOrder(data.order || null);
      await onSaleComplete();
    } catch (e) {
      setError(e.message || "Could not complete sale");
    } finally {
      setSubmitting(false);
    }
  }

  return <div>
    <PageHeading eyebrow="POINT OF SALE" title="Ring up an order" sub="Selling an item deducts its recipe ingredients from live inventory and logs the sale."/>

    {error && <div className="error-banner"><AlertTriangle size={18}/><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}
    {lastOrder && <div className="success-banner"><CheckCircle2 size={18}/><div><b>Sale recorded · {money(lastOrder.total)}</b><span>{lastOrder.items.map(i => `${i.quantity}x ${i.item} (${i.size})`).join(", ")}</span></div><button onClick={() => setLastOrder(null)}>Dismiss</button></div>}
    {!!shortfalls.length && <div className="warn-banner"><AlertTriangle size={18}/><div><b>Stock ran short on the last sale</b><span>{shortfalls.map(s => `${s.ingredient} short by ${formatQty(s.short_by, s.unit)}`).join(", ")}</span></div><button onClick={() => setShortfalls([])}>Dismiss</button></div>}

    <div className="pos-layout">
      <div>
        <div className="menu-search">
          <Search size={16}/>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search the menu…" autoFocus/>
          {!!search && <button className="menu-search-clear" onClick={() => setSearch("")}><X size={14}/></button>}
        </div>
        <div className="menu-list">
          {filteredMenu.map(m => (
            <div className="menu-row" key={m.item}>
              <b>{m.item}</b>
              <div className="menu-row-sizes">
                {m.sizes.map(s => (
                  <button key={s.size} className="menu-size-chip" onClick={() => addToCart(m.item, s.size, s.price)}>
                    {s.size}<span>{money(s.price)}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
          {!filteredMenu.length && <Empty text={loading ? "Loading menu…" : !menu.length ? "No menu yet. Upload your menu and sales history on the Data Upload page." : "No menu items match your search"}/>}
        </div>
      </div>

      <div className="cart-panel">
        <h2>Current order</h2>
        <div className="cart-lines">
          {lines.map(l => (
            <div className="cart-line" key={l.key}>
              <div className="cart-line-info">
                <b>{l.item}</b>
                <span>{l.size} · {money(l.price)}</span>
              </div>
              <div className="qty-stepper">
                <button onClick={() => changeQty(l.key, -1)}><Minus size={13}/></button>
                <span>{l.quantity}</span>
                <button onClick={() => changeQty(l.key, 1)}><Plus size={13}/></button>
              </div>
              <button className="cart-remove" onClick={() => removeLine(l.key)}><Trash2 size={14}/></button>
            </div>
          ))}
          {!lines.length && <div className="cart-empty">Tap a menu item to add it to the order.</div>}
        </div>
        <div className="cart-totals">
          <div className="row"><span>Items</span><span>{itemCount}</span></div>
          <div className="row total"><span>Total</span><span>{money(total)}</span></div>
        </div>
        <button className="primary" disabled={!lines.length || submitting} onClick={completeSale}>
          <CreditCard size={16}/> {submitting ? "Recording sale…" : "Complete sale"}
        </button>
      </div>
    </div>
  </div>
}

function SalesLog({ log, loading }) {
  const orders = log.orders || [];

  return <div>
    <PageHeading eyebrow="SALES LOG" title="Order history" sub="Every sale rung up through Point of Sale, kept for reference."/>

    <div className="kpi-grid compact">
      <KPI icon={Receipt} label="Orders today" value={log.today_orders || 0} suffix="orders" tone="blue" trend="Live"/>
      <KPI icon={CreditCard} label="Revenue today" value={money(log.today_total)} suffix="total" tone="green" trend="POS sales"/>
      <KPI icon={Package} label="Orders logged" value={orders.length} suffix="shown" tone="amber" trend="Most recent first"/>
    </div>

    <section className="card table-card">
      <TableTop title="Recent orders" count={orders.length}/>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Time</th><th>Items</th><th>Item count</th><th>Total</th></tr></thead>
          <tbody>
            {orders.map(o => (
              <tr key={o.order_id}>
                <td>{new Date(o.timestamp).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
                <td>{o.items.map(i => `${num(i.quantity, 0)}x ${i.item} (${i.size})`).join(", ")}</td>
                <td>{o.item_count}</td>
                <td className="order-num">{money(o.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!orders.length && <Empty text={loading ? "Loading sales log…" : "No sales recorded yet — ring up an order from Point of Sale."}/>}
      </div>
    </section>
  </div>
}

function Inventory({ rows, loading, navigate }) {
  const counts = rows.reduce((a,x)=>{a[x.Status]=(a[x.Status]||0)+1;return a},{});
  const wasteFlagged = rows.filter(x => x.Waste_Risk && x.Waste_Risk !== "LOW").length;
  return <div><PageHeading eyebrow="INVENTORY CONTROL" title="Ingredient inventory" sub="Stock coverage calculated against the 7-day demand forecast." action={<button className="secondary" onClick={()=>window.print()}><Download size={16}/> Export / Print</button>}/>
    <div className="status-strip">
      {["CRITICAL","LOW","NORMAL","OVERSTOCKED"].map(s=><div key={s}><span className={`status-dot ${s.toLowerCase()}`}></span><b>{counts[s]||0}</b><span>{s[0]+s.slice(1).toLowerCase()}</span></div>)}
    </div>
    {wasteFlagged > 0 && (
      <div className="notice">
        <Leaf size={18}/>
        <div>
          <b>{wasteFlagged} ingredient{wasteFlagged > 1 ? "s are" : " is"} sitting on more stock than the next 7 days will use</b>
          <span>Same table, waste lens — see what to push before it spoils.</span>
        </div>
        <button className="text-btn" style={{marginLeft:"auto"}} onClick={() => navigate?.("waste")}>Open Waste Control</button>
      </div>
    )}
    <section className="card table-card">
      <TableTop title="Current kitchen stock" count={rows.length}/>
      <div className="table-scroll desktop-table"><table><thead><tr><th>Ingredient</th><th>Category</th><th>Current</th><th>7-day demand</th><th>Days of stock</th><th>Status</th><th>Suggested order</th><th>Waste risk</th></tr></thead><tbody>
        {rows.map((x,i)=><tr key={i}><td><b>{x.Ingredient}</b></td><td>{x.Category || "—"}</td><td>{formatQty(x.Current_Inventory, x.Unit)}</td><td>{formatQty(x.Forecast_7_Day_Demand, x.Unit)}</td><td><div className="stock-meter"><div style={{width:`${Math.min(100,(x.Days_of_Stock||0)/14*100)}%`}}></div><span>{x.Days_of_Stock >= 900 ? "∞" : num(x.Days_of_Stock)} d</span></div></td><td><StatusPill status={x.Status}/></td><td className="order-num">{Number(x.Suggested_Order)>0 ? `+${formatQty(x.Suggested_Order, x.Unit)}` : "—"}</td><td>{x.Waste_Risk && x.Waste_Risk !== "LOW" ? <StatusPill status={x.Waste_Risk}/> : <span style={{color:"var(--muted)"}}>—</span>}</td></tr>)}
      </tbody></table></div>
      <div className="mobile-cards">
        {rows.map((x,i) => (
          <div className="info-card" key={i}>
            <div className="todo-card-top"><b>{x.Ingredient}</b><StatusPill status={x.Status}/></div>
            <div className="info-card-grid">
              <div><span>Current</span><b>{formatQty(x.Current_Inventory, x.Unit)}</b></div>
              <div><span>7-day demand</span><b>{formatQty(x.Forecast_7_Day_Demand, x.Unit)}</b></div>
              <div><span>Days left</span><b>{x.Days_of_Stock >= 900 ? "∞" : num(x.Days_of_Stock)}</b></div>
              <div><span>Suggested order</span><b>{Number(x.Suggested_Order)>0 ? `+${formatQty(x.Suggested_Order, x.Unit)}` : "—"}</b></div>
            </div>
            {x.Waste_Risk && x.Waste_Risk !== "LOW" && <div style={{marginTop:8}}><StatusPill status={x.Waste_Risk}/> <span style={{fontSize:10,color:"var(--muted)"}}>waste risk</span></div>}
          </div>
        ))}
      </div>
      {!rows.length && <Empty text={loading ? "Loading inventory…" : "No inventory matches your search"}/>}
    </section>
  </div>
}

function Forecast({ rows, chart, top, accuracy, loading }) {
  const [item, setItem] = useState("ALL");

  const items = [...new Set(rows.map((x) => x.item))];

  const shown =
    item === "ALL"
      ? rows
      : rows.filter((x) => x.item === item);

  const chartRows =
    item === "ALL"
      ? chart
      : (() => {
          const m = {};

          shown.forEach((x) => {
            m[x.date] =
              (m[x.date] || 0) +
              Number(x.forecast_quantity || 0);
          });

          return Object.entries(m).map(
            ([date, demand]) => ({
              date: shortDate(date),
              demand
            })
          );
        })();

  return (
    <div>
      <PageHeading
        eyebrow="DEMAND PLANNING"
        title="7-day demand forecast"
        sub="ARIMA predictions converted to equivalent base servings across menu sizes."
        action={
          <div className="select-wrap">
            <CalendarDays size={16} />

            <select
              value={item}
              onChange={(e) => setItem(e.target.value)}
            >
              <option value="ALL">
                All menu items
              </option>

              {items.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </div>
        }
      />

      <div className="dashboard-grid">

        {/* DEMAND CURVE */}
        <section className="card wide chart-card">
          <div className="card-head">
            <div>
              <h2>Demand curve</h2>
              <p>Expected units by day</p>
            </div>
          </div>

          <div className="chart-wrap tall">
            {chartRows.length ? (
              <ResponsiveContainer
                width="100%"
                height="100%"
              >
                <LineChart
                  data={chartRows}
                  margin={{
                    top: 10,
                    right: 8,
                    left: -22,
                    bottom: 0
                  }}
                >
                  <CartesianGrid
                    vertical={false}
                    strokeDasharray="4 5"
                    stroke={chartGridColor}
                  />

                  <XAxis
                    dataKey="date"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: chartTickColor }}
                  />

                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: chartTickColor }}
                  />

                  <Tooltip contentStyle={chartTooltipStyle} labelStyle={{ color: chartTickColor }} />

                  <Line
                    type="monotone"
                    dataKey="demand"
                    strokeWidth={3}
                    stroke="#8fc194"
                    dot={{ r: 4, fill: "#8fc194" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Empty
                text={
                  loading
                    ? "Loading..."
                    : "No forecast data"
                }
              />
            )}
          </div>
        </section>


        {/* DEMAND LEADERS */}
        <section className="card">
          <div className="card-head">
            <div>
              <h2>Demand leaders</h2>
              <p>7-day total</p>
            </div>
          </div>

          {top.map((x, i) => (
            <div
              className="rank-row"
              key={x.item}
            >
              <span>{i + 1}</span>

              <b>{x.item}</b>

              <strong>
                {num(x.demand, 0)}
              </strong>
            </div>
          ))}
        </section>

        {/* MODEL ACCURACY */}
        <section className="card wide">
          <div className="card-head">
            <div>
              <h2>Model accuracy</h2>
              <p>{accuracy?.overall?.holdout_days || 14}-day backtest against actual sales</p>
            </div>
            <span className="mini-label"><Gauge size={13}/> Backtest</span>
          </div>

          <div className="waste-metrics" style={{margin:"14px 0 6px"}}>
            <div><span>Accuracy</span><b>{accuracy?.overall?.accuracy_pct != null ? `${num(accuracy.overall.accuracy_pct,1)}%` : "—"}</b></div>
            <div><span>MAPE</span><b>{accuracy?.overall?.mape != null ? `${num(accuracy.overall.mape,1)}%` : "—"}</b></div>
            <div><span>Items scored</span><b>{accuracy?.overall?.items_scored ?? 0}/{accuracy?.overall?.items_total ?? 0}</b></div>
          </div>

          {(accuracy?.items || []).slice(0, 8).map((x, i) => (
            <div className="rank-row" key={x.item}>
              <span>{i + 1}</span>
              <b>{x.item}</b>
              <strong>{x.accuracy_pct != null ? `${num(x.accuracy_pct,0)}%` : "n/a"}</strong>
            </div>
          ))}
          {!accuracy?.items?.length && <Empty text={loading ? "Loading…" : "No accuracy data"}/>}
        </section>

      </div>


      {/* DAILY FORECAST TABLE */}
      <section className="card table-card">

        <TableTop
          title="Daily forecast records"
          count={shown.length}
        />

        <div className="table-scroll">

          {shown.length ? (
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Menu item</th>
                  <th>Forecast quantity</th>
                </tr>
              </thead>

              <tbody>
                {shown.map((x, i) => (
                  <tr key={i}>
                    <td>
                      {shortDate(x.date)}
                    </td>

                    <td>
                      <b>{x.item}</b>
                    </td>

                    <td className="order-num">
                      {num(
                        x.forecast_quantity,
                        2
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty
              text={
                loading
                  ? "Loading forecast..."
                  : "No forecast records"
              }
            />
          )}

        </div>

      </section>

    </div>
  );
}

function Orders({ rows, loading }) {
  const [checked, setChecked] = useState({});
  const doneCount = rows.filter((_, i) => checked[i]).length;

  function toggle(i) {
    setChecked(prev => ({ ...prev, [i]: !prev[i] }));
  }

  function buyLabel(x) {
    return Number(x.Suggested_Order) > 0 ? `+${formatQty(x.Suggested_Order, x.Unit)}` : "Restock";
  }

  return <div>
    <PageHeading
      eyebrow="PROCUREMENT"
      title="Grocery list"
      sub="Every low or critical ingredient, ready to check off as you shop."
      action={<button className="secondary" onClick={() => setChecked({})}><RefreshCw size={16}/> Reset list</button>}
    />
    <div className="notice"><Zap size={18}/><div><b>Smart reorder logic</b><span>Lead time and safety stock (tune them in Settings) are built into the recommended quantities.</span></div></div>

    <section className="card table-card">
      <TableTop title={`Grocery list · ${doneCount} of ${rows.length} bought`} count={rows.length}/>

      <div className="table-scroll desktop-table">
        <table><thead><tr><th></th><th>Ingredient</th><th>Current</th><th>7-day demand</th><th>Coverage</th><th>Status</th><th>Buy</th></tr></thead><tbody>
          {rows.map((x, i) => (
            <tr key={i} className={checked[i] ? "row-done" : ""}>
              <td><input type="checkbox" checked={!!checked[i]} onChange={() => toggle(i)}/></td>
              <td><b>{x.Ingredient}</b></td>
              <td>{formatQty(x.Current_Inventory, x.Unit)}</td>
              <td>{formatQty(x.Forecast_7_Day_Demand, x.Unit)}</td>
              <td>{x.Days_of_Stock >= 900 ? "∞" : `${num(x.Days_of_Stock)} days`}</td>
              <td><StatusPill status={x.Status}/></td>
              <td><strong className="suggested">{buyLabel(x)}</strong></td>
            </tr>
          ))}
        </tbody></table>
      </div>

      <div className="mobile-cards">
        {rows.map((x, i) => (
          <label className={checked[i] ? "todo-card done" : "todo-card"} key={i}>
            <input type="checkbox" checked={!!checked[i]} onChange={() => toggle(i)}/>
            <div className="todo-card-body">
              <div className="todo-card-top"><b>{x.Ingredient}</b><StatusPill status={x.Status}/></div>
              <span>{formatQty(x.Current_Inventory, x.Unit)} left · {x.Days_of_Stock >= 900 ? "∞" : `${num(x.Days_of_Stock)}d`} coverage</span>
              <strong className="suggested">{buyLabel(x)}</strong>
            </div>
          </label>
        ))}
      </div>

      {!rows.length && <Empty text={loading ? "Loading orders…" : "Nothing low or critical right now — nice work."}/>}
    </section>
  </div>
}

function usedInLabel(usedIn) {
  const list = usedIn || [];
  if (!list.length) return null;
  const shown = list.slice(0, 4);
  const extra = list.length - shown.length;
  return [...shown, ...(extra > 0 ? [`+${extra} more`] : [])];
}

const DISPOSAL = {
  GARDENING: { label: "Gardening", icon: Sprout, cls: "garden" },
  DONATE: { label: "Donate", icon: HandHeart, cls: "donate" }
};

function DisposalTag({ route }) {
  const d = DISPOSAL[route];
  if (!d) return null;
  const Icon = d.icon;
  return <span className={`disposal-tag ${d.cls}`}><Icon size={12}/> {d.label}</span>;
}

function Waste({ rows, loading }) {
  const [route, setRoute] = useState("ALL");
  const high=rows.filter(x=>x.Waste_Risk==="HIGH").length, med=rows.filter(x=>x.Waste_Risk==="MEDIUM").length;
  const garden=rows.filter(x=>x.Disposal_Route==="GARDENING").length, donate=rows.filter(x=>x.Disposal_Route==="DONATE").length;
  const shown = route==="ALL" ? rows : rows.filter(x=>x.Disposal_Route===route);
  return <div><PageHeading eyebrow="WASTE CONTROL" title="Waste prevention" sub="Prioritize excess perishable stock before it becomes food waste."/>
    <div className="kpi-grid"><KPI icon={Flame} label="High risk" value={high} suffix="ingredients" tone="red" trend="Immediate action"/><KPI icon={Droplets} label="Medium risk" value={med} suffix="ingredients" tone="amber" trend="Monitor closely"/><KPI icon={Sprout} label="For gardening" value={garden} suffix="items" tone="green" trend="Compost scraps & spoilage"/><KPI icon={HandHeart} label="To donate" value={donate} suffix="items" tone="blue" trend="Give before expiry"/></div>
    {rows.length>0 && <div className="disposal-filter">{[["ALL","All"],["GARDENING","Gardening"],["DONATE","Donate"]].map(([k,l])=><button key={k} className={route===k?"active":""} onClick={()=>setRoute(k)}>{l}</button>)}</div>}
    <div className="waste-grid">{shown.map((x,i)=><section className={`card waste-card ${String(x.Waste_Risk).toLowerCase()}`} key={i}><div className="waste-card-head"><div className="signal"><Leaf size={17}/></div><div className="waste-card-tags"><DisposalTag route={x.Disposal_Route}/><StatusPill status={x.Waste_Risk}/></div></div><h2>{x.Ingredient}</h2><div className="waste-metrics"><div><span>Current stock</span><b>{formatQty(x.Current_Inventory, x.Unit)}</b></div><div><span>Expected usage</span><b>{formatQty(x.Expected_7_Day_Usage, x.Unit)}</b></div><div><span>Expected excess</span><b>{formatQty(x.Expected_Excess, x.Unit)}</b></div></div>{usedInLabel(x.Used_In) && <div className="used-in-row">{usedInLabel(x.Used_In).map((d,j)=><span className="mini-label" key={j}>{d}</span>)}</div>}<div className="suggestion"><Sparkles size={16}/><span>{x.Waste_Reduction_Suggestion}</span></div>{x.Disposal_Note && <div className={`disposal-note ${DISPOSAL[x.Disposal_Route]?.cls || ""}`}>{x.Disposal_Route==="GARDENING"?<Sprout size={16}/>:<HandHeart size={16}/>}<span>{x.Disposal_Note}</span></div>}</section>)}</div>
    {!rows.length&&<div className="card"><Empty text={loading?"Loading waste analysis…":"No medium/high waste risks detected."}/></div>}
  </div>
}

const DATASETS = [
  {
    kind: "menu", icon: UtensilsCrossed, title: "Menu & recipes",
    desc: "One row per dish ingredient: how many grams (or ml) of each ingredient a half/base serving uses. Medium and Large are scaled automatically."
  },
  {
    kind: "inventory", icon: Boxes, title: "Kitchen inventory",
    desc: "Current stock of every ingredient. Use the same ingredient names and units as the menu file. Category \"Perishable\" enables waste tracking."
  },
  {
    kind: "sales", icon: TrendingUp, title: "Sales history",
    desc: "Daily quantity sold per dish and size (Half, Medium or Large), with its price. Prices here also build the Point of Sale menu."
  }
];

function DataUpload({ status, onUploaded }) {
  return <div>
    <PageHeading eyebrow="DATA" title="Upload your data" sub="Upload CSV or Excel files. The forecast, inventory status and waste analysis recalculate as soon as a file is uploaded."/>
    <div className="notice"><Sparkles size={18}/><div><b>Not sure about the format?</b><span>Download a template, fill it in with your own data, and upload it back. Column names are not case-sensitive.</span></div></div>
    <div className="upload-grid">
      {DATASETS.map(d => <UploadCard key={d.kind} {...d} status={status[d.kind]} onUploaded={onUploaded}/>)}
    </div>
  </div>
}

function UploadCard({ kind, icon: Icon, title, desc, status, onUploaded }) {
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState("replace");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [inputKey, setInputKey] = useState(0);
  const uploaded = status?.uploaded;

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError("");
    setDone("");
    try {
      const body = new FormData();
      body.append("file", file);
      const r = await apiFetch(`/api/data/upload/${kind}?mode=${mode}`, { method: "POST", body });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Upload failed");
      setDone(`${file.name} uploaded · ${data.rows} rows${mode === "append" ? " in total" : ""}`);
      setFile(null);
      setInputKey(k => k + 1);
      await onUploaded();
    } catch (e) {
      setError(e.message || "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return <section className="card upload-card">
    <div className="upload-card-head">
      <div className="signal"><Icon size={17}/></div>
      {status ? <StatusPill status={uploaded ? "Uploaded" : "Not uploaded"}/> : null}
    </div>
    <h2>{title}</h2>
    <p>{desc}</p>
    <div className="upload-columns">
      {(status?.columns || []).map(c => <span key={c} className={status.required_columns.includes(c) ? "mini-label required" : "mini-label"}>{c}</span>)}
    </div>
    <small className="upload-hint">Highlighted columns are required; the rest are optional.</small>

    {error && <div className="error-banner"><AlertTriangle size={18}/><span>{error}</span></div>}
    {done && <div className="success-banner"><CheckCircle2 size={18}/><div><b>Dashboard updated</b><span>{done}</span></div></div>}

    <label className="file-drop">
      <input key={inputKey} type="file" accept=".csv,.xlsx,.xls" onChange={e => { setFile(e.target.files[0] || null); setError(""); setDone(""); }}/>
      <Upload size={16}/><span>{file ? file.name : "Choose a .csv or .xlsx file"}</span>
    </label>

    {kind === "sales" && uploaded && (
      <div className="field">
        <label>When uploading</label>
        <select value={mode} onChange={e => setMode(e.target.value)}>
          <option value="replace">Replace existing sales history</option>
          <option value="append">Add to existing sales history</option>
        </select>
      </div>
    )}

    <div className="upload-actions">
      <a className="secondary" href={`${API}/api/data/template/${kind}`} download><Download size={15}/> Template</a>
      <button className="primary" disabled={!file || busy} onClick={upload}>
        <Upload size={15}/> {busy ? "Uploading & recalculating…" : uploaded ? "Upload & update" : "Upload"}
      </button>
    </div>
  </section>
}

function SettingsPage({ settings, onSave, saving, error }) {
  const [form, setForm] = useState(settings);
  const [saved, setSaved] = useState(false);

  useEffect(() => { setForm(settings); }, [settings]);

  function set(key, value) {
    setForm(prev => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  async function submit(e) {
    e.preventDefault();
    const ok = await onSave(form);
    if (ok) {
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    }
  }

  return <div>
    <PageHeading eyebrow="CONFIGURATION" title="Settings" sub="Tune how DineTrack calculates stock status, reorder points and refresh."/>

    {error && <div className="error-banner"><AlertTriangle size={18}/><span>{error}</span></div>}
    {saved && <div className="success-banner"><CheckCircle2 size={18}/><div><b>Settings saved</b><span>Dashboard recalculated with the new values.</span></div></div>}

    <form className="card settings-form" onSubmit={submit}>
      <div className="field">
        <label>Restaurant name</label>
        <input value={form.restaurant_name} onChange={e => set("restaurant_name", e.target.value)}/>
      </div>

      <div className="field-grid">
        <div className="field">
          <label>Lead time (days)</label>
          <input type="number" min="0" step="0.5" value={form.lead_time_days} onChange={e => set("lead_time_days", Number(e.target.value))}/>
        </div>
        <div className="field">
          <label>Safety stock (days)</label>
          <input type="number" min="0" step="0.5" value={form.safety_stock_days} onChange={e => set("safety_stock_days", Number(e.target.value))}/>
        </div>
      </div>

      <span className="eyebrow field-label">STOCK STATUS THRESHOLDS (DAYS OF STOCK REMAINING)</span>
      <div className="field-grid three">
        <div className="field">
          <label>Critical at or below</label>
          <input type="number" min="0" step="0.5" value={form.critical_days} onChange={e => set("critical_days", Number(e.target.value))}/>
        </div>
        <div className="field">
          <label>Low at or below</label>
          <input type="number" min="0" step="0.5" value={form.low_days} onChange={e => set("low_days", Number(e.target.value))}/>
        </div>
        <div className="field">
          <label>Normal at or below</label>
          <input type="number" min="0" step="0.5" value={form.normal_days} onChange={e => set("normal_days", Number(e.target.value))}/>
        </div>
      </div>

      <div className="field">
        <label>Auto-refresh</label>
        <select value={form.refresh_interval_seconds} onChange={e => set("refresh_interval_seconds", Number(e.target.value))}>
          <option value={0}>Off</option>
          <option value={30}>Every 30 seconds</option>
          <option value={60}>Every minute</option>
          <option value={120}>Every 2 minutes</option>
          <option value={300}>Every 5 minutes</option>
        </select>
      </div>

      <button className="primary" type="submit" disabled={saving}>
        <Save size={16}/> {saving ? "Saving…" : "Save settings"}
      </button>
    </form>
  </div>
}

function TableTop({title,count}) {
  return <div className="table-top"><div><h2>{title}</h2><span>{count} records</span></div><div className="table-actions"><button className="icon-btn"><Command size={16}/></button></div></div>
}

export default App;