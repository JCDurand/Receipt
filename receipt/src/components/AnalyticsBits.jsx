import React from "react";

/* A row of buttons, one of which is on */
export const Pills = ({ options, value, onChange, label }) => (
  <div className="spending-presets" role="group" aria-label={label}>
    {options.map((o) => (
      <button
        key={o.key}
        type="button"
        className={`spending-pill${value === o.key ? " is-on" : ""}`}
        aria-pressed={value === o.key}
        onClick={() => onChange(o.key)}
      >
        {o.label}
      </button>
    ))}
  </div>
);

/* Buttons which each switch one of several things on or off */
export const MultiPills = ({ options, chosen, onToggle, label, empty }) =>
  options.length === 0 ? (
    <p className="spending-hint">{empty}</p>
  ) : (
    <div className="spending-presets" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          className={`spending-pill${chosen.includes(o.id) ? " is-on" : ""}`}
          aria-pressed={chosen.includes(o.id)}
          onClick={() => onToggle(o.id)}
        >
          {o.name}
        </button>
      ))}
    </div>
  );

/* A statistic. `delta` is the change on the period before as a fraction, and
   `upIsGood` says which way is better, for its colour; the arrow and the
   words carry it as well. */
export const Stat = ({ label, value, detail, tone, delta, upIsGood = false }) => (
  <div className="stat-tile">
    <span className="stat-label">{label}</span>
    <span className={`stat-value${tone ? ` is-${tone}` : ""}`}>{value}</span>
    {delta != null && (
      <span className={`stat-delta ${delta === 0 ? "" : delta > 0 === upIsGood ? "is-good" : "is-bad"}`}>
        <span aria-hidden="true">{delta > 0 ? "▲" : delta < 0 ? "▼" : "■"}</span>{" "}
        {delta === 0 ? "No change" : `${Math.abs(Math.round(delta * 100))}% ${delta > 0 ? "more" : "less"}`} than the period before
      </span>
    )}
    {detail && <span className="stat-detail">{detail}</span>}
  </div>
);

/* Why there is nothing to chart, and perhaps a button which changes that */
export const Empty = ({ message, action }) => (
  <div className="chart-empty">
    <p>{message}</p>
    {action && (
      <button type="button" className="spending-pill is-on" onClick={action.run}>
        {action.label}
      </button>
    )}
  </div>
);
