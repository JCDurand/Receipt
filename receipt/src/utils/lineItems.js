/* Line items which have not been saved yet, as the upload and manual entry
   dialogs edit them: the rows of a table, and what is sent to the server when
   they are saved.

   A row is { key, name, merchant, date, direction, amount, tags } and, for a
   receipt item, its `quantity` (how many of the item its line is for: 5 red apples
   for 70.00 is 5) and `unit_price` (what one costs, which follows from the amount
   and the quantity). `amount` is always positive text, and is the line's total
   whatever its quantity: `direction` says whether the money went out ("debit") or
   came in ("credit"). `date` is YYYY-MM-DD, as everywhere else, or "" when there
   is none. */

export const DIRECTIONS = [
  { value: "debit", label: "Debit" },
  { value: "credit", label: "Credit" },
];

/* An amount without its sign: the direction says which way it went */
export const absAmount = (amount) => String(amount ?? "").replace(/^[-+]/, "");

/* The direction of a signed amount, as a statement records them: a debit is negative */
export const directionOfAmount = (amount) => (Number(amount) > 0 ? "credit" : "debit");

/* What one of a line's items costs: its amount shared between the quantity, or
   null when there is no such price (no amount yet, or a quantity which is not more
   than nothing) */
export const unitPriceOf = (amount, quantity) => {
  const total = Number(absAmount(amount));
  const count = Number(quantity);
  return absAmount(amount) !== "" && Number.isFinite(total) && count > 0 ? (total / count).toFixed(2) : null;
};

/* The change to a row when its quantity is: its unit price follows, so the line
   keeps its total */
export const quantityPatch = (row, quantity) => {
  const unitPrice = unitPriceOf(row.amount, quantity);
  return unitPrice === null ? { quantity } : { quantity, unit_price: unitPrice };
};

/* A quantity left blank is the one of an item on its own */
const quantityOf = (row) => (String(row.quantity ?? "").trim() === "" ? "1" : String(row.quantity).trim());

export const blankRow = (key) => ({
  key,
  name: "",
  merchant: "",
  date: "",
  direction: "debit",
  quantity: "1",
  amount: "",
  tags: [],
});

/* The line items read from a receipt. The merchant and date are the receipt's, for
   the user to change line by line. */
export const rowsFromReceipt = (result) =>
  (result.items || []).map((item, key) => ({
    key,
    name: item.name,
    merchant: result.merchant_name || "",
    date: result.transaction_date || "",
    direction: Number(item.total) < 0 ? "credit" : "debit",
    amount: absAmount(item.total),
    quantity: item.quantity,
    unit_price: absAmount(item.unit_price),
    tags: [],
  }));

/* The transactions read from a bank statement. Its lines only have the bank's
   text, in which the merchant is to be found, so that is where the merchant starts,
   unless one of the user's templates has already named it. A template's tags
   (sent as ids) are already on the line, as the tags of `availableTags` they are. */
export const rowsFromStatement = (result, availableTags = []) =>
  (result.transactions || []).map((line, key) => ({
    key,
    name: line.name,
    merchant: line.merchant || line.name,
    date: line.date,
    direction: directionOfAmount(line.amount),
    amount: absAmount(line.amount),
    tags: (line.tags || []).map((id) => availableTags.find((tag) => tag.id === id)).filter(Boolean),
  }));

const tagIds = (row) => row.tags.map((tag) => tag.id);

export const receiptItemsPayload = (rows) =>
  rows.map((row) => ({
    name: row.name,
    quantity: quantityOf(row),
    unit_price: row.unit_price,
    total: row.amount,
    merchant: row.merchant.trim(),
    date: row.date || null,
    direction: row.direction,
    tags: tagIds(row),
  }));

export const statementTransactionsPayload = (rows) =>
  rows.map((row) => ({
    name: row.name,
    merchant: row.merchant.trim(),
    date: row.date,
    direction: row.direction,
    amount: row.amount,
    tags: tagIds(row),
  }));

/* A manual entry keeps only the rows which have a name and an amount */
export const manualItemsPayload = (rows) =>
  rows
    .filter((row) => row.name.trim() && row.amount !== "")
    .map((row) => ({
      name: row.name.trim(),
      cost: parseFloat(row.amount),
      quantity: quantityOf(row),
      merchant: row.merchant.trim(),
      date: row.date || null,
      direction: row.direction,
      tags: tagIds(row),
    }));
