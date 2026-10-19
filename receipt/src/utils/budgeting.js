/* Budgets against spending, month by month, and where the spending is heading:
   a straight-line (least squares) fit through each month's spending, which says
   which way it is moving, how fast, and what the coming months will be at that
   rate. Money is whole cents. */
import { spendingLines, spentCents, tagIndex, toCents } from "./spending";
import { withSubtags } from "./analytics";

const pad = (n) => String(n).padStart(2, "0");

/* ---- Months, as "YYYY-MM" ---- */

export const monthKeyOf = (iso) => iso.slice(0, 7);

export const currentMonthKey = (today = new Date()) => `${today.getFullYear()}-${pad(today.getMonth() + 1)}`;

export const addMonths = (key, count) => {
  const [y, m] = key.split("-").map(Number);
  const d = new Date(y, m - 1 + count, 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
};

export const monthsBetween = (from, to) => {
  const [fy, fm] = from.split("-").map(Number);
  const [ty, tm] = to.split("-").map(Number);
  return (ty - fy) * 12 + (tm - fm);
};

export const monthLabel = (key, long = false) => {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-ZA", { month: long ? "long" : "short", year: "numeric" });
};

/* The `count` months up to and including `endKey`, oldest first */
export const monthRange = (endKey, count) => Array.from({ length: count }, (_, i) => addMonths(endKey, i - count + 1));

/* ---- Budgets ---- */

/* Whether the budget applies in the month: from its first month, for its
   number of months (for good, when it has none) */
export const isActiveIn = (budget, key) => {
  const start = budget.start_month.slice(0, 7);
  if (key < start) return false;
  return budget.months == null || key < addMonths(start, budget.months);
};

/* Where a budget is in its period: "Month 2 of 3", or null when it has no end */
export const periodPosition = (budget, key) => {
  if (budget.months == null) return null;
  const at = monthsBetween(budget.start_month.slice(0, 7), key) + 1;
  return { month: at, of: budget.months };
};

/* ---- Monthly totals ---- */

/**
 * What was spent each month under each scope. A scope is { id, tagIds } where
 * tagIds are the tags it counts (null for all spending): a line item counts
 * once towards a scope, however many of its tags are in it. Returns
 * Map(scopeId -> Map(monthKey -> cents)).
 */
export const monthlyTotals = (lines, scopes, monthKeys) => {
  const wanted = new Set(monthKeys);
  const tagsOf = tagIndex(lines);
  const totals = new Map(scopes.map((s) => [s.id, new Map()]));
  const scopeSets = scopes.map((s) => ({ ...s, set: s.tagIds ? new Set(s.tagIds) : null }));

  for (const line of spendingLines(lines)) {
    const key = monthKeyOf(line.date);
    if (!wanted.has(key)) continue;
    const cents = spentCents(line);
    const lineTags = tagsOf(line);
    for (const scope of scopeSets) {
      if (scope.set && !lineTags.some((t) => scope.set.has(t.id))) continue;
      const months = totals.get(scope.id);
      months.set(key, (months.get(key) || 0) + cents);
    }
  }
  return totals;
};

/* The scopes to chart: all spending, and each tag (with the tags beneath it) */
export const buildScopes = (budgets, tags) => {
  const overall = budgets.find((b) => !b.tag) || null;
  return [
    { id: "overall", name: "Overall spending", tagIds: null, budget: overall },
    ...tags.map((tag) => ({
      id: tag.id,
      name: tag.name,
      tagIds: withSubtags([tag.id], tags),
      budget: budgets.find((b) => b.tag === tag.id) || null,
    })),
  ];
};

/* ---- Regression ---- */

/* A straight line through the values (taken at 0, 1, 2, ...) by least squares:
   { n, mean, slope, intercept, r2, at(i) }. `r2` is how much of the ups and
   downs the line explains, from 0 to 1. */
export const regress = (values) => {
  const n = values.length;
  const mx = (n - 1) / 2;
  const my = values.reduce((s, v) => s + v, 0) / n;
  let sxx = 0;
  let sxy = 0;
  let syy = 0;
  values.forEach((v, i) => {
    sxx += (i - mx) ** 2;
    sxy += (i - mx) * (v - my);
    syy += (v - my) ** 2;
  });
  const slope = sxx === 0 ? 0 : sxy / sxx;
  const intercept = my - slope * mx;
  const r2 = syy === 0 ? 1 : (sxy * sxy) / (sxx * syy);
  return { n, mean: my, slope, intercept, r2, at: (i) => intercept + slope * i };
};

/* How trustworthy the line is, in words */
export const fitWord = (r2) => (r2 >= 0.7 ? "strong" : r2 >= 0.3 ? "moderate" : "weak");

/* The fewest completed months a trend is drawn from */
export const MIN_HISTORY = 3;

/**
 * Where each scope's spending stands and is heading.
 *   monthKeys  the completed months to fit (oldest first); months before a
 *              scope's first spending are left out, not counted as nothing
 *   today      for the month in progress
 * Returns one object per scope:
 *   { scope, values, history, reg, forecastCurrent, forecastNext, changePct,
 *     currentCents, paceCents, limitCents, active, status, reduceCents, reasons }
 * `status` is "over", "near" (80% used), "pace" (on pace to go over), "trend"
 * (the trend takes it over next month), "ok", "none" (no budget) or "inactive"
 * (a budget which does not apply this month). `reduceCents` is how much a month
 * would have to come down by to stay within the limit, 0 when it need not, and
 * `reasons` says what the evidence is: any of "over" (already past the limit
 * this month), "pace" (this month is on pace to go over), "trend-up" (spending
 * is rising towards more than the limit), "trend-down" (falling, but not fast
 * enough) and "average" (the monthly average is above the limit).
 */
export const scopeStats = (scopes, totals, monthKeys, today = new Date()) => {
  const nowKey = currentMonthKey(today);
  const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();

  return scopes.map((scope) => {
    const months = totals.get(scope.id);
    const firstWith = monthKeys.findIndex((k) => (months.get(k) || 0) > 0);
    const history = firstWith < 0 ? [] : monthKeys.slice(firstWith);
    const values = history.map((k) => months.get(k) || 0);
    const reg = values.length >= MIN_HISTORY ? regress(values) : null;

    const currentCents = months.get(nowKey) || 0;
    const paceCents = Math.round((currentCents / today.getDate()) * daysInMonth);
    const forecastCurrent = reg ? Math.max(0, Math.round(reg.at(values.length))) : null;
    const forecastNext = reg ? Math.max(0, Math.round(reg.at(values.length + 1))) : null;
    const changePct = reg && reg.mean > 0 ? reg.slope / reg.mean : null;

    /* Where this month is heading. A month's spending is lumpy (rent on the 1st), so
       extrapolating the days so far overshoots; with a trend, use what it says for
       this month (never less than is already spent), and the pace only without one. */
    const projectedCents = reg ? Math.max(currentCents, forecastCurrent) : paceCents;

    const budget = scope.budget;
    const active = !!budget && isActiveIn(budget, nowKey);
    const limitCents = budget ? toCents(budget.monthly_limit) : 0;

    let status = "none";
    const reasons = [];
    let reduceCents = 0;
    if (budget && !active) {
      status = "inactive";
    } else if (active) {
      if (currentCents > limitCents) {
        status = "over";
        reasons.push("over");
      } else if (currentCents >= limitCents * 0.8) {
        status = "near";
      } else if (projectedCents > limitCents) {
        status = "pace";
      } else if (reg && forecastNext > limitCents) {
        status = "trend";
      } else {
        status = "ok";
      }
      if (projectedCents > limitCents && status !== "over") reasons.push("pace");
      if (reg && forecastNext > limitCents) reasons.push(reg.slope > 0 ? "trend-up" : "trend-down");
      if (reg && reg.mean > limitCents) reasons.push("average");
      const worst = Math.max(forecastNext || 0, projectedCents, currentCents);
      reduceCents = reasons.length ? Math.max(0, worst - limitCents) : 0;
    }

    return {
      scope,
      values,
      history,
      reg,
      forecastCurrent,
      forecastNext,
      changePct,
      currentCents,
      paceCents,
      projectedCents,
      limitCents,
      active,
      status,
      reduceCents,
      reasons,
    };
  });
};

/* What was spent in a budget's period so far, and what the period allows, for
   a budget of several months */
export const periodSpend = (budget, months, nowKey) => {
  const start = budget.start_month.slice(0, 7);
  const last = nowKey < addMonths(start, budget.months) ? nowKey : addMonths(start, budget.months - 1);
  let spent = 0;
  for (let key = start; key <= last; key = addMonths(key, 1)) spent += months.get(key) || 0;
  return { spent, allowed: toCents(budget.monthly_limit) * budget.months };
};
