import React, { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, clearToken, getToken, setToken } from "./api";

function rupees(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

const RISK_I18N = { low: "riskLow", med: "riskMed", high: "riskHigh" };

function riskClass(level) {
  if (level === "high") return "danger";
  if (level === "med") return "warn";
  return "";
}

function ProfitTerms({ area, village, district, yld, qty, perHa }) {
  const { t } = useTranslation();
  if (!area) return null;
  const place = [village, district].filter(Boolean).join(", ");
  return (
    <p className="muted">
      {t("profitOnArea", { area, place: place || t("yourFarm") })}
      {yld ? ` · ${t("harvestQty", { qty: Math.round(qty || 0), yld: Math.round(yld) })}` : ""}
      {perHa != null ? ` · ${t("perHectare")}: ${rupees(perHa)}` : ""}
    </p>
  );
}

function RiskBadge({ risk }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  if (!risk?.level) return null;
  const why = risk.why || t("riskWhyFallback");
  return (
    <span className="risk-wrap">
      <button
        type="button"
        className={`badge ${riskClass(risk.level)}`}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-expanded={open}
      >
        {t(RISK_I18N[risk.level] || "riskMed")}
      </button>
      {open && <span className="risk-tip">{why}</span>}
    </span>
  );
}

function Freshness({ data }) {
  const { t } = useTranslation();
  if (!data) return null;
  const q = data.quality || "actual";
  const label = q === "predicted" ? t("predicted") : q === "estimated" ? t("estimated") : q === "missing" ? "Missing" : t("actual");
  return (
    <p className="muted">
      {t("source")}: {data.source || "—"} · {t("updated")}: {data.last_updated ? new Date(data.last_updated).toLocaleString() : "—"}
      {data.price_date ? ` · Date: ${data.price_date}` : ""} · {label}
    </p>
  );
}

function LangSwitch() {
  const { i18n } = useTranslation();
  const set = async (lng) => {
    i18n.changeLanguage(lng);
    localStorage.setItem("lang", lng);
    try {
      await api(`/api/auth/language?lang=${lng}`, { method: "PUT" });
    } catch {
      /* not logged in */
    }
  };
  return (
    <div className="lang">
      {["en", "hi", "mr"].map((lng) => (
        <button
          key={lng}
          type="button"
          className={i18n.language.startsWith(lng) ? "on" : ""}
          onClick={() => set(lng)}
        >
          {lng === "en" ? "English" : lng === "hi" ? "हिन्दी" : "मराठी"}
        </button>
      ))}
    </div>
  );
}

function Login({ onAuth }) {
  const { t } = useTranslation();
  const [email, setEmail] = useState("farmer@farmdss.local");
  const [password, setPassword] = useState("ChangeMeFarmer1!");
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      const data = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      onAuth(data);
    } catch (ex) {
      setErr(ex.message);
    }
  };
  return (
    <div className="page">
      <div className="hero">
        <h1>{t("appName")}</h1>
        <p>{t("tagline")}</p>
      </div>
      <LangSwitch />
      <form className="card" onSubmit={submit}>
        {err && <div className="error">{err}</div>}
        <label>{t("email")}</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        <label>{t("password")}</label>
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
        <button className="btn">{t("login")}</button>
      </form>
      <NavLink to="/register">
        <button className="btn secondary">{t("register")}</button>
      </NavLink>
      <p className="muted">{t("syncHint")}</p>
    </div>
  );
}

function Register({ onAuth }) {
  const { t, i18n } = useTranslation();
  const [form, setForm] = useState({ email: "", password: "", full_name: "", preferred_language: i18n.language.slice(0, 2) });
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      const data = await api("/api/auth/register", { method: "POST", body: JSON.stringify(form) });
      onAuth(data);
    } catch (ex) {
      setErr(ex.message);
    }
  };
  return (
    <div className="page">
      <div className="hero">
        <h1>{t("register")}</h1>
      </div>
      <form className="card" onSubmit={submit}>
        {err && <div className="error">{err}</div>}
        <label>{t("name")}</label>
        <input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        <label>{t("email")}</label>
        <input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <label>{t("password")}</label>
        <input required minLength={8} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <button className="btn">{t("register")}</button>
      </form>
    </div>
  );
}

