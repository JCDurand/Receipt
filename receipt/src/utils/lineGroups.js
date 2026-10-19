/* Line items grouped under the documents they belong to, for the Transactions
   table. A bank statement holds its lines and, beneath them, any receipt which
   was matched to one of its lines (the statement is the bank's record, so it
   comes first); a receipt holds its items. A receipt matched to no statement
   line stands on its own, and a line item which belongs to no document is a
   row of its own. */
import { toCents } from "./spending";

const sourceKey = (source) => `${source.category}:${source.id}`;

/* What a line item adds to money in or out, in cents */
const money = (line) => {
  const cents = Math.abs(toCents(line.amount));
  const isIn = line.kind === "statement_line" ? toCents(line.amount) > 0 : line.direction === "in";
  return isIn ? { in: cents, out: 0 } : { in: 0, out: cents };
};

/**
 * The documents behind `allLines` (every line item, whatever the filters), so
 * that a document is described by all of its line items, and a receipt is put
 * under the statement it was matched to even when the matched line is filtered
 * out. Returns { groups: Map(key -> group), parentOf: Map(receiptKey -> statementKey) }.
 */
export const documentGroups = (allLines) => {
  const groups = new Map();
  const statementOfLine = new Map(); // statement line id -> its statement's key

  for (const line of allLines) {
    if (!line.source) continue;
    const key = sourceKey(line.source);
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        id: line.source.id,
        kind: line.source.category, // "statement", "receipt" or "cash"
        name: line.source.name,
        account: line.account,
        total: 0,
        inCents: 0,
        outCents: 0,
        firstDate: line.date,
        lastDate: line.date,
        receipts: 0,
      });
    }
    const group = groups.get(key);
    group.total += 1;
    const m = money(line);
    group.inCents += m.in;
    group.outCents += m.out;
    if (line.date < group.firstDate) group.firstDate = line.date;
    if (line.date > group.lastDate) group.lastDate = line.date;
    if (line.kind === "statement_line") statementOfLine.set(line.id, key);
  }

  /* a receipt goes under the statement holding the first line any of its items was matched to */
  const parentOf = new Map();
  const anchorOf = new Map(); // receipt key -> the statement line id it hangs from
  for (const line of allLines) {
    if (line.kind !== "receipt_item" || !line.source || !line.transaction_id) continue;
    const key = sourceKey(line.source);
    const statementKey = statementOfLine.get(line.transaction_id);
    if (statementKey && !parentOf.has(key)) {
      parentOf.set(key, statementKey);
      anchorOf.set(key, line.transaction_id);
      groups.get(statementKey).receipts += 1;
    }
  }
  return { groups, parentOf, anchorOf };
};

/**
 * The rows to show, for `lines` (the line items which pass the filters, in the
 * order they are sorted) grouped by `structure` (documentGroups of every line).
 * `isOpen(key)` says whether a group shows its line items. A group's place is
 * that of its first line item in the sort; inside a statement, a receipt comes
 * straight after the line it was matched to.
 *
 * Returns { entries, topLevel } where entries are LineTable's ({ type: "group",
 * group, depth, isOpen } and { type: "line", line, depth }) and topLevel is how
 * many rows stand at the top, for paging.
 */
export const groupEntries = (lines, structure, isOpen, limit = Infinity) => {
  const { groups, parentOf, anchorOf } = structure;

  /* which line items of each group pass the filters, in sorted order */
  const members = new Map();
  const order = []; // top-level things, in the order they first appear: group keys, or lines
  const placed = new Set();
  const topOf = (line) => {
    if (!line.source) return null;
    const key = sourceKey(line.source);
    return parentOf.get(key) || key;
  };

  for (const line of lines) {
    const key = line.source ? sourceKey(line.source) : null;
    if (key) {
      if (!members.has(key)) members.set(key, []);
      members.get(key).push(line);
    }
    const top = topOf(line);
    if (top === null) {
      order.push({ line });
    } else if (!placed.has(top)) {
      placed.add(top);
      order.push({ key: top });
    }
  }

  /* the receipts under each statement, keyed by the statement line they hang from */
  const receiptsUnder = new Map();
  for (const [receiptKey, statementKey] of parentOf) {
    if (!members.has(receiptKey)) continue;
    if (!receiptsUnder.has(statementKey)) receiptsUnder.set(statementKey, []);
    receiptsUnder.get(statementKey).push(receiptKey);
  }

  const entries = [];
  const shown = (key) => ({ ...groups.get(key), shown: (members.get(key) || []).length });

  const pushGroup = (key, depth) => {
    const open = isOpen(key);
    entries.push({ type: "group", group: shown(key), depth, isOpen: open });
    if (!open) return;

    const own = members.get(key) || [];
    const receipts = receiptsUnder.get(key) || [];
    const done = new Set();
    const pushReceipt = (receiptKey) => {
      if (done.has(receiptKey)) return;
      done.add(receiptKey);
      pushGroup(receiptKey, depth + 1);
    };
    for (const line of own) {
      entries.push({ type: "line", line, depth: depth + 1 });
      for (const receiptKey of receipts) if (anchorOf.get(receiptKey) === line.id) pushReceipt(receiptKey);
    }
    /* receipts whose line did not pass the filters, though their items did */
    for (const receiptKey of receipts) pushReceipt(receiptKey);
  };

  let topLevel = 0;
  for (const item of order) {
    if (topLevel >= limit) break;
    topLevel += 1;
    if (item.line) entries.push({ type: "line", line: item.line, depth: 0 });
    else pushGroup(item.key, 0);
  }
  return { entries, topLevel: order.length };
};
