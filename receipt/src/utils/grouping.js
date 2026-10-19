/* Grouping money in or out for the Expense and Income analysis charts: by
   merchant, or by tag (with further tags or merchants as labels inside each
   group), and the same groups over time. Money is whole cents. */
import { incomeLines, receivedCents, merchantName, bucketKey, bucketsBetween, bucketLabel, chartSpan } from "./analytics";
import { spendingLines, spentCents, tagIndex } from "./spending";

/* ---- Banks ---- */

const BANK_LABELS = { investec: "Investec", fnb: "FNB", absa: "ABSA" };

/* Which bank a line item came from. Only a bank statement's lines have one:
   receipts and cash are "none", and a statement uploaded before the bank was
   recorded is "unspecified". */
export const bankOf = (line) => {
  if (line.kind !== "statement_line") return "none";
  return line.source?.bank || "unspecified";
};

export const bankLabel = (key) =>
  BANK_LABELS[key] || (key === "unspecified" ? "Bank not recorded" : key === "none" ? "Receipts and cash" : key);

/* The banks lines come from, as [{ key, label }], the known ones first */
export const banksIn = (lines) => {
  const found = new Set(lines.map(bankOf));
  const order = [...Object.keys(BANK_LABELS), "unspecified", "none"];
  return [...found]
    .sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99) || a.localeCompare(b))
    .map((key) => ({ key, label: bankLabel(key) }));
};

/* ---- What is counted ---- */

export const centsFor = (flow, line) => (flow === "in" ? receivedCents(line) : spentCents(line));

/* The line items a chart counts: money out (or in), in the period, from the bank */
export const countedLines = (lines, { flow = "out", from = "", to = "", bank = "all" } = {}) => {
  const picked = flow === "in" ? incomeLines(lines, { from, to }) : spendingLines(lines, { from, to });
  return bank === "all" ? picked : picked.filter((line) => bankOf(line) === bank);
};

/* An amount in n parts which add up to it exactly (the spare cents go to the first) */
const split = (cents, n) => {
  const share = Math.floor(cents / n);
  const spare = cents - share * n;
  return Array.from({ length: n }, (_, i) => share + (i === 0 ? spare : 0));
};

export const OTHER_ID = "__other";
const UNTAGGED = { id: "__untagged", name: "Untagged" };

/* ---- Grouping ---- */

/**
 * options:
 *   flow       "out" | "in"
 *   from, to, bank   as for countedLines
 *   groupBy    "merchant" | "tag"
 *   tagIds     for "tag": the tags to make groups of (all tags, when empty). A
 *              chosen tag takes in the tags beneath it.
 *   labelBy    "none" | "merchant" | "tag": what each group is divided into
 *   labelTagIds  for "tag" labels: only these tags (all other tags, when empty)
 *   maxGroups  groups past this many are folded into "Other"
 *   maxLabels  the same for labels
 *
 * Returns { groups, labels, totalCents, count } where each group is
 * { id, name, cents, count, entries: [{ line, cents }], segments: [{ id, name, cents }] }
 * and `labels` are the labels in use, as [{ id, name }], biggest first.
 */
