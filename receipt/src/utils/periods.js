import { addDays, isoDay } from "./analytics";

/* The date a number of months before `today`, the day after (so "3 months" is
   3 months of days ending today); the last day of a month which is too short
   for today's day-of-month */
const monthsBefore = (today, months) => {
  const target = new Date(today.getFullYear(), today.getMonth() - months, 1);
  const daysThere = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(today.getDate(), daysThere));
  return isoDay(addDays(target, 1));
};

/* The periods the dashboard pages offer, as from/to dates (YYYY-MM-DD) */
export const periodPresets = (today = new Date()) => {
  const to = isoDay(today);
  return [
    { key: "1m", label: "1 month", from: monthsBefore(today, 1), to },
    { key: "3m", label: "3 months", from: monthsBefore(today, 3), to },
    { key: "6m", label: "6 months", from: monthsBefore(today, 6), to },
    { key: "12m", label: "12 months", from: monthsBefore(today, 12), to },
    { key: "ytd", label: "This year", from: `${today.getFullYear()}-01-01`, to },
    { key: "all", label: "All time", from: "", to: "" },
  ];
};
