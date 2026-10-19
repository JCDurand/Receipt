import React, { useMemo } from "react";
import { MultiLineChart } from "./Charts";
import { Empty, Pills } from "./AnalyticsBits";
import { STATUS } from "./BudgetManager";
import { formatMoney } from "../utils/format";
import { addMonths, currentMonthKey, fitWord, MIN_HISTORY, monthLabel } from "../utils/budgeting";

const WINDOWS = [
  { key: "3", label: "3 months" },
  { key: "6", label: "6 months" },
  { key: "12", label: "12 months" },
];

const REASONS = {
  over: (s) => `${formatMoney(s.currentCents)} has been spent this month, past the ${formatMoney(s.limitCents)} target.`,
  pace: (s) => `This month is expected to reach ${formatMoney(s.projectedCents)}, past the target.`,
  "trend-up": (s) =>
    `Spending has been rising by about ${formatMoney(Math.round(Math.abs(s.reg.slope)))} a month (a ${fitWord(s.reg.r2)} trend), taking next month to ${formatMoney(s.forecastNext)}.`,
  "trend-down": (s) =>
    `Spending is falling by about ${formatMoney(Math.round(Math.abs(s.reg.slope)))} a month, but next month is still forecast at ${formatMoney(s.forecastNext)}, past the target.`,
  average: (s) => `The average over the last ${s.reg.n} months, ${formatMoney(Math.round(s.reg.mean))}, is above the target.`,
};

const percent = (fraction) => `${fraction > 0 ? "+" : ""}${(fraction * 100).toFixed(1)}%`;

/* ▲ up, ▼ down, ■ level: money going up is worse, so up is red */
const Arrow = ({ value }) => (
  <span className={value > 0 ? "is-neg" : value < 0 ? "is-pos" : ""}>
    <span aria-hidden="true">{value > 0 ? "▲" : value < 0 ? "▼" : "■"}</span> {value > 0 ? "up" : value < 0 ? "down" : "level"}
  </span>
);

/**
 * What the spending is doing against the targets: where it must come down,
 * a chart of a month-by-month figures for one tag with its trend and target,
 * and the statistics of each tag's trend over a number of months.
 */