export const groupLines = (lines, tags, options) => {
  const {
    flow = "out",
    groupBy = "merchant",
    tagIds = [],
    labelBy = "none",
    labelTagIds = [],
    maxGroups = 12,
    maxLabels = 6,
  } = options;

  const counted = countedLines(lines, options);
  const tagsOf = tagIndex(lines);
  const parentOf = new Map(tags.map((t) => [t.id, t.parent]));
  /* the chosen tag a tag falls under: itself, or the nearest of its ancestors that was chosen */
  const chosen = new Set(tagIds);
  const rollUp = (id) => {
    for (let at = id, hops = 0; at && hops < 20; at = parentOf.get(at), hops++) if (chosen.has(at)) return at;
    return null;
  };
  const tagName = (id) => tags.find((t) => t.id === id)?.name || "Unknown tag";

  const groups = new Map();
  const addTo = (id, name, line, cents, labelParts) => {
    const group = groups.get(id) || { id, name, cents: 0, entries: [], segmentTotals: new Map() };
    group.cents += cents;
    group.entries.push({ line, cents });
    for (const part of labelParts(cents)) {
      const seg = group.segmentTotals.get(part.id) || { id: part.id, name: part.name, cents: 0 };
      seg.cents += part.cents;
      group.segmentTotals.set(part.id, seg);
    }
    groups.set(id, group);
  };

  /* what a line (worth `cents` in its group) is divided into inside the group */
  const labelsFor = (line, groupTagId) => (cents) => {
    if (labelBy === "merchant") {
      const name = merchantName(line);
      return [{ id: name.toLowerCase(), name, cents }];
    }
    if (labelBy === "tag") {
      /* inside a tag's group the group's own tag is no label; by merchant, every tag is one */
      let others = tagsOf(line).filter((t) => !groupTagId || (t.id !== groupTagId && rollUp(t.id) !== groupTagId));
      if (labelTagIds.length) others = others.filter((t) => labelTagIds.includes(t.id));
      if (others.length === 0) return [{ id: UNTAGGED.id, name: groupTagId ? "No other tag" : UNTAGGED.name, cents }];
      return split(cents, others.length).map((share, i) => ({ id: others[i].id, name: others[i].name, cents: share }));
    }
    return [{ id: "total", name: "Total", cents }];
  };

  for (const line of counted) {
    const cents = centsFor(flow, line);
    if (groupBy === "merchant") {
      const name = merchantName(line);
      addTo(name.toLowerCase(), name, line, cents, labelsFor(line, null));
      continue;
    }

    /* by tag: a line with several tags is shared between them */
    const own = tagsOf(line);
    let ids;
    if (tagIds.length) {
      ids = [...new Set(own.map((t) => rollUp(t.id)).filter(Boolean))];
      if (ids.length === 0) continue; // none of the chosen tags
    } else {
      ids = own.map((t) => t.id);
    }
    if (ids.length === 0) {
      addTo(UNTAGGED.id, UNTAGGED.name, line, cents, labelsFor(line, null));
      continue;
    }
    split(cents, ids.length).forEach((share, i) => {
      const id = ids[i];
      const name = own.find((t) => t.id === id)?.name || tagName(id);
      addTo(id, name, line, share, labelsFor(line, id));
    });
  }

  const sorted = [...groups.values()]
    .map((g) => ({
      ...g,
      count: new Set(g.entries.map((e) => e.line.id)).size,
      segments: [...g.segmentTotals.values()],
    }))
    .sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name));

  const folded = foldGroups(sorted, maxGroups);

  /* the labels in use, biggest first, past maxLabels folded into one */
  const labelTotals = new Map();
  for (const g of folded) {
    for (const seg of g.segments) {
      const t = labelTotals.get(seg.id) || { id: seg.id, name: seg.name, cents: 0 };
      t.cents += seg.cents;
      labelTotals.set(seg.id, t);
    }
  }
  const ranked = [...labelTotals.values()].sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name));
  const keep = new Set(ranked.slice(0, ranked.length > maxLabels ? maxLabels - 1 : maxLabels).map((l) => l.id));
  const labels = ranked.filter((l) => keep.has(l.id));
  if (ranked.length > keep.size) labels.push({ id: OTHER_ID, name: "Other", cents: 0 });

  const regrouped = folded.map((g) => ({ ...g, segments: foldSegments(g.segments, keep) }));

  return {
    groups: regrouped,
    labels,
    totalCents: regrouped.reduce((s, g) => s + g.cents, 0),
    count: counted.length,
  };
};

const foldSegments = (segments, keep) => {
  const out = new Map();
  for (const seg of segments) {
    const id = keep.has(seg.id) ? seg.id : OTHER_ID;
    const entry = out.get(id) || { id, name: id === OTHER_ID ? "Other" : seg.name, cents: 0 };
    entry.cents += seg.cents;
    out.set(id, entry);
  }
  return [...out.values()];
};

/* Past `max` groups the smallest become one "Other" group, which can be opened like any other */
const foldGroups = (sorted, max) => {
  if (sorted.length <= max) return sorted;
  const rest = sorted.slice(max - 1);
  const segmentTotals = new Map();
  for (const g of rest) {
    for (const seg of g.segments) {
      const t = segmentTotals.get(seg.id) || { id: seg.id, name: seg.name, cents: 0 };
      t.cents += seg.cents;
      segmentTotals.set(seg.id, t);
    }
  }
  const entries = rest.flatMap((g) => g.entries);
  return [
    ...sorted.slice(0, max - 1),
    {
      id: OTHER_ID,
      name: `Other (${rest.length})`,
      cents: rest.reduce((s, g) => s + g.cents, 0),
      entries,
      count: new Set(entries.map((e) => e.line.id)).size,
      segmentTotals,
      segments: [...segmentTotals.values()],
    },
  ];
};

/* ---- The groups against dates ---- */

/**
 * Each group's total in every day, week or month of the period: the stack of
 * groups in each bucket. `groups` are those groupLines returned.
 * Returns { granularity, series: [{ id, name }], points: [{ key, label, short, values: { [groupId]: cents }, totalCents }] }
 */
export const groupsOverTime = (groups, { from = "", to = "" } = {}, granularity = "auto") => {
  const entries = groups.flatMap((g) => g.entries.map((e) => ({ ...e, groupId: g.id })));
  const span = chartSpan(
    entries.map((e) => e.line),
    { from, to },
    granularity
  );
  if (!span) return { granularity: "day", series: [], points: [] };

  const byBucket = new Map();
  for (const { line, cents, groupId } of entries) {
    const key = bucketKey(line.date, span.unit);
    const values = byBucket.get(key) || {};
    values[groupId] = (values[groupId] || 0) + cents;
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
  return { granularity: span.unit, series: groups.map((g) => ({ id: g.id, name: g.name })), points };
};
