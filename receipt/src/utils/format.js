/* A date-only value ("2026-08-15") is read as that calendar day, not as
   midnight UTC, which would show the day before in some timezones */
export const formatDay = (dateString) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateString || "");
  const parsed = match ? new Date(+match[1], +match[2] - 1, +match[3]) : new Date(dateString);
  if (!dateString || isNaN(parsed.getTime())) return dateString || "-";
  return parsed.toLocaleDateString("en-ZA", { year: "numeric", month: "short", day: "numeric" });
};

export const formatDateTime = (dateString) => {
  if (!dateString) return "-";
  const parsed = new Date(dateString);
  return isNaN(parsed.getTime()) ? dateString : parsed.toLocaleString("en-ZA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

/* The currency every figure is shown in: the one the user chose in Settings.
   The server converts line items into it, so the amounts reaching the pages
   are already in it; this is only how they are written. Set once the user's
   settings have loaded (see AuthProvider). */
let displayCurrency = "ZAR";

export const setCurrency = (code) => {
  displayCurrency = code || "ZAR";
};

export const getCurrency = () => displayCurrency;

/* An amount held as whole cents, in the user's currency (or `currency`, for an
   amount shown in the one it was recorded in) */
export const formatMoney = (cents, { currency = displayCurrency, ...options } = {}) =>
  (cents / 100).toLocaleString("en-ZA", { style: "currency", currency, ...options });

export const accountLabel = (account) =>
  account
    ? `${account.account_name || `${account.card_type} account`}${
        account.account_number ? ` (...${account.account_number})` : ""
      }`
    : "";

/* Which way the money went, as the server reports it for a saved line item
   ("in" is a credit, "out" a debit) */
export const directionKey = (direction) => (direction === "in" || direction === "credit" ? "credit" : "debit");

export const directionLabel = (direction) => (directionKey(direction) === "credit" ? "Credit" : "Debit");

/* What a line item is shown as: the user's alias if it has one, else the name it was read with */
export const shownName = (name, alias) => alias || name || "";
