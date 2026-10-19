/* Numbers behind the analytics dashboard, worked out from the line items of
   GET /line-items/ and the accounts of GET /accounts/. Money is whole cents. */
import { spendingLines, spentCents, tagIndex, toCents } from "./spending";
import { getCurrency } from "./format";

export const isoDay = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

export const parseDay = (iso) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
};

export const addDays = (date, days) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);

/* Line items carry a date and no time of day, so "24 hours" is yesterday and
   today, and the longer periods end today */
export const analyticsPresets = (today = new Date()) => {
  const to = isoDay(today);
  const back = (days) => isoDay(addDays(today, -days));
  return [
    { key: "24h", label: "24 hours", from: back(1), to },
    { key: "1w", label: "1 week", from: back(6), to },
    { key: "1m", label: "1 month", from: back(29), to },
    { key: "3m", label: "3 months", from: back(89), to },
    { key: "1y", label: "1 year", from: back(364), to },
    { key: "all", label: "All time", from: "", to: "" },
  ];
};

/* ---- Money in, money out ---- */

/* Money coming in, in cents. A matched receipt item is not income. */
export const receivedCents = (line) => {
  if (line.kind !== "statement_line") return 0;
  const cents = toCents(line.amount);
  return cents > 0 ? cents : 0;
};

const inPeriod = (line, from, to) => (!from || line.date >= from) && (!to || line.date <= to);

/* Money coming in which satisfies every filter, as spendingLines is for money
   going out */
export const incomeLines = (lines, { tagIds = [], from = "", to = "" } = {}) => {
  const tagsOf = tagIndex(lines);
  return lines.filter(
    (line) =>
      receivedCents(line) > 0 &&
      inPeriod(line, from, to) &&
      (tagIds.length === 0 || tagsOf(line).some((tag) => tagIds.includes(tag.id)))
  );
};

export const incomeInPeriod = (lines, filters = {}) =>
  incomeLines(lines, filters).reduce((sum, line) => sum + receivedCents(line), 0);

/* The lines a chart counts and what each is worth: money out, unless the
   filters' `flow` is "in" */
export const flowOf = (filters) =>
  filters.flow === "in" ? { pick: incomeLines, cents: receivedCents } : { pick: spendingLines, cents: spentCents };

/* The chosen tags and every tag beneath them, so that choosing a parent tag
   takes in its subtags */
export const withSubtags = (tagIds, tags) => {
  const found = new Set(tagIds);
  let grew = true;
  while (grew) {
    grew = false;
    for (const tag of tags) {
      if (tag.parent && found.has(tag.parent) && !found.has(tag.id)) {
        found.add(tag.id);
        grew = true;
      }
    }
  }
  return [...found];
};

/* ---- Statistical summary ---- */

export const summarise = (lines, filters) => {
  const { pick, cents } = flowOf(filters);
  const chosen = pick(lines, filters);
  const amounts = chosen.map(cents).sort((a, b) => a - b);
  const total = amounts.reduce((sum, c) => sum + c, 0);
  const spent = filters.flow === "in" ? spendingLines(lines, filters).reduce((s, l) => s + spentCents(l), 0) : total;
  const income = filters.flow === "in" ? total : incomeInPeriod(lines, filters);

  const days = new Set(chosen.map((l) => l.date));
  let spanDays = 1;
  const from = filters.from || (chosen.length ? chosen.reduce((m, l) => (l.date < m ? l.date : m), chosen[0].date) : "");
  const to = filters.to || isoDay(new Date());
  if (from) spanDays = Math.max(1, Math.round((parseDay(to) - parseDay(from)) / 86400000) + 1);

  const mid = Math.floor(amounts.length / 2);
  const median = amounts.length === 0 ? 0 : amounts.length % 2 ? amounts[mid] : Math.round((amounts[mid - 1] + amounts[mid]) / 2);
  const biggest = chosen.reduce((best, l) => (!best || cents(l) > cents(best) ? l : best), null);

  return {
    count: chosen.length,
    totalCents: total,
    spentCents: spent,
    incomeCents: income,
    netCents: income - spent,
    averageCents: chosen.length ? Math.round(total / chosen.length) : 0,
    medianCents: median,
    perDayCents: Math.round(total / spanDays),
    activeDays: days.size,
    biggest,
    biggestCents: biggest ? cents(biggest) : 0,
  };
};

