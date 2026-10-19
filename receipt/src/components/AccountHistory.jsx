import React, { useMemo, useState } from "react";
import { MultiLineChart, colorAt } from "./Charts";
import { Empty, Pills } from "./AnalyticsBits";
import { AccountWarning } from "./AccountBalance";
import { balanceIntervals } from "../utils/accountHistory";
import { bucketKey } from "../utils/analytics";
import { formatDay, formatMoney } from "../utils/format";
import "../styles/AccountBalance.css";

const GRANULARITIES = [
  { key: "auto", label: "Auto" },
  { key: "day", label: "Day" },
  { key: "week", label: "Week" },
  { key: "month", label: "Month" },
];

const shortOf = (label, unit) => (unit === "month" ? label.split(" ")[0] : label.replace("Week of ", ""));

/**
 * The balance of the user's bank accounts through time: a chart of each
 * account (and their total) at the end of every day, week or month of the
 * period, and a table of what each interval opened with, what came in and went
 * out, and what it closed with. An account's balance follows its documents from
 * the day it was opened; before that, it is worked back from the opening
 * balance, interval by interval. `history` is GET /accounts/history/'s answer.
 */
const AccountHistory = ({ history, period }) => {
  const [accountId, setAccountId] = useState("all");
  const [granularity, setGranularity] = useState("auto");

  const accounts = useMemo(() => history?.accounts || [], [history]);
  const chosen = useMemo(
    () => (accountId === "all" ? accounts : accounts.filter((a) => a.id === accountId)),
    [accounts, accountId]
  );
  const { unit, rows } = useMemo(() => balanceIntervals(chosen, period, granularity), [chosen, period, granularity]);

  if (accounts.length === 0) {
    return <Empty message="Add a bank account to see its balance through time." />;
  }

  const point = (row, cents) => ({ key: row.key, label: row.label, short: shortOf(row.label, unit), cents });
  const series =
    chosen.length === 1
      ? [{ id: chosen[0].id, name: chosen[0].account_name, color: colorAt(0), points: rows.map((r) => point(r, r.closing)) }]
      : [
          ...chosen.map((a, i) => ({
            id: a.id,
            name: a.account_name,
            color: colorAt(i),
            points: rows.map((r) => point(r, r.perAccount[a.id])),
          })),
          { id: "total", name: "All accounts", color: "#2c3e50", dashed: true, dots: true, points: rows.map((r) => point(r, r.closing)) },
        ];
  const markers = chosen
    .map((a, i) => ({ key: bucketKey(a.opened_on, unit), label: `${a.account_name} opened`, color: colorAt(i) }))
    .filter((m) => rows.some((r) => r.key === m.key));
  const anyBefore = rows.some((r) => r.beforeOpening);

  return (
    <div className="account-history">
      <div className="chart-card chart-card-wide">
        <div className="chart-card-head">
          <h4>Account balances over time</h4>
          <div className="budget-controls">
            <select className="analytics-select" value={accountId} onChange={(e) => setAccountId(e.target.value)} aria-label="Account">
              <option value="all">All accounts</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.account_name} (...{a.account_number})
                </option>
              ))}
            </select>
            <Pills options={GRANULARITIES} value={granularity} onChange={setGranularity} label="Interval" />
          </div>
        </div>

        {chosen.map((a) => (
          <div key={a.id} className="account-history-warning">
            <AccountWarning account={a} />
          </div>
        ))}

        {rows.length === 0 ? (
          <Empty message="Nothing moved in this period." />
        ) : (
          <MultiLineChart series={series} markers={markers} label="Account balances over time" />
        )}
        <p className="spending-note">
          From the day an account was opened, its balance is its opening balance moved by every line dated after it. Before
          then it is worked back from the opening balance, taking off each interval's money in and adding back its money out.
          Amounts are in {history.currency}, each converted at the rate of its own day.
        </p>
      </div>

      {rows.length > 0 && (
        <div className="chart-card chart-card-wide">
          <div className="chart-card-head">
            <h4>Interval by interval</h4>
            <span className="spending-hint">Newest first</span>
          </div>
          <div className="recurring-scroll account-history-table">
            <table className="recurring-table">
              <thead>
                <tr>
                  <th>{unit === "month" ? "Month" : unit === "week" ? "Week" : "Day"}</th>
                  <th className="num">Opening</th>
                  <th className="num">Money in</th>
                  <th className="num">Money out</th>
                  <th className="num">Closing</th>
                  <th>Balance</th>
                </tr>
              </thead>
              <tbody>
                {[...rows].reverse().map((r) => (
                  <tr key={r.key} className={r.beforeOpening ? "is-before-opening" : undefined}>
                    <td>{unit === "day" ? formatDay(r.start) : r.label}</td>
                    <td className="num">{formatMoney(r.opening)}</td>
                    <td className="num line-amount is-credit">{r.in ? `+${formatMoney(r.in)}` : "-"}</td>
                    <td className="num line-amount is-debit">{r.out ? `−${formatMoney(r.out)}` : "-"}</td>
                    <td className={`num${r.closing < 0 ? " is-neg" : ""}`}>
                      <strong>{formatMoney(r.closing)}</strong>
                    </td>
                    <td className="spending-hint">{r.beforeOpening ? "Worked back from the opening balance" : "Recorded"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {anyBefore && (
            <p className="spending-note">
              Intervals before an account was opened are not checked against anything: they only add up if every statement
              from then has been uploaded.
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export default AccountHistory;
