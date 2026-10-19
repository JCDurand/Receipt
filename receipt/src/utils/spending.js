/* Working out what was spent from the line items of GET /line-items/. Amounts
   are counted in whole cents, so that adding many of them up does not drift. */

export const toCents = (amount) => Math.round(Number(amount) * 100);

/* What a line item adds to spending, in cents. Money out of a bank account
   counts, and so does an item bought on a receipt; money in counts for nothing,
   and neither does an item which paid money back (a credit). A statement line's
   direction is told by the sign of its amount; a receipt item's amount is always
   positive, and its `direction` says which way it went. */
export const spentCents = (line) => {
  const cents = toCents(line.amount);
  if (line.kind === "statement_line") return cents < 0 ? -cents : 0;
  if (line.direction === "in") return 0;
  return cents > 0 ? cents : 0;
};

/* A receipt item which is matched to a statement line is the same spending as
   that line, so it is counted once, through the statement line */
const isCounted = (line) => line.kind === "statement_line" || !line.matched;

/* The tags a line counts under. A statement line carries the tags of the
   receipt items matched to it as well as its own, because those items are not
   counted themselves (see isCounted) and would otherwise lose their tags. */
export const tagIndex = (lines) => {
  const extra = new Map();
  for (const line of lines) {
    if (line.kind === "receipt_item" && line.transaction_id && line.tags?.length) {
      if (!extra.has(line.transaction_id)) extra.set(line.transaction_id, []);
      extra.get(line.transaction_id).push(...line.tags);
    }
  }
  return (line) => {
    const own = line.tags || [];
    const more = line.kind === "statement_line" ? extra.get(line.id) : null;
    if (!more) return own;
    const byId = new Map([...own, ...more].map((t) => [t.id, t]));
    return [...byId.values()];
  };
};

/* Line items which are spending, and which satisfy every filter:
   from, to: dates as YYYY-MM-DD, inclusive (unbounded, when empty)
   tagIds: has at least one of these tags (any, when empty) */
export const spendingLines = (lines, { tagIds = [], from = "", to = "" } = {}) => {
  const tagsOf = tagIndex(lines);
  return lines.filter(
    (line) =>
      spentCents(line) > 0 &&
      isCounted(line) &&
      (!from || line.date >= from) &&
      (!to || line.date <= to) &&
      (tagIds.length === 0 || tagsOf(line).some((tag) => tagIds.includes(tag.id)))
  );
};

/* The total spent by those line items, and how it divides by tag. A line item
   with several tags is counted under each of them (so the tags can add up to
   more than the total), and under "untagged" when it has none. With tags
   chosen, only they are broken down. */
export const summariseSpending = (lines, filters = {}) => {
  const counted = spendingLines(lines, filters);
  const chosen = filters.tagIds || [];
  const tagsOf = tagIndex(lines);

  const byTag = new Map();
  let untagged = { cents: 0, count: 0 };
  let totalCents = 0;

  for (const line of counted) {
    const cents = spentCents(line);
    totalCents += cents;

    const lineTags = tagsOf(line);
    if (lineTags.length === 0) {
      untagged = { cents: untagged.cents + cents, count: untagged.count + 1 };
    }
    for (const tag of lineTags) {
      if (chosen.length > 0 && !chosen.includes(tag.id)) continue;
      const entry = byTag.get(tag.id) || { id: tag.id, name: tag.name, cents: 0, count: 0 };
      entry.cents += cents;
      entry.count += 1;
      byTag.set(tag.id, entry);
    }
  }

  return {
    totalCents,
    count: counted.length,
    byTag: [...byTag.values()].sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name)),
    untagged: chosen.length === 0 && untagged.count > 0 ? untagged : null,
  };
};

const isoDay = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

/* Ready-made periods, as from/to dates in the same form as the filters above */
export const periodPresets = (today = new Date()) => {
  const year = today.getFullYear();
  const month = today.getMonth();
  return [
    { key: "all", label: "All time", from: "", to: "" },
    { key: "this-month", label: "This month", from: isoDay(new Date(year, month, 1)), to: isoDay(new Date(year, month + 1, 0)) },
    { key: "last-month", label: "Last month", from: isoDay(new Date(year, month - 1, 1)), to: isoDay(new Date(year, month, 0)) },
    { key: "last-30", label: "Last 30 days", from: isoDay(new Date(year, month, today.getDate() - 29)), to: isoDay(today) },
    { key: "this-year", label: "This year", from: `${year}-01-01`, to: `${year}-12-31` },
  ];
};
