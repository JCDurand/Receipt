import React from "react";

/* The time period a page looks at: the presets (1 month, 3 months, ...) and a
   custom range. `state` is what usePeriod returns. */
const PeriodFilter = ({ state, label = "Period" }) => {
  const { period, presets, choosePreset, chooseDates } = state;
  const isBackwards = period.from !== "" && period.to !== "" && period.from > period.to;
  return (
    <div className="spending-group">
      <span className="spending-label">{label}</span>
      <div className="spending-presets" role="group" aria-label={label}>
        {presets.map((p) => (
          <button
            key={p.key}
            type="button"
            className={`spending-pill${period.key === p.key ? " is-on" : ""}`}
            aria-pressed={period.key === p.key}
            onClick={() => choosePreset(p.key)}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="spending-dates">
        <label>
          From
          <input
            type="date"
            value={period.from}
            max={period.to || undefined}
            onChange={(e) => chooseDates({ from: e.target.value })}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={period.to}
            min={period.from || undefined}
            onChange={(e) => chooseDates({ to: e.target.value })}
          />
        </label>
      </div>
      {isBackwards && <p className="spending-warning">The start date is after the end date.</p>}
    </div>
  );
};

export default PeriodFilter;

/* The period in words, for a line saying what the filters are set to */
export const describePeriod = ({ period, presets }) => {
  const preset = presets.find((p) => p.key === period.key);
  if (preset && preset.key === "all") return "All time";
  if (preset) return preset.label;
  if (!period.from && !period.to) return "All time";
  return `${period.from || "start"} to ${period.to || "today"}`;
};
