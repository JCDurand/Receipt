/* Statements and receipts against a timeline. A statement is the main thing on
   it: the receipts which were matched to it are consolidated into it, and a
   receipt which was matched to nothing stands alone, unconsolidated. Money is
   whole cents, in the user's currency. */
import { bucketKey, bucketLabel, bucketsBetween, chartSpan } from "./analytics";
import { toCents } from "./spending";
import { bankOf } from "./grouping";

export const MODES = [
  { key: "statements", label: "Statements only" },
  { key: "both", label: "Statements and receipts" },
  { key: "transactions", label: "All transactions" },
];

const dayOf = (value) => (value ? String(value).slice(0, 10) : "");

/* What a receipt item or statement line adds to money in or out */
const moneyOf = (line) => {
  const cents = Math.abs(toCents(line.amount));
  const isIn = line.kind === "statement_line" ? toCents(line.amount) > 0 : line.direction === "in";
  return { in: isIn ? cents : 0, out: isIn ? 0 : cents };
};

/**
 * Builds the statements and receipts from the document list and the line items.
 * Returns { statements, receipts } where
 *   statement: { kind: "statement", id, name, date, firstDate, lastDate, bank, account, lineCount, inCents, outCents, receipts: [receipt] }
 *   receipt:   { kind: "receipt" | "cash", id, name, date, totalCents, itemCount, statementIds, isConsolidated }
 */
export const buildDocuments = (documents, lines, accounts) => {
  const byAccount = new Map(accounts.map((a) => [a.id, a]));
  const bySource = new Map();
  for (const line of lines) {
    if (!line.source) continue;
    if (!bySource.has(line.source.id)) bySource.set(line.source.id, []);
    bySource.get(line.source.id).push(line);
  }

  const statements = documents
    .filter((d) => d.category === "statement")
    .map((doc) => {
      const own = bySource.get(doc.id) || [];
      const dates = own.map((l) => l.date).sort();
      const fallback = dayOf(doc.uploaded_at);
      const totals = own.reduce((t, l) => ({ in: t.in + moneyOf(l).in, out: t.out + moneyOf(l).out }), { in: 0, out: 0 });
      const account = byAccount.get(doc.meta?.account);
      return {
        kind: "statement",
        id: doc.id,
        name: doc.file_name,
        firstDate: dates[0] || fallback,
        lastDate: dates[dates.length - 1] || fallback,
        date: dates[dates.length - 1] || fallback,
        bank: own.length ? bankOf(own[0]) : doc.meta?.bank || "unspecified",
        account: account ? account.account_name : "",
        lineCount: own.length || doc.meta?.transaction_count || 0,
        inCents: totals.in,
        outCents: totals.out,
        receipts: [],
      };
    });

  const receipts = documents
    .filter((d) => d.category === "receipt" || d.category === "cash")
    .map((doc) => {
      const own = bySource.get(doc.id) || [];
      const dates = own.map((l) => l.date).sort();
      const net = own.reduce((sum, l) => sum + moneyOf(l).out - moneyOf(l).in, 0);
      const statementIds = doc.statement_ids || [];
      return {
        kind: doc.category,
        id: doc.id,
        name: doc.file_name,
        date: dates[0] || dayOf(doc.meta?.transaction_date) || dayOf(doc.uploaded_at),
        totalCents: net,
        itemCount: own.length || (doc.meta?.items || []).length,
        statementIds,
        isConsolidated: statementIds.length > 0,
      };
    });

  const byId = new Map(statements.map((s) => [s.id, s]));
  for (const receipt of receipts) for (const id of receipt.statementIds) byId.get(id)?.receipts.push(receipt);
  return { statements, receipts };
};

/**
 * What the timeline shows, newest first, for the mode and the filters (from,
 * to, bank). In "statements" or "both" mode: statement nodes (with, in "both",
 * the receipts consolidated into them as children) and, in "both", receipts
 * which are not under a statement shown: unconsolidated ones, and ones whose
 * statement is outside the filters (`statementOutOfView`).
 */
export const timelineNodes = ({ statements, receipts }, mode, { from = "", to = "", bank = "all" }) => {
  const inPeriod = (day) => (!from || day >= from) && (!to || day <= to);
  const shown = statements
    // a statement is in the period when its dates reach into it
    .filter((s) => (bank === "all" || s.bank === bank) && (!to || s.firstDate <= to) && (!from || s.lastDate >= from))
    .map((s) => ({ ...s, children: mode === "both" ? s.receipts : [] }));
  if (mode === "statements") return shown.sort((a, b) => b.date.localeCompare(a.date));

  const visible = new Set(shown.map((s) => s.id));
  const standalone = receipts
    .filter((r) => inPeriod(r.date) && !r.statementIds.some((id) => visible.has(id)))
    // choosing a bank leaves only what belongs to its statements
    .filter((r) => bank === "all" || r.statementIds.length > 0)
    .map((r) => ({ ...r, statementOutOfView: r.isConsolidated }));
  return [...shown, ...standalone].sort((a, b) => b.date.localeCompare(a.date));
};

/* ---- The histogram ---- */

/**
 * How many statements and receipts (or transactions) fall in each day, week or
 * month, stacked by what they are.
 * Returns { granularity, series: [{ id, name, color }], points } for StackedColumns,
 * whose `values` are counts.
 */
export const histogram = (nodes, mode, filters, granularity = "auto", transactions = []) => {
  const palette = { statement: "#2a78d6", consolidated: "#1baf7a", unconsolidated: "#eb6834", out: "#eb6834", in: "#1baf7a" };
  const dated =
    mode === "transactions"
      ? transactions.map((l) => ({ date: l.date, series: moneyOf(l).in > 0 ? "in" : "out" }))
      : nodes.map((n) => ({
          date: n.date,
          series: n.kind === "statement" ? "statement" : n.isConsolidated ? "consolidated" : "unconsolidated",
        }));
  const names = {
    statement: "Statements",
    consolidated: "Receipts consolidated",
    unconsolidated: "Receipts unconsolidated",
    out: "Money out",
    in: "Money in",
  };
  const ids = mode === "transactions" ? ["out", "in"] : mode === "statements" ? ["statement"] : ["statement", "consolidated", "unconsolidated"];
  const series = ids.map((id) => ({ id, name: names[id], color: palette[id] }));

  const span = chartSpan(dated, filters, granularity);
  if (!span) return { granularity: "day", series, points: [] };
  const byBucket = new Map();
  for (const item of dated) {
    const key = bucketKey(item.date, span.unit);
    const values = byBucket.get(key) || {};
    values[item.series] = (values[item.series] || 0) + 1;
    byBucket.set(key, values);
  }
  const points = bucketsBetween(span.first, span.last, span.unit).map((key) => {
    const values = byBucket.get(key) || {};
    const label = bucketLabel(key, span.unit);
    return {
      key,
      label,
      short: span.unit === "month" ? label.split(" ")[0] : label.replace("Week of ", ""),
      values,
      totalCents: Object.values(values).reduce((s, c) => s + c, 0),
    };
  });
  return { granularity: span.unit, series, points };
};