/* The period of the same length just before the filters' one, to compare
   against; none when the period is open at either end */
export const previousPeriod = (filters) => {
  if (!filters.from || !filters.to || filters.from > filters.to) return null;
  const from = parseDay(filters.from);
  const span = Math.round((parseDay(filters.to) - from) / 86400000) + 1;
  return { ...filters, from: isoDay(addDays(from, -span)), to: isoDay(addDays(from, -1)) };
};

/* How much bigger `now` is than `before`, as a fraction; null when there is
   nothing before to compare with */
export const change = (now, before) => (before > 0 ? (now - before) / before : null);

/* ---- Category breakdown ---- */

/* Spending by tag, for a pie. A line item with several tags would be counted
   under each and so add up to more than the total; here its amount is split
   evenly between its tags (the spare cents to the first), so the slices add
   up to exactly the total. Untagged items are their own slice. Past `max`
   slices the smallest are folded into "Other". */
export const categoryBreakdown = (lines, filters, max = 8) => {
  const { pick, cents: centsOf } = flowOf(filters);
  const chosen = filters.tagIds || [];
  const tagsOf = tagIndex(lines);
  const slices = new Map();
  const add = (id, name, cents) => {
    const entry = slices.get(id) || { id, name, cents: 0 };
    entry.cents += cents;
    slices.set(id, entry);
  };

  for (const line of pick(lines, filters)) {
    const cents = centsOf(line);
    const tags = chosen.length ? tagsOf(line).filter((t) => chosen.includes(t.id)) : tagsOf(line);
    if (tags.length === 0) {
      add("untagged", "Untagged", cents);
      continue;
    }
    const share = Math.floor(cents / tags.length);
    const spare = cents - share * tags.length;
    tags.forEach((tag, i) => add(tag.id, tag.name, share + (i === 0 ? spare : 0)));
  }

  return foldSmallest([...slices.values()], max);
};

export const foldSmallest = (entries, max) => {
  const sorted = entries.sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name));
  if (sorted.length <= max) return sorted;
  const rest = sorted.slice(max - 1);
  return [...sorted.slice(0, max - 1), { id: "other", name: "Other", cents: rest.reduce((s, r) => s + r.cents, 0), count: rest.reduce((s, r) => s + (r.count || 0), 0) }];
};

/* Who the money went to (or came from), by merchant, biggest first */
export const merchantName = (line) => (line.merchant || line.display_name || line.description || "Unknown").trim();

export const topMerchants = (lines, filters, max = 8) => {
  const { pick, cents } = flowOf(filters);
  const byName = new Map();
  for (const line of pick(lines, filters)) {
    const name = merchantName(line);
    const id = name.toLowerCase();
    const entry = byName.get(id) || { id, name, cents: 0, count: 0 };
    entry.cents += cents(line);
    entry.count += 1;
    byName.set(id, entry);
  }
  return foldSmallest([...byName.values()], max);
};

/* Total for each day of the week, Monday first */
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export const weekdayPattern = (lines, filters) => {
  const { pick, cents } = flowOf(filters);
  const points = WEEKDAYS.map((short, i) => ({ key: short, short, label: WEEKDAY_NAMES[i], cents: 0, count: 0 }));
  for (const line of pick(lines, filters)) {
    const point = points[(parseDay(line.date).getDay() + 6) % 7];
    point.cents += cents(line);
    point.count += 1;
  }
  return points;
};

/* ---- Spending over time ---- */

const mondayOf = (iso) => {
  const d = parseDay(iso);
  return isoDay(addDays(d, -((d.getDay() + 6) % 7)));
};

export const bucketKey = (iso, granularity) =>
  granularity === "month" ? iso.slice(0, 7) : granularity === "week" ? mondayOf(iso) : iso;