const BudgetInsights = ({ part, stats, totals, windowMonths, onWindow, focusId, onFocus, monthKey, onMonth, monthKeys }) => {
  const nowKey = currentMonthKey();
  const nextKey = addMonths(nowKey, 1);
  const flagged = stats.filter((s) => s.reduceCents > 0);
  const budgeted = stats.filter((s) => s.scope.budget && s.active);
  const focus = stats.find((s) => s.scope.id === focusId) || stats[0];
  const choices = stats.filter((s) => s.scope.id === "overall" || s.history.length > 0 || s.scope.budget);

  const chart = useMemo(() => {
    if (!focus || focus.history.length === 0) return null;
    const keys = [...focus.history, nowKey, nextKey];
    const labelOf = (key) => (key === nextKey ? `${monthLabel(key)} (forecast)` : key === nowKey ? `${monthLabel(key)} (so far)` : monthLabel(key));
    const point = (key, cents) => ({ key, label: labelOf(key), short: monthLabel(key).split(" ")[0], cents });
    const months = totals.get(focus.scope.id);
    const series = [
      { id: "spent", name: "Spent", color: "#2a78d6", points: keys.map((k) => point(k, focus.history.includes(k) ? months.get(k) || 0 : null)) },
      { id: "now", name: "This month so far", color: "#eb6834", dots: true, dashed: true, points: keys.map((k) => point(k, k === nowKey ? focus.currentCents : null)) },
    ];
    if (focus.reg) {
      series.push({
        id: "trend",
        name: "Trend",
        color: "#4a3aa7",
        dashed: true,
        points: keys.map((k, i) => point(k, Math.max(0, Math.round(focus.reg.at(i))))),
      });
    }
    const levels = focus.scope.budget ? [{ cents: focus.limitCents, label: "Monthly target", color: "#d03b3b" }] : [];
    return { series, levels };
  }, [focus, totals, nowKey, nextKey]);

  const rows = stats.filter((s) => s.scope.budget || s.history.length > 0).sort((a, b) => (b.scope.budget ? 1 : 0) - (a.scope.budget ? 1 : 0) || b.currentCents - a.currentCents);
  const previousKey = addMonths(monthKey, -1);

  return (
    <>
      {/* Where spending must come down */}
      {part === "actions" && (
      <div className="chart-card chart-card-wide">
        <div className="chart-card-head">
          <h4>What to do</h4>
        </div>
        {budgeted.length === 0 ? (
          <p className="dashboard-panel-empty">Add a target below and its trend is checked against it here.</p>
        ) : flagged.length === 0 ? (
          <p className="budget-ok">
            <span aria-hidden="true">✓</span> Nothing needs cutting: spending and its trend are within every target that applies this month.
            {budgeted.some((s) => !s.reg) && ` (A trend needs at least ${MIN_HISTORY} completed months of spending, which some do not have yet.)`}
          </p>
        ) : (
          <ul className="budget-alerts">
            {flagged.map((s) => (
              <li key={s.scope.id}>
                <strong>
                  <span aria-hidden="true">!</span> Reduce {s.scope.id === "overall" ? "overall" : s.scope.name} spending by about{" "}
                  {formatMoney(s.reduceCents)} a month
                </strong>
                <span className="spending-hint">
                  {" "}
                  to stay within {formatMoney(s.limitCents)}
                  {s.reg && s.forecastNext ? ` (${Math.round((s.reduceCents / s.forecastNext) * 100)}% less than next month's forecast)` : ""}.
                </span>
                <ul>
                  {s.reasons.map((code) => (
                    <li key={code}>{REASONS[code](s)}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>
      )}

      {/* One tag's months, its trend and its target */}
      {part === "chart" && (
      <div className="chart-card chart-card-wide">
        <div className="chart-card-head">
          <h4>Spending by month</h4>
          <div className="budget-controls">
            <select className="analytics-select" value={focus?.scope.id} onChange={(e) => onFocus(e.target.value)} aria-label="Tag to chart">
              {choices.map((s) => (
                <option key={s.scope.id} value={s.scope.id}>
                  {s.scope.name}
                </option>
              ))}
            </select>
            <Pills options={WINDOWS} value={String(windowMonths)} onChange={(k) => onWindow(Number(k))} label="Months to look at" />
          </div>
        </div>
        {chart ? (
          <MultiLineChart series={chart.series} levels={chart.levels} label={`${focus.scope.name} spending by month`} />
        ) : (
          <Empty message={`No ${focus?.scope.name || ""} spending in the last ${windowMonths} months.`.replace("  ", " ")} />
        )}
        <p className="spending-note">
          {focus?.reg
            ? `The trend is a straight line fitted through the ${focus.reg.n} completed months. It is ${fitWord(focus.reg.r2)} (R² ${focus.reg.r2.toFixed(2)}); the last point is the forecast for next month.`
            : `A trend needs at least ${MIN_HISTORY} completed months of spending.`}
        </p>
      </div>
      )}

      {/* The statistics, tag by tag */}
      {part === "stats" && (
      <div className="chart-card chart-card-wide">
        <div className="chart-card-head">
          <h4>How spending is changing</h4>
          <label className="group-modal-sort">
            <span className="spending-label">Month</span>
            <select className="analytics-select" value={monthKey} onChange={(e) => onMonth(e.target.value)} aria-label="Month to compare">
              {[...monthKeys].reverse().map((k) => (
                <option key={k} value={k}>
                  {monthLabel(k, true)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {rows.length === 0 ? (
          <p className="dashboard-panel-empty">There is no spending in these months yet.</p>
        ) : (
          <div className="recurring-scroll">
            <table className="recurring-table">
              <thead>
                <tr>
                  <th>Tag</th>
                  <th className="num">{monthLabel(monthKey)}</th>
                  <th className="num">Than {monthLabel(previousKey)}</th>
                  <th className="num">Average a month</th>
                  <th className="num">Trend a month</th>
                  <th className="num">Fit (R²)</th>
                  <th className="num">Forecast next month</th>
                  <th className="num">Target</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => {
                  const months = totals.get(s.scope.id);
                  const inMonth = months.get(monthKey) || 0;
                  const before = months.get(previousKey);
                  const status = STATUS[s.status];
                  return (
                    <tr key={s.scope.id}>
                      <td>{s.scope.name}</td>
                      <td className="num">{formatMoney(inMonth)}</td>
                      <td className="num">
                        {before ? (
                          <>
                            {percent((inMonth - before) / before)} <Arrow value={inMonth - before} />
                          </>
                        ) : (
                          "-"
                        )}
                      </td>
                      <td className="num">{s.reg ? formatMoney(Math.round(s.reg.mean)) : "-"}</td>
                      <td className="num">
                        {s.reg ? (
                          <>
                            {formatMoney(Math.round(s.reg.slope))}
                            {s.changePct != null && <span className="spending-hint"> ({percent(s.changePct)})</span>}{" "}
                            <Arrow value={Math.round(s.reg.slope)} />
                          </>
                        ) : (
                          <span className="spending-hint">Not enough months</span>
                        )}
                      </td>
                      <td className="num">{s.reg ? `${s.reg.r2.toFixed(2)} · ${fitWord(s.reg.r2)}` : "-"}</td>
                      <td className="num">{s.forecastNext != null ? formatMoney(s.forecastNext) : "-"}</td>
                      <td className="num">{s.scope.budget ? formatMoney(s.limitCents) : "-"}</td>
                      <td>
                        <span className={`budget-status is-${status.tone}`}>
                          <span aria-hidden="true">{status.icon}</span> {status.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="spending-note">
          Trend and forecast come from the {windowMonths} completed months before this one (from a tag's first spending). A tag's figures include the tags beneath it.
        </p>
      </div>
      )}
    </>
  );
};

export default BudgetInsights;