function FarmPage() {
  const { t } = useTranslation();
  const [farm, setFarm] = useState({ name: "My farm", state: "Maharashtra", district: "Raigad", village: "Panvel", latitude: 18.9894, longitude: 73.1175, area_hectares: 1 });
  const [q, setQ] = useState("");
  const [places, setPlaces] = useState([]);
  const [msg, setMsg] = useState("");
  const [crops, setCrops] = useState([]);
  const [cost, setCost] = useState({ crop_id: "", season: "kharif", total_production_cost: "", expected_yield_quintal_per_hectare: "" });

  useEffect(() => {
    api("/api/farms")
      .then((rows) => {
        if (rows[0]) setFarm(rows[0]);
      })
      .catch(() => {});
    api("/api/crops").then(setCrops).catch(() => {});
  }, []);

  const search = async () => {
    const data = await api(`/api/geocode?q=${encodeURIComponent(q)}`);
    setPlaces(data.results || []);
  };
  const save = async (e) => {
    e.preventDefault();
    await api("/api/farms", { method: "POST", body: JSON.stringify(farm) });
    setMsg("Saved.");
  };
  const saveCost = async (e) => {
    e.preventDefault();
    await api("/api/farms/costs", {
      method: "POST",
      body: JSON.stringify({
        crop_id: Number(cost.crop_id),
        season: cost.season,
        total_production_cost: cost.total_production_cost === "" ? null : Number(cost.total_production_cost),
        expected_yield_quintal_per_hectare: cost.expected_yield_quintal_per_hectare === "" ? null : Number(cost.expected_yield_quintal_per_hectare),
      }),
    });
    setMsg("Your costs were saved.");
  };
  return (
    <div>
      <div className="card">
        <h2>{t("myFarm")}</h2>
        <p>{t("farmHelp")}</p>
        {msg && <div className="ok">{msg}</div>}
        <label>{t("searchPlace")}</label>
        <div className="row">
          <input value={q} onChange={(e) => setQ(e.target.value)} />
          <button type="button" className="btn small" onClick={search}>
            Search
          </button>
        </div>
        {places.map((p, i) => (
          <button
            key={i}
            className="btn secondary"
            type="button"
            onClick={() =>
              setFarm({
                ...farm,
                village: p.name,
                district: p.admin2 || farm.district,
                state: p.admin1 || farm.state,
                latitude: p.latitude,
                longitude: p.longitude,
              })
            }
          >
            {p.name}, {p.admin2 || ""} {p.admin1}
          </button>
        ))}
        <form onSubmit={save}>
          <label>{t("state")}</label>
          <input value={farm.state} onChange={(e) => setFarm({ ...farm, state: e.target.value })} required />
          <label>{t("district")}</label>
          <input value={farm.district} onChange={(e) => setFarm({ ...farm, district: e.target.value })} required />
          <label>{t("village")}</label>
          <input value={farm.village || ""} onChange={(e) => setFarm({ ...farm, village: e.target.value })} />
          <label>{t("area")}</label>
          <input type="number" step="0.01" value={farm.area_hectares} onChange={(e) => setFarm({ ...farm, area_hectares: Number(e.target.value) })} />
          <p className="muted">
            Location: {farm.latitude}, {farm.longitude}
          </p>
          <button className="btn">{t("save")}</button>
        </form>
      </div>
      <form className="card" onSubmit={saveCost}>
        <h2>{t("yourCosts")}</h2>
        <label>Crop</label>
        <select value={cost.crop_id} onChange={(e) => setCost({ ...cost, crop_id: e.target.value })} required>
          <option value="">—</option>
          {crops.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name_en}
            </option>
          ))}
        </select>
        <label>{t("prodCost")}</label>
        <input type="number" value={cost.total_production_cost} onChange={(e) => setCost({ ...cost, total_production_cost: e.target.value })} />
        <label>{t("yield")}</label>
        <input type="number" value={cost.expected_yield_quintal_per_hectare} onChange={(e) => setCost({ ...cost, expected_yield_quintal_per_hectare: e.target.value })} />
        <button className="btn">{t("save")}</button>
      </form>
    </div>
  );
}

