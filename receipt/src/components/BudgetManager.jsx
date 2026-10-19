import React, { useState } from "react";
import { ProgressBar } from "./Charts";
import { documentService } from "../utils/api";
import { formatMoney } from "../utils/format";
import { currentMonthKey, monthLabel, periodPosition, periodSpend } from "../utils/budgeting";

/* What each status reads as; the colour never says it alone */
export const STATUS = {
  over: { tone: "critical", icon: "✕", label: "Over budget" },
  near: { tone: "serious", icon: "!", label: "Close to the limit" },
  pace: { tone: "warning", icon: "↗", label: "On pace to go over" },
  trend: { tone: "warning", icon: "↗", label: "Trend takes it over" },
  ok: { tone: "good", icon: "✓", label: "On track" },
  inactive: { tone: "good", icon: "–", label: "Not active this month" },
  none: { tone: "good", icon: "–", label: "No target" },
};

const MODES = [
  { key: "forever", label: "Every month, until changed" },
  { key: "one", label: "For 1 month" },
  { key: "many", label: "For a number of months" },
];

const blankForm = () => ({ scope: "overall", amount: "", mode: "forever", months: "3", start: currentMonthKey() });

const formFor = (budget) => ({
  scope: budget.tag || "overall",
  amount: Number(budget.monthly_limit).toFixed(2),
  mode: budget.months == null ? "forever" : budget.months === 1 ? "one" : "many",
  months: String(budget.months && budget.months > 1 ? budget.months : 3),
  start: budget.start_month.slice(0, 7),
});

const describePeriod = (budget) => {
  const from = monthLabel(budget.start_month.slice(0, 7), true);
  if (budget.months == null) return `every month from ${from}`;
  return budget.months === 1 ? `${from} only` : `${budget.months} months from ${from}`;
};

/**
 * Targets for what is spent each month: one for all spending and one for any
 * number of tags, each for a month, a number of months, or until changed. Each
 * is shown against what has been spent this month (and, for a target of
 * several months, over its whole period), with where the month is heading.
 * They are added, changed and removed here.
 */