const nextKey = (key, granularity) => {
  if (granularity === "month") {
    const [y, m] = key.split("-").map(Number);
    return isoDay(new Date(y, m, 1)).slice(0, 7);
  }
  return isoDay(addDays(parseDay(key), granularity === "week" ? 7 : 1));
};

/* Every bucket from the one holding `first` to the one holding `last` */
export const bucketsBetween = (first, last, unit) => {
  const keys = [];
  let key = bucketKey(first, unit);
  const end = bucketKey(last, unit);
  while (key <= end && keys.length < 1000) {
    keys.push(key);
    key = nextKey(key, unit);
  }
  return keys;
};

/* Day, week or month, by how long the period is */
export const autoGranularity = (firstDay, lastDay) => {
  const span = Math.round((parseDay(lastDay) - parseDay(firstDay)) / 86400000) + 1;
  return span <= 45 ? "day" : span <= 200 ? "week" : "month";
};

/* The first and last day to chart, and in what buckets */
export const chartSpan = (dated, filters, granularity) => {
  if (dated.length === 0 && !(filters.from && filters.to)) return null;
  const dates = dated.map((l) => l.date).sort();
  const first = filters.from || dates[0];
  const last = filters.to || dates[dates.length - 1];
  return { first, last, unit: granularity === "auto" ? autoGranularity(first, last) : granularity };
};

/* Spent in each day, week or month of the period, gaps filled with zero.
   Returns [{ key, label, cents, count }] */
export const spendingOverTime = (lines, filters, granularity = "auto") => {
  const { pick, cents } = flowOf(filters);
  const chosen = pick(lines, filters);
  const span = chartSpan(chosen, filters, granularity);
  if (!span) return { granularity: "day", points: [] };

  const totals = new Map();
  for (const line of chosen) {
    const key = bucketKey(line.date, span.unit);
    const entry = totals.get(key) || { cents: 0, count: 0 };
    entry.cents += cents(line);
    entry.count += 1;
    totals.set(key, entry);
  }

  const points = bucketsBetween(span.first, span.last, span.unit).map((key) => ({
    key,
    label: bucketLabel(key, span.unit),
    ...(totals.get(key) || { cents: 0, count: 0 }),
  }));
  return { granularity: span.unit, points };
};

/* Money in and money out side by side in each day, week or month.
   Returns [{ key, label, inCents, outCents, netCents }] */
export const cashFlow = (lines, filters, granularity = "auto") => {
  const out = spendingLines(lines, filters);
  const received = incomeLines(lines, filters);
  const span = chartSpan([...out, ...received], filters, granularity);
  if (!span) return { granularity: "day", points: [] };

  const totals = new Map();
  const add = (line, field, cents) => {
    const key = bucketKey(line.date, span.unit);
    const entry = totals.get(key) || { inCents: 0, outCents: 0 };
    entry[field] += cents;
    totals.set(key, entry);
  };
  out.forEach((l) => add(l, "outCents", spentCents(l)));
  received.forEach((l) => add(l, "inCents", receivedCents(l)));

  const points = bucketsBetween(span.first, span.last, span.unit).map((key) => {
    const entry = totals.get(key) || { inCents: 0, outCents: 0 };
    return { key, label: bucketLabel(key, span.unit), ...entry, netCents: entry.inCents - entry.outCents };
  });
  return { granularity: span.unit, points };
};

export const bucketLabel = (key, unit) => {
  if (unit === "month") {
    const [y, m] = key.split("-").map(Number);
    return new Date(y, m - 1, 1).toLocaleDateString("en-ZA", { month: "short", year: "numeric" });
  }
  const text = parseDay(key).toLocaleDateString("en-ZA", { day: "numeric", month: "short" });
  return unit === "week" ? `Week of ${text}` : text;
};

/* ---- Recurring payments ---- */

const CADENCES = [
  { key: "weekly", label: "Weekly", days: 7, low: 5, high: 9 },
  { key: "fortnightly", label: "Every two weeks", days: 14, low: 12, high: 17 },
  { key: "monthly", label: "Monthly", days: 30.44, low: 26, high: 35 },
  { key: "quarterly", label: "Quarterly", days: 91, low: 80, high: 100 },
  { key: "yearly", label: "Yearly", days: 365, low: 350, high: 380 },
];