function Dashboard() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [weather, setWeather] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api("/api/dashboard")
      .then(setData)
      .catch((e) => setErr(e.message));
    api("/api/weather")
      .then(setWeather)
      .catch(() => {});
  }, []);
  if (err) {
    if (err.includes("farm location")) return <FarmPage />;
    return <div className="error">{err}</div>;
  }
  if (!data) return <p>Loading…</p>;
  if (!data.has_data) {
    return (
      <div className="card">
        <h2>{t("today")}</h2>
        <p>{data.message || t("noData")}</p>
      </div>
    );
  }
  const d = data.today;
  return (
    <div>
      <div className="card">
        <h2>{t("today")}</h2>
        <p className="muted">{t("bestCrop")}</p>
        <div className="stat">{d.best_crop}</div>
        <p className="muted">{t("bestMarket")}</p>
        <div className="stat" style={{ fontSize: "1.3rem" }}>
          {d.best_market}
        </div>
        <p className="muted">{t("expectedPrice")}</p>
        <div className="stat" style={{ fontSize: "1.3rem" }}>
          {rupees(d.expected_price_min)}–{rupees(d.expected_price_max)} {t("perQuintal")}
        </div>
        <p className="muted">{t("expectedProfit")}</p>
        <div className="stat">{rupees(d.expected_net_profit)}</div>
        <ProfitTerms
          area={d.area_hectares}
          village={d.farm_village}
          district={d.farm_district}
          yld={d.yield_quintal_per_hectare}
          qty={d.quantity_quintals}
          perHa={d.profit_per_hectare}
        />
        <p className="muted">{t("profitFormula")}</p>
        <p className="muted">{t("risk")}</p>
        <div>
          <RiskBadge risk={d.risk} />
        </div>
        <p className="muted">{t("recommendation")}</p>
        <span className="badge">{d.recommendation}</span>
        <p>
          <strong>{t("why")}:</strong> {d.reason}
        </p>
        <p>{d.sell_reason}</p>
        <Freshness data={d.freshness} />
      </div>
      {weather?.current && (
        <div className="card">
          <h2>{t("weather")}</h2>
          <p>
            {weather.current.conditions} · {weather.current.temperature_c}°C · rain {weather.current.rainfall_mm} mm · humidity {weather.current.humidity_percent}%
          </p>
          <Freshness data={weather.freshness} />
          <p className="muted">{t("forecast")}</p>
          {(weather.forecast || []).slice(0, 5).map((f) => (
            <div key={f.date}>
              {f.date}: {f.conditions}, {f.temperature_min_c}–{f.temperature_max_c}°C, rain {f.rainfall_mm} mm
              <span className="badge warn">forecast</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MarketsPage() {
  const { t } = useTranslation();
  const [crops, setCrops] = useState([]);
  const [cropId, setCropId] = useState("");
  const [rows, setRows] = useState([]);
  const [sort, setSort] = useState("profit");
  const [reason, setReason] = useState("");
  useEffect(() => {
    api("/api/crops").then((list) => {
      setCrops(list);
      if (list[0]) setCropId(String(list[0].id));
    });
  }, []);
  const load = async () => {
    const data = await api(`/api/market-recommendations?crop_id=${cropId}`);
    setRows(data.markets || []);
    setReason(data.reason || data.message || "");
  };
  const sorted = [...rows].sort((a, b) => {
    if (sort === "price") return (b.modal_price || 0) - (a.modal_price || 0);
    if (sort === "distance") return (a.distance_km || 99) - (b.distance_km || 99);
    if (sort === "transport") return (a.transport_cost || 0) - (b.transport_cost || 0);
    return (b.expected_net_profit || 0) - (a.expected_net_profit || 0);
  });
  return (
    <div className="card">
      <h2>{t("compare")}</h2>
      <label>Crop</label>
      <select value={cropId} onChange={(e) => setCropId(e.target.value)}>
        {crops.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name_en}
          </option>
        ))}
      </select>
      <button className="btn" onClick={load}>
        {t("compare")}
      </button>
      <div className="row" style={{ marginTop: 12 }}>
        {[
          ["profit", t("sortProfit")],
          ["price", t("sortPrice")],
          ["distance", t("sortDistance")],
          ["transport", t("sortTransport")],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`btn small${sort === key ? "" : " secondary"}`}
            onClick={() => setSort(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {reason && <p>{reason}</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t("market")}</th>
              <th>{t("price")}</th>
              <th>{t("distance")}</th>
              <th>{t("transport")}</th>
              <th>{t("costs")}</th>
              <th>{t("netProfit")}</th>
              <th>{t("risk")}</th>
              <th>{t("recommendation")}</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((m) => (
              <tr key={m.market_id}>
                <td>
                  {m.market}
                  <div className="muted">{m.district}</div>
                </td>
                <td>
                  {rupees(m.modal_price)}
                  <div className="muted">{m.freshness?.quality}</div>
                </td>
                <td>
                  {m.distance_km ? `${m.distance_km} km` : "—"}
                  <div className="muted">{m.distance_label}</div>
                </td>
                <td>{rupees(m.transport_cost)}</td>
                <td>{rupees(m.total_cost)}</td>
                <td>
                  {rupees(m.expected_net_profit)}
                  <div className="muted">
                    {m.area_hectares ? t("profitOnArea", { area: m.area_hectares, place: [m.farm_village, m.farm_district].filter(Boolean).join(", ") }) : ""}
                  </div>
                </td>
                <td>
                  <RiskBadge risk={m.risk} />
                </td>
                <td>{m.recommendation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CropsPage() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api("/api/crop-recommendations")
      .then(setData)
      .catch((e) => setErr(e.message));
  }, []);
  if (err) return <div className="error">{err}</div>;
  if (!data) return <p>Loading…</p>;
  return (
    <div>
      <div className="card">
        <h2>{t("crops")}</h2>
        <p className="muted">{data.method_note}</p>
        {data.message && <p>{data.message}</p>}
        {(data.crops || []).map((c) => (
          <div key={c.crop_id} className="card">
            <strong>{c.crop}</strong> · score {c.score}{" "}
            <RiskBadge risk={c.risk} />
            <div className="stat" style={{ fontSize: "1.2rem" }}>
              {rupees(c.expected_net_profit)}
            </div>
            <ProfitTerms
              area={c.area_hectares}
              village={c.farm_village}
              district={c.farm_district}
              yld={c.yield_quintal_per_hectare}
              qty={c.quantity_quintals}
              perHa={c.profit_per_hectare}
            />
            <p>{c.reason}</p>
            <p className="muted">
              {c.best_market} · {rupees(c.modal_price)} / quintal
            </p>
            <Freshness data={c.freshness} />
          </div>
        ))}
      </div>
    </div>
  );
}

function AdminPage({ me }) {
  const [jobs, setJobs] = useState([]);
  const [fails, setFails] = useState([]);
  const [transport, setTransport] = useState({ cost_per_km: 25, truck_capacity_quintals: 80, notes: "" });
  const [msg, setMsg] = useState("");
  const refresh = () => {
    api("/api/admin/sync-jobs").then(setJobs);
    api("/api/admin/import-failures").then(setFails);
    api("/api/admin/transport").then((t) => t && setTransport(t));
  };
  useEffect(() => {
    if (me?.role === "admin") refresh();
  }, [me]);
  if (me?.role !== "admin") return <div className="error">Administrator access required.</div>;
  const sync = async () => {
    const job = await api("/api/admin/sync/mandi", { method: "POST" });
    setMsg(`Sync ${job.status}: ${job.error_summary || `${job.records_ok} saved`}`);
    refresh();
  };
  const upload = async (e) => {
    const file = e.target.files[0];
    const fd = new FormData();
    fd.append("file", file);
    const job = await api("/api/admin/import/prices", { method: "POST", body: fd });
    setMsg(`Import ${job.status}: ${job.records_ok} ok, ${job.records_failed} failed`);
    refresh();
  };
  const saveT = async (e) => {
    e.preventDefault();
    await api("/api/admin/transport", { method: "PUT", body: JSON.stringify(transport) });
    setMsg("Transport settings saved.");
  };
  return (
    <div>
      {msg && <div className="ok">{msg}</div>}
      <div className="card">
        <h2>Government mandi sync</h2>
        <p className="muted">Uses data.gov.in AGMARKNET. Requires DATA_GOV_IN_API_KEY, or upload a CSV/Excel export.</p>
        <button className="btn" onClick={sync}>
          Fetch latest mandi prices
        </button>
        <label>Upload CSV / Excel</label>
        <input type="file" accept=".csv,.xlsx,.xls" onChange={upload} />
      </div>
      <form className="card" onSubmit={saveT}>
        <h2>Transport assumptions</h2>
        <label>Cost per km (₹)</label>
        <input type="number" value={transport.cost_per_km} onChange={(e) => setTransport({ ...transport, cost_per_km: Number(e.target.value) })} />
        <label>Truck capacity (quintals)</label>
        <input type="number" value={transport.truck_capacity_quintals} onChange={(e) => setTransport({ ...transport, truck_capacity_quintals: Number(e.target.value) })} />
        <button className="btn">Save</button>
      </form>
      <div className="card">
        <h2>Sync status</h2>
        {jobs.map((j) => (
          <p key={j.id}>
            {j.source} · {j.status} · ok {j.records_ok} · failed {j.records_failed} · {j.started_at}
            {j.error_summary ? ` · ${j.error_summary}` : ""}
          </p>
        ))}
      </div>
      <div className="card">
        <h2>Failed imports</h2>
        {fails.slice(0, 20).map((f) => (
          <p key={f.id} className="muted">
            {f.created_at}: {f.reason}
          </p>
        ))}
      </div>
    </div>
  );
}

function Shell({ me, onLogout, children }) {
  const { t } = useTranslation();
  return (
    <div className="page">
      <div className="hero">
        <div className="topbar">
          <h1>{t("appName")}</h1>
          <div className="desktop-nav">
            <NavLink to="/">{t("dashboard")}</NavLink>
            <NavLink to="/farm">{t("myFarm")}</NavLink>
            <NavLink to="/markets">{t("markets")}</NavLink>
            <NavLink to="/crops">{t("crops")}</NavLink>
            {me?.role === "admin" && <NavLink to="/admin">{t("admin")}</NavLink>}
            <button type="button" className="logout-btn" onClick={onLogout}>
              {t("logout")}
            </button>
          </div>
        </div>
        <div className="hero-user">
          <p style={{ margin: 0 }}>{me?.full_name}</p>
          <button type="button" className="logout-btn" onClick={onLogout}>
            {t("logout")}
          </button>
        </div>
      </div>
      <LangSwitch />
      {children}
      <nav className="nav">
        <NavLink to="/" end>
          {t("dashboard")}
        </NavLink>
        <NavLink to="/farm">{t("myFarm")}</NavLink>
        <NavLink to="/markets">{t("markets")}</NavLink>
        <NavLink to="/crops">{t("crops")}</NavLink>
        {me?.role === "admin" && <NavLink to="/admin">{t("admin")}</NavLink>}
        <button type="button" onClick={onLogout}>
          {t("logout")}
        </button>
      </nav>
    </div>
  );
}

export default function App() {
  const [me, setMe] = useState(null);
  const [ready, setReady] = useState(false);
  const nav = useNavigate();

  const loadMe = async () => {
    if (!getToken()) {
      setMe(null);
      setReady(true);
      return;
    }
    try {
      setMe(await api("/api/auth/me"));
    } catch {
      clearToken();
      setMe(null);
    }
    setReady(true);
  };

  useEffect(() => {
    loadMe();
  }, []);

  const onAuth = (data) => {
    setToken(data.access_token);
    if (data.language) {
      localStorage.setItem("lang", data.language);
    }
    loadMe().then(() => nav("/"));
  };
  const onLogout = (e) => {
    e?.preventDefault?.();
    clearToken();
    setMe(null);
    nav("/login", { replace: true });
  };

  if (!ready) return <p style={{ padding: 24 }}>Loading…</p>;

  return (
    <Routes>
      <Route path="/login" element={me ? <Navigate to="/" /> : <Login onAuth={onAuth} />} />
      <Route path="/register" element={me ? <Navigate to="/" /> : <Register onAuth={onAuth} />} />
      <Route
        path="/*"
        element={
          me ? (
            <Shell me={me} onLogout={onLogout}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/farm" element={<FarmPage />} />
                <Route path="/markets" element={<MarketsPage />} />
                <Route path="/crops" element={<CropsPage />} />
                <Route path="/admin" element={<AdminPage me={me} />} />
              </Routes>
            </Shell>
          ) : (
            <Navigate to="/login" />
          )
        }
      />
    </Routes>
  );
}
