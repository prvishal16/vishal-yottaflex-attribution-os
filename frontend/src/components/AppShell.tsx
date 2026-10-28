import {
  Activity,
  ChevronDown,
  Database,
  Gauge,
  Megaphone,
  Menu,
  Route,
  ShieldAlert,
  Sparkles,
  X,
} from "lucide-react";
import { Suspense, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { api } from "../api/client";
import { LoadingState } from "./Primitives";
import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../hooks/useRunContext";
import { classNames, truncateHash } from "../utils/format";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: Gauge, end: true },
  { to: "/campaigns", label: "Campaigns", icon: Megaphone, end: false },
  { to: "/journeys", label: "Journey explorer", icon: Route, end: false },
  { to: "/data-quality", label: "Data quality", icon: ShieldAlert, end: false },
  { to: "/runs", label: "Runs & reproducibility", icon: Database, end: false },
];

export function AppShell() {
  const location = useLocation();
  const {
    runs,
    activeRunId,
    effectiveRunId,
    loading,
    error,
    selectRun,
  } = useRunContext();
  const health = useAsync(api.health, []);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const selectedRun = runs.find((run) => run.run_id === effectiveRunId);
  const pageTitle =
    location.pathname === "/"
      ? "Overview"
      : location.pathname.startsWith("/campaigns/")
        ? "Campaign detail"
        : NAV_ITEMS.find((item) => location.pathname.startsWith(item.to) && item.to !== "/")
            ?.label ?? "Overview";
  const isHealthy = health.data?.status === "ok" && !health.error;

  return (
    <div className="app-shell">
      <aside className={classNames("sidebar", mobileOpen && "is-open")}>
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <svg viewBox="0 0 34 34" fill="none">
              <path d="M8 9.5 17 17l9-7.5" stroke="currentColor" strokeWidth="1.8" />
              <path d="M17 17v9" stroke="currentColor" strokeWidth="1.8" />
              <circle cx="8" cy="9.5" r="2.4" fill="currentColor" />
              <circle cx="26" cy="9.5" r="2.4" fill="currentColor" />
              <circle cx="17" cy="26" r="2.4" fill="currentColor" />
            </svg>
          </span>
          <span className="brand__text">
            <strong>YottaFlex</strong>
            <span>Attribution OS</span>
          </span>
          <button
            className="sidebar__close icon-button"
            type="button"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        <div className="sidebar__section-label">Workspace</div>
        <nav className="nav" aria-label="Primary navigation">
          {NAV_ITEMS.slice(0, 3).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => classNames("nav__item", isActive && "is-active")}
            >
              <item.icon size={17} strokeWidth={1.8} />
              <span>{item.label}</span>
              <span className="nav__indicator" aria-hidden="true" />
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__section-label">Trust layer</div>
        <nav className="nav" aria-label="Trust navigation">
          {NAV_ITEMS.slice(3).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => classNames("nav__item", isActive && "is-active")}
            >
              <item.icon size={17} strokeWidth={1.8} />
              <span>{item.label}</span>
              <span className="nav__indicator" aria-hidden="true" />
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__spacer" />

        <div className="dataset-card">
          <div className="dataset-card__head">
            <span className="eyebrow">Active dataset</span>
            <span className={classNames("status-dot", isHealthy ? "is-ok" : "is-error")} />
          </div>
          <code>{effectiveRunId ?? "No dataset"}</code>
          <div className="dataset-card__meta">
            <span>{selectedRun?.profile ?? "—"} profile</span>
            <span>seed {selectedRun?.seed ?? "—"}</span>
          </div>
          <div className="dataset-card__hash" title={selectedRun?.combined_hash}>
            <Sparkles size={11} />
            {truncateHash(selectedRun?.combined_hash, 16)}
          </div>
        </div>

        <div className="sidebar__footer">
          <Activity size={13} />
          <span>Deterministic by construction</span>
        </div>
      </aside>

      {mobileOpen ? (
        <button
          className="sidebar-scrim"
          type="button"
          aria-label="Close navigation overlay"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}

      <div className="app-main">
        <header className="topbar">
          <div className="topbar__left">
            <button
              className="icon-button topbar__menu"
              type="button"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={19} />
            </button>
            <div className="crumbs">
              <span>Console</span>
              <span className="crumbs__slash">/</span>
              <strong>{pageTitle}</strong>
            </div>
          </div>

          <div className="topbar__actions">
            <span
              className={classNames(
                "connection",
                isHealthy ? "connection--ok" : health.loading ? "" : "connection--error",
              )}
              title={health.error?.message ?? "FastAPI analytics service"}
            >
              <span className="status-dot" />
              {health.loading ? "Connecting" : isHealthy ? "API live" : "API offline"}
            </span>
            <label className="run-select">
              <Database size={14} />
              <span className="run-select__label">Dataset</span>
              <select
                value={effectiveRunId ?? ""}
                onChange={(event) => {
                  const next = event.target.value;
                  selectRun(next === activeRunId ? null : next);
                }}
                disabled={loading || runs.length === 0}
                aria-label="Select dataset run"
              >
                {!effectiveRunId ? <option value="">No run</option> : null}
                {runs.map((run) => (
                  <option key={run.run_id} value={run.run_id}>
                    {run.run_id}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="run-select__chevron" />
            </label>
          </div>
        </header>

        {error ? <div className="global-banner">{error}</div> : null}

        <main className="page">
          <Suspense
            fallback={
              <div className="page-stack">
                <LoadingState rows={8} />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </main>

        <footer className="app-footer">
          <span>Synthetic data only. Deliberate anomaly fixtures are labelled separately from detection.</span>
          <span className="app-footer__build">YottaFlex FDE · v1.0</span>
        </footer>
      </div>
    </div>
  );
}