export const medianOf = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/* A merchant's name without the reference numbers banks add to it, so that
   "NETFLIX.COM 4471" and "NETFLIX.COM 9902" are the same payee */
export const payeeKey = (line) => merchantName(line).toLowerCase().replace(/[\d#*]+/g, " ").replace(/\s+/g, " ").trim();

/* Payments that come round on a regular cadence: the same payee at least three
   times, most of the gaps between them close to one cadence, and most of the
   amounts close to their typical one. Looks at all of the history, whatever
   the filters. Returns [{ id, name, cadence, typicalCents, monthlyCents,
   lastDate, nextDate, count, isLate }], biggest monthly cost first. */
export const recurringPayments = (lines, today = new Date()) => {
  const byPayee = new Map();
  for (const line of spendingLines(lines)) {
    const key = payeeKey(line);
    if (!key) continue;
    if (!byPayee.has(key)) byPayee.set(key, { name: merchantName(line).replace(/(\s+[\d#*]+)+$/, ""), days: new Map() });
    const days = byPayee.get(key).days;
    days.set(line.date, (days.get(line.date) || 0) + spentCents(line));
  }

  const found = [];
  for (const [id, { name, days }] of byPayee) {
    if (days.size < 3) continue;
    const dates = [...days.keys()].sort();
    const gaps = dates.slice(1).map((d, i) => Math.round((parseDay(d) - parseDay(dates[i])) / 86400000));
    const typicalGap = medianOf(gaps);
    const cadence = CADENCES.find((c) => typicalGap >= c.low && typicalGap <= c.high);
    if (!cadence) continue;
    if (gaps.filter((g) => g >= cadence.low && g <= cadence.high).length < gaps.length * 0.6) continue;

    const amounts = [...days.values()];
    const typical = Math.round(medianOf(amounts));
    if (amounts.filter((a) => Math.abs(a - typical) <= typical * 0.3).length < amounts.length * 0.6) continue;

    const last = dates[dates.length - 1];
    const next = isoDay(addDays(parseDay(last), Math.round(cadence.days)));
    found.push({
      id,
      name,
      cadence: cadence.label,
      typicalCents: typical,
      monthlyCents: Math.round((typical * 30.44) / cadence.days),
      lastDate: last,
      nextDate: next,
      count: dates.length,
      /* due a while ago and not seen since: perhaps cancelled */
      isLate: isoDay(addDays(parseDay(next), Math.round(cadence.days / 2))) < isoDay(today),
    });
  }
  return found.sort((a, b) => b.monthlyCents - a.monthlyCents);
};

/* ---- Budgets ---- */

/* Each budget against what has been spent under its tag (and the tags beneath
   it) in the month holding `today`: spent, its share of the limit, where the
   month is heading at the pace so far, and the average of the three months
   before. `status` is "over", "near" (80% used), "pace" (heading over) or "ok". */
export const budgetProgress = (lines, budgets, tags, today = new Date()) => {
  const year = today.getFullYear();
  const month = today.getMonth();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const monthSpan = (offset) => ({
    from: isoDay(new Date(year, month - offset, 1)),
    to: isoDay(new Date(year, month - offset + 1, 0)),
  });

  return budgets.map((budget) => {
    const tagIds = withSubtags([budget.tag], tags);
    const spentIn = (span) => spendingLines(lines, { tagIds, ...span }).reduce((s, l) => s + spentCents(l), 0);
    const spent = spentIn(monthSpan(0));
    const limit = toCents(budget.monthly_limit);
    const projected = Math.round((spent / today.getDate()) * daysInMonth);
    const status = spent > limit ? "over" : spent >= limit * 0.8 ? "near" : projected > limit ? "pace" : "ok";
    return {
      ...budget,
      limitCents: limit,
      spentCents: spent,
      leftCents: limit - spent,
      projectedCents: projected,
      averageCents: Math.round((spentIn(monthSpan(1)) + spentIn(monthSpan(2)) + spentIn(monthSpan(3))) / 3),
      share: limit > 0 ? spent / limit : 0,
      status,
    };
  });
};

/* ---- Why a chart is empty ---- */

/* When the filters leave nothing to chart, the likeliest reason and what would
   change it: { message, action: { label, flow?, allTime?, clearTags? } }, the
   action being the filters to change.
   `names` are the chosen tags' names, for saying which tags are meant. */
export const explainEmpty = (lines, filters, names = "") => {
  const { pick } = flowOf(filters);
  const other = filters.flow === "in" ? spendingLines : incomeLines;
  const flowWord = filters.flow === "in" ? "money coming in" : "spending";
  const otherWord = filters.flow === "in" ? "spending" : "money coming in";
  const otherFlow = filters.flow === "in" ? "out" : "in";
  const allTime = { ...filters, from: "", to: "" };

  if (filters.tagIds?.length && pick(lines, allTime).length === 0 && other(lines, allTime).length === 0) {
    return { message: `No line items are tagged ${names} yet.`, action: { label: "Clear the tags", clearTags: true } };
  }
  if (other(lines, filters).length > 0) {
    return {
      message: `There is no ${flowWord} here${names ? ` tagged ${names}` : ""}, but there is ${otherWord}.`,
      action: { label: filters.flow === "in" ? "Show spending" : "Show money in", flow: otherFlow },
    };
  }
  const anyTime = pick(lines, allTime);
  if (anyTime.length > 0) {
    const latest = anyTime.reduce((m, l) => (l.date > m ? l.date : m), anyTime[0].date);
    return {
      message: `Nothing in this period. The latest is from ${parseDay(latest).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })}.`,
      action: { label: "Show all time", allTime: true },
    };
  }
  if (other(lines, allTime).length > 0) {
    return {
      message: `There is no ${flowWord}${names ? ` tagged ${names}` : ""} at any time, only ${otherWord}, and none in this period.`,
      action: { label: `${filters.flow === "in" ? "Show spending" : "Show money in"}, all time`, flow: otherFlow, allTime: true },
    };
  }
  return { message: "There are no line items yet. Upload a statement or a receipt to get started.", action: null };
};

/* ---- Account balances ---- */

/* Each account's balance at the end of every day it had a statement line, and
   the total of all of them. An account's funds are its balance today, so the
   balance on earlier days is worked back from that through its statement
   lines. Returns { accounts: [{ id, name, current, points }], total: points }
   where points are [{ date, cents }] sorted by date, over the whole history. */
export const runningBalances = (lines, accounts) => {
  const perAccount = accounts.map((account) => {
    const own = lines
      .filter((l) => l.kind === "statement_line" && l.account?.id === account.id)
      .sort((a, b) => a.date.localeCompare(b.date));
    const current = toCents(account.funds);
    const net = own.reduce((sum, l) => sum + toCents(l.amount), 0);

    /* Balance after each day's lines, from the opening balance */
    let running = current - net;
    const points = [];
    for (const line of own) {
      running += toCents(line.amount);
      if (points.length && points[points.length - 1].date === line.date) points[points.length - 1].cents = running;
      else points.push({ date: line.date, cents: running });
    }
    return {
      id: account.id,
      name: account.account_name || `${account.card_type} account`,
      current,
      opening: current - net,
      points,
    };
  });

  const allDates = [...new Set(perAccount.flatMap((a) => a.points.map((p) => p.date)))].sort();
  const total = allDates.map((date) => ({
    date,
    cents: perAccount.reduce((sum, a) => {
      let balance = a.opening;
      for (const p of a.points) {
        if (p.date > date) break;
        balance = p.cents;
      }
      return sum + balance;
    }, 0),
  }));

  return { accounts: perAccount, total, currentTotal: perAccount.reduce((s, a) => s + a.current, 0) };
};

/* ---- Expense timeline ---- */

/* Spending newest first, as a list of nodes. A bank statement line is a node,
   and the receipt items matched to it branch off it. A receipt which is not
   matched to a line is a node of its own, with its items as branches. A
   single unmatched item (cash, say) has no branches.
   Returns [{ key, date, title, cents, line, branches: [line] }] */
export const expenseTimeline = (lines, filters) => {
  const byLine = new Map();
  for (const line of lines) {
    if (line.kind === "receipt_item" && line.transaction_id) {
      if (!byLine.has(line.transaction_id)) byLine.set(line.transaction_id, []);
      byLine.get(line.transaction_id).push(line);
    }
  }

  const nodes = [];
  const receipts = new Map();
  for (const line of spendingLines(lines, filters)) {
    if (line.kind === "statement_line") {
      nodes.push({
        key: `line-${line.id}`,
        date: line.date,
        title: line.display_name || line.description || "-",
        cents: spentCents(line),
        line,
        branches: (byLine.get(line.id) || []).sort((a, b) => spentCents(b) - spentCents(a)),
      });
    } else if (line.source) {
      const id = `receipt-${line.source.id}`;
      const node = receipts.get(id) || {
        key: id,
        date: line.date,
        title: line.source.name,
        cents: 0,
        line: null,
        source: line.source,
        branches: [],
      };
      node.cents += spentCents(line);
      node.date = node.date > line.date ? node.date : line.date;
      node.branches.push(line);
      receipts.set(id, node);
    }
  }
  for (const node of receipts.values()) {
    if (node.branches.length === 1) node.branches = []; /* one item: nothing to branch to */
    nodes.push(node);
  }
  return nodes.sort((a, b) => b.date.localeCompare(a.date) || b.cents - a.cents);
};

/* ---- CSV export ---- */

const csvCell = (value) => {
  let text = value == null ? "" : String(value);
  /* A cell a spreadsheet would read as a formula is made plain text */
  if (/^[=+\-@\t\r]/.test(text) && Number.isNaN(Number(text))) text = `'${text}`;
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

export const toCsv = (rows) => rows.map((row) => row.map(csvCell).join(",")).join("\r\n");

const rand = (cents) => (cents / 100).toFixed(2);

/* The spending which the filters select, one row per line item */
export const spendingCsv = (lines, filters) => {
  const header = ["Date", "Description", "Merchant", "Type", "Account", "Tags", `Amount spent (${getCurrency()})`, "Document", "Matched to statement"];
  const tagsOf = tagIndex(lines);
  const rows = spendingLines(lines, filters)
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((l) => [
      l.date,
      l.display_name || l.description,
      l.merchant || "",
      l.kind === "statement_line" ? "Statement line" : "Receipt item",
      l.account ? l.account.account_name : "",
      tagsOf(l).map((t) => t.name).join("; "),
      rand(spentCents(l)),
      l.source ? l.source.name : "",
      l.matched ? "Yes" : "No",
    ]);
  return toCsv([header, ...rows]);
};

/* Summary figures, the split by tag, and the spending over time */
export const summaryCsv = (summary, categories, series) =>
  toCsv([
    ["Summary", `Value (${getCurrency()})`],
    ["Total spent", rand(summary.spentCents)],
    ["Money in", rand(summary.incomeCents)],
    ["Net", rand(summary.netCents)],
    ["Line items", summary.count],
    ["Average per line item", rand(summary.averageCents)],
    ["Median line item", rand(summary.medianCents)],
    ["Average per day", rand(summary.perDayCents)],
    [],
    ["Tag", `Amount (${getCurrency()})`],
    ...categories.map((c) => [c.name, rand(c.cents)]),
    [],
    [`Per ${series.granularity}`, `Amount (${getCurrency()})`, "Line items"],
    ...series.points.map((p) => [p.key, rand(p.cents), p.count]),
  ]);

export const balancesCsv = (balances) =>
  toCsv([
    ["Date", ...balances.accounts.map((a) => a.name), `Total (${getCurrency()})`],
    ...balances.total.map((p) => [
      p.date,
      ...balances.accounts.map((a) => {
        let b = a.opening;
        for (const q of a.points) {
          if (q.date > p.date) break;
          b = q.cents;
        }
        return rand(b);
      }),
      rand(p.cents),
    ]),
  ]);

export const downloadCsv = (filename, text) => {
  const url = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};
