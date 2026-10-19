/* Account balances through time, in day, week or month intervals, from the
   daily points of GET /accounts/history/ (each already in the user's currency
   as well as the account's). Money is whole cents. */
import { autoGranularity, bucketKey, bucketLabel, bucketsBetween } from "./analytics";
import { toCents } from "./spending";

/* An account's daily points as cents in the user's currency, oldest first */
const pointsOf = (account) =>
  account.points.map((p) => ({
    date: p.date,
    balance: toCents(p.balance_converted),
    in: toCents(p.in_converted),
    out: toCents(p.out_converted),
  }));

/* The balance at the end of `day`: the last point on or before it; before the
   first point, the first point's balance less what moved on its day */
const balanceAt = (points, day) => {
  let found = null;
  for (const p of points) {
    if (p.date > day) break;
    found = p;
  }
  if (found) return found.balance;
  const first = points[0];
  return first ? first.balance - (first.in - first.out) : 0;
};

/**
 * Every account's balance at the end of each interval of the period, with what
 * came in and went out during it, and the total of all of them.
 *   accounts     GET /accounts/history/'s accounts
 *   from, to     the period (YYYY-MM-DD, "" for open-ended)
 *   granularity  "auto", "day", "week" or "month"
 * Returns { unit, rows: [{ key, label, start, end, opening, in, out, closing,
 * beforeOpening, perAccount: { [id]: closing } }] }, oldest first. An interval
 * is `beforeOpening` when it ends before every chosen account was opened: its
 * balances are worked back from the opening balances, not recorded.
 */
export const balanceIntervals = (accounts, { from = "", to = "" }, granularity = "auto") => {
  const series = accounts.map((a) => ({ id: a.id, openedOn: a.opened_on, points: pointsOf(a) }));
  const dates = series.flatMap((s) => s.points.map((p) => p.date)).sort();
  if (dates.length === 0) return { unit: "day", rows: [] };

  const first = from || dates[0];
  const last = to || dates[dates.length - 1];
  if (first > last) return { unit: "day", rows: [] };
  const unit = granularity === "auto" ? autoGranularity(first, last) : granularity;
  const keys = bucketsBetween(first, last, unit);
  const latestOpening = series.reduce((m, s) => (s.openedOn > m ? s.openedOn : m), "");

  const rows = keys.map((key, i) => {
    const start = i === 0 ? first : unit === "month" ? `${key}-01` : key;
    const nextKey = keys[i + 1];
    /* the interval runs to the day before the next one starts, or the period's end */
    const end = nextKey ? previousDay(nextKey, unit) : last;
    let opening = 0;
    let closing = 0;
    let moneyIn = 0;
    let moneyOut = 0;
    const perAccount = {};
    for (const s of series) {
      const close = balanceAt(s.points, end);
      opening += balanceAt(s.points, previousDay(start, "day"));
      closing += close;
      perAccount[s.id] = close;
      for (const p of s.points) {
        if (p.date >= start && p.date <= end) {
          moneyIn += p.in;
          moneyOut += p.out;
        }
      }
    }
    return {
      key,
      label: bucketLabel(bucketKey(start, unit), unit),
      start,
      end,
      opening,
      in: moneyIn,
      out: moneyOut,
      closing,
      perAccount,
      beforeOpening: end < latestOpening,
    };
  });
  return { unit, rows };
};

/* The day before an interval's first day ("YYYY-MM" for a month) */
const previousDay = (key, unit) => {
  const iso = unit === "month" && key.length === 7 ? `${key}-01` : key;
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d - 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
};
