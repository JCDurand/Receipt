import React from "react";
import { useSearchParams } from "react-router-dom";
import "../styles/Tabs.css";

/* Which tab of a page is showing, kept in the address (?tab=...) so that reloading
   or sharing the link comes back to it. The first tab when there is none. */
export const useTabs = (tabs) => {
  const [params, setParams] = useSearchParams();
  const wanted = params.get("tab");
  const active = tabs.some((t) => t.key === wanted) ? wanted : tabs[0].key;
  const select = (key) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("tab", key);
        return next;
      },
      { replace: true }
    );
  return [active, select];
};

/* The row of tabs across the top of a page's content. `tabs` are
   [{ key, label, badge? }]; `actions` is what goes at the right end of the row. */
export const Tabs = ({ tabs, active, onSelect, actions, label = "Sections" }) => {
  const move = (evt, index) => {
    const step = evt.key === "ArrowRight" ? 1 : evt.key === "ArrowLeft" ? -1 : 0;
    if (!step && evt.key !== "Home" && evt.key !== "End") return;
    evt.preventDefault();
    const to = evt.key === "Home" ? 0 : evt.key === "End" ? tabs.length - 1 : (index + step + tabs.length) % tabs.length;
    onSelect(tabs[to].key);
    document.getElementById(`tab-${tabs[to].key}`)?.focus();
  };

  return (
    <div className="tabs-bar">
      <div className="tabs-list" role="tablist" aria-label={label}>
        {tabs.map((tab, i) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={`tab-${tab.key}`}
            aria-selected={active === tab.key}
            aria-controls={`panel-${tab.key}`}
            tabIndex={active === tab.key ? 0 : -1}
            className={`tabs-tab${active === tab.key ? " is-active" : ""}`}
            onClick={() => onSelect(tab.key)}
            onKeyDown={(evt) => move(evt, i)}
          >
            {tab.label}
            {tab.badge != null && tab.badge !== 0 && <span className="tabs-badge">{tab.badge}</span>}
          </button>
        ))}
      </div>
      {actions && <div className="tabs-actions">{actions}</div>}
    </div>
  );
};

export const TabPanel = ({ id, children }) => (
  <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className="tab-panel">
    {children}
  </div>
);

/* The button at the right of the tabs which opens and closes a page's filters,
   with a line saying what they are set to while they are closed */
export const FilterToggle = ({ isOpen, onToggle, summary }) => (
  <button type="button" className={`tabs-filter${isOpen ? " is-open" : ""}`} aria-expanded={isOpen} onClick={onToggle}>
    <span className="tabs-filter-label">Filters</span>
    {summary && <span className="tabs-filter-summary">{summary}</span>}
    <span aria-hidden="true">{isOpen ? "▴" : "▾"}</span>
  </button>
);
