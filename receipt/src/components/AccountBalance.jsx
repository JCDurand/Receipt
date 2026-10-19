import React from "react";
import { formatDay, formatMoney } from "../utils/format";
import { toCents } from "../utils/spending";

/* An account's balance now (in its own currency), and the opening balance it
   grew from, as the account list gives them */
export const AccountBalance = ({ account, compact = false }) => {
  if (account.balance == null) return null;
  const balance = toCents(account.balance);
  return (
    <span className={`account-balance${compact ? " is-compact" : ""}`}>
      <strong className={balance < 0 ? "is-neg" : undefined}>{formatMoney(balance, { currency: account.currency })}</strong>
      <span className="account-balance-sub">
        from {formatMoney(toCents(account.funds), { currency: account.currency })} on opening, {formatDay(account.opened_on)}
      </span>
    </span>
  );
};

/* What to say about a savings account which went below zero: it is not stopped,
   but it cannot be right. Nothing for an account which did not. */
export const AccountWarning = ({ account }) =>
  account?.warning ? (
    <p className="account-warning" role="alert">
      <span aria-hidden="true">!</span> {account.warning}
    </p>
  ) : null;