const BudgetManager = ({ budgets, setBudgets, tags, stats, totals }) => {
  const [form, setForm] = useState(blankForm);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const nowKey = currentMonthKey();

  const statFor = (budget) => stats.find((s) => s.scope.budget?.id === budget.id);
  const ordered = [...budgets].sort((a, b) => (a.tag ? 1 : 0) - (b.tag ? 1 : 0) || a.tag_name.localeCompare(b.tag_name));
  const takenScopes = new Set(budgets.filter((b) => b.id !== editingId).map((b) => b.tag || "overall"));
  const scopeOptions = [{ id: "overall", name: "Overall spending" }, ...tags].filter((o) => !takenScopes.has(o.id));
  const months = form.mode === "one" ? 1 : form.mode === "many" ? Number(form.months) : null;
  const isValid = Number(form.amount) > 0 && form.start && (form.mode !== "many" || (Number.isInteger(months) && months >= 2 && months <= 120));

  const startEditing = (budget) => {
    setEditingId(budget.id);
    setForm(formFor(budget));
    setError(null);
  };
  const reset = () => {
    setEditingId(null);
    setForm(blankForm());
    setError(null);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!isValid) return;
    setSaving(true);
    setError(null);
    const body = { monthly_limit: Number(form.amount).toFixed(2), start_month: `${form.start}-01`, months };
    try {
      if (editingId) {
        const updated = await documentService.updateBudget(editingId, body);
        setBudgets((prev) => prev.map((b) => (b.id === editingId ? updated : b)));
      } else {
        const created = await documentService.createBudget({ tag: form.scope === "overall" ? null : form.scope, ...body });
        setBudgets((prev) => [...prev, created]);
      }
      reset();
    } catch (err) {
      setError(err.serverMessage || "That could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (budget) => {
    setSaving(true);
    setError(null);
    try {
      await documentService.deleteBudget(budget.id);
      setBudgets((prev) => prev.filter((b) => b.id !== budget.id));
      if (editingId === budget.id) reset();
    } catch (err) {
      setError(err.serverMessage || "That could not be removed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="chart-card chart-card-wide">
      <div className="chart-card-head">
        <h4>Targets for {monthLabel(nowKey, true)}</h4>
        <span className="spending-hint">A target counts spending under its tag and every tag beneath it.</span>
      </div>

      {error && <p className="spending-warning budget-error">{error}</p>}

      {ordered.length === 0 ? (
        <p className="dashboard-panel-empty">Set a monthly target for all your spending, or for any tags, to track spending against it.</p>
      ) : (
        <ul className="budget-list">
          {ordered.map((b) => {
            const stat = statFor(b);
            const status = STATUS[stat?.status || "none"];
            const limit = Math.round(Number(b.monthly_limit) * 100);
            const spent = stat?.currentCents || 0;
            const position = periodPosition(b, nowKey);
            const period = b.months != null && b.months > 1 && stat?.active ? periodSpend(b, totals.get(stat.scope.id), nowKey) : null;
            return (
              <li key={b.id}>
                <div className="budget-row">
                  <span className="budget-name">{b.tag_name}</span>
                  <span className={`budget-status is-${status.tone}`}>
                    <span aria-hidden="true">{status.icon}</span> {status.label}
                  </span>
                  <span className="budget-figures">
                    {formatMoney(spent)} of {formatMoney(limit)}
                  </span>
                </div>
                <ProgressBar share={limit ? spent / limit : 0} tone={status.tone} marker={limit && stat?.active ? stat.projectedCents / limit : null} />
                <div className="budget-row budget-detail">
                  <span>
                    {limit - spent >= 0 ? `${formatMoney(limit - spent)} left` : `${formatMoney(spent - limit)} over`}
                    {stat?.active && ` · expected to reach ${formatMoney(stat.projectedCents)}`} · {describePeriod(b)}
                    {position && stat?.active && ` · month ${position.month} of ${position.of}`}
                    {period && ` · ${formatMoney(period.spent)} of ${formatMoney(period.allowed)} over the whole period`}
                  </span>
                  <span className="budget-actions">
                    <button type="button" className="link-button" onClick={() => startEditing(b)}>
                      Change
                    </button>
                    <button type="button" className="link-button" disabled={saving} onClick={() => remove(b)}>
                      Remove
                    </button>
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {(editingId || scopeOptions.length > 0) && (
        <form className="budget-form budget-form-wide" onSubmit={submit}>
          <label>
            <span className="spending-label">Applies to</span>
            <select
              className="analytics-select"
              value={form.scope}
              disabled={!!editingId}
              onChange={(e) => setForm({ ...form, scope: e.target.value })}
              aria-label="What the target applies to"
            >
              {(editingId ? [{ id: form.scope, name: ordered.find((b) => b.id === editingId)?.tag_name }] : scopeOptions).map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="spending-label">Target a month</span>
            <input
              className="budget-input"
              type="number"
              min="0.01"
              step="0.01"
              placeholder="Amount"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
              aria-label="Target a month"
            />
          </label>
          <label>
            <span className="spending-label">For</span>
            <select className="analytics-select" value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })} aria-label="How long it applies">
              {MODES.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          {form.mode === "many" && (
            <label>
              <span className="spending-label">Months</span>
              <input
                className="budget-input budget-input-narrow"
                type="number"
                min="2"
                max="120"
                step="1"
                value={form.months}
                onChange={(e) => setForm({ ...form, months: e.target.value })}
                aria-label="Number of months"
              />
            </label>
          )}
          <label>
            <span className="spending-label">Starting</span>
            <input className="budget-input" type="month" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} aria-label="First month" />
          </label>
          <button type="submit" className="spending-pill is-on" disabled={saving || !isValid}>
            {editingId ? "Save changes" : "Add target"}
          </button>
          {editingId && (
            <button type="button" className="spending-pill" onClick={reset}>
              Cancel
            </button>
          )}
        </form>
      )}
    </div>
  );
};

export default BudgetManager;
