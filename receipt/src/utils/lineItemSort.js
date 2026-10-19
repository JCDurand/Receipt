import { accountLabel, directionLabel, shownName } from "./format";

export const KIND_LABELS = { statement_line: "Statement line", receipt_item: "Receipt item" };

/* A line item's tags as the one text it is sorted by */
const tagsKey = (line) => line.tags.map((tag) => tag.name.toLowerCase()).join(", ");

/* The columns, in the order every table of line items shows them, and the
   value each is sorted by. A missing value (null or "") sorts last whichever way
   the column is sorted, so an untagged line item never comes first when sorting
   by tags. A line item's merchant is shown beneath its name, and a cash entry
   is marked in its type. */
export const COLUMNS = [
  { key: "date", label: "Date", value: (l) => l.date },
  { key: "description", label: "Name", value: (l) => shownName(l.description, l.display_name).toLowerCase() },
  { key: "tags", label: "Tags", value: tagsKey },
  { key: "source", label: "Source document", value: (l) => (l.source?.name || "").toLowerCase() },
  { key: "kind", label: "Type", value: (l) => KIND_LABELS[l.kind] },
  { key: "account", label: "Account", value: (l) => accountLabel(l.account).toLowerCase() },
  /* by size, as the amount is shown without its sign */
  { key: "amount", label: "Total", value: (l) => Math.abs(Number(l.amount)), numeric: true },
  { key: "quantity", label: "Qty", value: (l) => (l.quantity == null ? null : Number(l.quantity)), numeric: true },
  { key: "unit_price", label: "Unit price", value: (l) => (l.unit_price == null ? null : Math.abs(Number(l.unit_price))), numeric: true },
  { key: "status", label: "Status", value: (l) => l.status },
  { key: "matched", label: "Matched", value: (l) => (l.matched ? 1 : 0) },
  { key: "added_at", label: "Added", value: (l) => l.added_at },
  { key: "direction", label: "Debit / Credit", value: (l) => directionLabel(l.direction) },
];

/* The columns with these keys, in the order above */
export const columnsFor = (keys) => COLUMNS.filter((c) => keys.includes(c.key));

const isEmpty = (value) => value === null || value === undefined || value === "";

export const compareBy = (column, direction) => (a, b) => {
  const x = column.value(a);
  const y = column.value(b);
  if (isEmpty(x) || isEmpty(y)) return isEmpty(x) && isEmpty(y) ? 0 : isEmpty(x) ? 1 : -1;
  const result = x < y ? -1 : x > y ? 1 : 0;
  return direction === "asc" ? result : -result;
};
