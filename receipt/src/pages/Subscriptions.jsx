import React, { useCallback, useEffect, useMemo, useState } from "react";
import PageShell, { PageStatus } from "../components/PageShell";
import { CategoryBars } from "../components/Charts";
import { Empty, Stat } from "../components/AnalyticsBits";
import GroupDetailModal from "../components/GroupDetailModal";
import { TabPanel, Tabs, useTabs } from "../components/Tabs";
import { useFinanceData } from "../hooks/useFinanceData";
import { addDays, isoDay, payeeKey, recurringPayments } from "../utils/analytics";
import { spendingLines, spentCents, toCents } from "../utils/spending";
import { accountLabel, formatDay, formatMoney } from "../utils/format";
import { documentService } from "../utils/api";

const UPCOMING_DAYS = 30;
const TABS = [
  { key: "marked", label: "Marked" },
  { key: "summary", label: "Summary" },
  { key: "upcoming", label: "Upcoming" },
  { key: "all", label: "All payments" },
];

const lineKey = (line) => `${line.kind}-${line.id}`;

/* Marks line items as subscriptions (on) or takes the mark off, one at a time */
const setMarks = async (lines, on) => {
  for (const line of lines) {
    const save = line.kind === "statement_line" ? documentService.setTransactionSubscription : documentService.setItemSubscription;
    await save(line.id, on);
  }
};

/* The subscriptions the user has marked (on the Transactions page, or from the
   regular payments found here), and the payments which come round on a regular
   cadence: what they cost a month and a year, what is due soon, and which have
   stopped (perhaps cancelled) */
const Subscriptions = () => {
  const { lines, isLoading, error } = useFinanceData();
  const [openId, setOpenId] = useState(null);
  const [tab, setTab] = useTabs(TABS);

  /* What the server adds up from the marked line items: { subscriptions, monthly_total } */
  const [marked, setMarked] = useState(null);
  const [markedError, setMarkedError] = useState(null);
  /* Marks changed on this page since the line items were loaded, by line key */
  const [changedMarks, setChangedMarks] = useState({});
  const [busyId, setBusyId] = useState(null);

  const loadMarked = useCallback(() => {
    documentService
      .getSubscriptions()
      .then((data) => {
        setMarked(data);
        setMarkedError(null);
      })
      .catch((err) => {
        console.error("Failed to load the marked subscriptions", err);
        setMarkedError("Failed to load your marked subscriptions.");
      });
  }, []);

  useEffect(() => loadMarked(), [loadMarked]);

  const isMarked = (line) => changedMarks[lineKey(line)] ?? Boolean(line.is_subscription);

  /* Marks (or unmarks) every one of these line items, then shows the subscriptions as saved */
  const changeMarks = async (id, targets, on) => {
    setBusyId(id);
    setMarkedError(null);
    try {
      await setMarks(targets, on);
      setChangedMarks((prev) => ({ ...prev, ...Object.fromEntries(targets.map((t) => [lineKey(t), on])) }));
    } catch (err) {
      console.error("Failed to change the subscription marks", err);
      setMarkedError(err.serverMessage || "The subscription could not be changed. Please try again.");
    } finally {
      setBusyId(null);
      loadMarked();
    }
  };

  /* The line items behind a regular payment found from the history */
  const linesOf = (paymentId) => spendingLines(lines).filter((line) => payeeKey(line) === paymentId);
  const isPaymentMarked = (paymentId) => {
    const its = linesOf(paymentId);
    return its.length > 0 && its.every(isMarked);
  };
  const markedSubscriptions = marked?.subscriptions || [];
  const markedMonthly = marked ? toCents(marked.monthly_total) : 0;

  const today = useMemo(() => new Date(), []);
  const payments = useMemo(() => recurringPayments(lines, today), [lines, today]);
  const active = payments.filter((p) => !p.isLate);
  const stopped = payments.filter((p) => p.isLate);
  const monthly = active.reduce((sum, p) => sum + p.monthlyCents, 0);
  const horizon = isoDay(addDays(today, UPCOMING_DAYS));
  const upcoming = active.filter((p) => p.nextDate <= horizon).sort((a, b) => a.nextDate.localeCompare(b.nextDate));
  const dueSoon = upcoming.reduce((sum, p) => sum + p.typicalCents, 0);

  const opened = payments.find((p) => p.id === openId);
  const openedGroup = useMemo(() => {
    if (!opened) return null;
    const entries = spendingLines(lines)
      .filter((line) => payeeKey(line) === opened.id)
      .map((line) => ({ line, cents: spentCents(line) }));
    return { id: opened.id, name: opened.name, cents: entries.reduce((s, e) => s + e.cents, 0), entries };
  }, [opened, lines]);

  const slices = active.map((p) => ({ id: p.id, name: p.name, cents: p.monthlyCents }));

  return (
    <PageShell title="Subscriptions" subtitle="The payments you marked as subscriptions, the ones which come round on a schedule, and what they add up to">
      <PageStatus isLoading={isLoading} error={error} />
      {!isLoading && !error && (
        <section className="dashboard-panel analytics">
          <Tabs
            tabs={TABS.map((t) =>
              t.key === "upcoming" ? { ...t, badge: upcoming.length } : t.key === "marked" ? { ...t, badge: markedSubscriptions.length } : t
            )}
            active={tab}
            onSelect={setTab}
          />

          {tab === "marked" && (
            <TabPanel id="marked">
              {markedError && <p className="spending-warning">{markedError}</p>}
              {marked === null && !markedError ? (
                <p className="dashboard-panel-empty">Loading your marked subscriptions...</p>
              ) : markedSubscriptions.length === 0 ? (
                <Empty message="Nothing is marked as a subscription yet. Mark a charge with ☆ Subscription on the Transactions page, or mark one of the regular payments found under All payments." />
              ) : (
                <>
                  <div className="stat-grid">
                    <Stat label="Marked" value={String(markedSubscriptions.length)} detail="Subscriptions you flagged" />
                    <Stat label="A month" value={formatMoney(markedMonthly)} detail="At their latest prices" tone="neg" />
                    <Stat label="A year" value={formatMoney(markedMonthly * 12)} detail="At the same rate" />
                  </div>
                  <div className="chart-card chart-card-wide">
                    <div className="chart-card-head">
                      <h4>Your subscriptions</h4>
                    </div>
                    <div className="recurring-scroll">
                      <table className="recurring-table">
                        <thead>
                          <tr>
                            <th>Subscription</th>
                            <th className="num">Latest charge</th>
                            <th>Last charged</th>
                            <th>Next expected</th>
                            <th>Charges</th>
                            <th>Account</th>
                            <th aria-label="Unmark" />
                          </tr>
                        </thead>
                        <tbody>
                          {markedSubscriptions.map((sub) => (
                            <tr key={sub.name}>
                              <td>{sub.name}</td>
                              <td className="num">{formatMoney(toCents(sub.amount))}</td>
                              <td>{formatDay(sub.last_charged)}</td>
                              <td>{formatDay(sub.next_expected)}</td>
                              <td>{sub.charges}</td>
                              <td>{accountLabel(sub.account) || "-"}</td>
                              <td>
                                <button
                                  type="button"
                                  className="link-button"
                                  disabled={busyId !== null}
                                  onClick={() => changeMarks(`marked-${sub.name}`, sub.lines, false)}
                                >
                                  {busyId === `marked-${sub.name}` ? "Unmarking..." : "Unmark"}
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="spending-note">
                      Charges you marked as subscriptions, one row for each thing paid for. The next charge is expected a month after the last.
                    </p>
                  </div>
                </>
              )}
            </TabPanel>
          )}

          {tab !== "marked" && payments.length === 0 ? (
            <Empty message="No regular payments found yet. A payee paid at least three times on a steady schedule (weekly, monthly, yearly) shows up here." />
          ) : (
            <>
              {tab === "summary" && (
                <TabPanel id="summary">
                  <div className="stat-grid">
                    <Stat label="Active" value={String(active.length)} detail="Still being paid" />
                    <Stat label="A month" value={formatMoney(monthly)} detail="All active, averaged to a month" tone="neg" />
                    <Stat label="A year" value={formatMoney(monthly * 12)} detail="At the same rate" />
                    <Stat
                      label={`Due in ${UPCOMING_DAYS} days`}
                      value={formatMoney(dueSoon)}
                      detail={`${upcoming.length} ${upcoming.length === 1 ? "payment" : "payments"}`}
                    />
                    <Stat label="Overdue" value={String(stopped.length)} detail={stopped.length ? "Not paid when expected: cancelled?" : "None"} />
                  </div>
                  <div className="chart-card chart-card-wide">
                    <div className="chart-card-head">
                      <h4>What they cost a month</h4>
                    </div>
                    <CategoryBars slices={slices} onSelect={(s) => setOpenId(s.id)} />
                    <p className="spending-note">Click one to see every payment. Overdue ones are left out.</p>
                  </div>
                </TabPanel>
              )}

              {tab === "upcoming" && (
                <TabPanel id="upcoming">
                  <div className="chart-card chart-card-wide">
                    <div className="chart-card-head">
                      <h4>Due in the next {UPCOMING_DAYS} days</h4>
                    </div>
                    {upcoming.length === 0 ? (
                      <p className="dashboard-panel-empty">Nothing is expected in the next {UPCOMING_DAYS} days.</p>
                    ) : (
                      <ul className="upcoming-list">
                        {upcoming.map((p) => (
                          <li key={p.id}>
                            <span className="upcoming-date">{formatDay(p.nextDate)}</span>
                            <span className="upcoming-name">{p.name}</span>
                            <strong>{formatMoney(p.typicalCents)}</strong>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </TabPanel>
              )}

              {tab === "all" && (
                <TabPanel id="all">
                  <div className="chart-card chart-card-wide">
                    <div className="chart-card-head">
                      <h4>All regular payments</h4>
                    </div>
                    <div className="recurring-scroll">
                      <table className="recurring-table">
                        <thead>
                          <tr>
                            <th>Payee</th>
                            <th>How often</th>
                            <th className="num">Usually</th>
                            <th className="num">A month</th>
                            <th className="num">A year</th>
                            <th>Last paid</th>
                            <th>Next expected</th>
                            <th>Subscription</th>
                          </tr>
                        </thead>
                        <tbody>
                          {payments.map((p) => (
                            <tr key={p.id} className={p.isLate ? "is-late" : ""}>
                              <td>
                                <button type="button" className="link-button" onClick={() => setOpenId(p.id)}>
                                  {p.name}
                                </button>
                              </td>
                              <td>
                                {p.cadence} <span className="spending-hint">({p.count} times)</span>
                              </td>
                              <td className="num">{formatMoney(p.typicalCents)}</td>
                              <td className="num">{formatMoney(p.monthlyCents)}</td>
                              <td className="num">{formatMoney(p.monthlyCents * 12)}</td>
                              <td>{formatDay(p.lastDate)}</td>
                              <td>{p.isLate ? "Overdue: cancelled?" : formatDay(p.nextDate)}</td>
                              <td>
                                {isPaymentMarked(p.id) ? (
                                  <span className="spending-hint">★ Marked</span>
                                ) : (
                                  <button
                                    type="button"
                                    className="link-button"
                                    disabled={busyId !== null}
                                    onClick={() => changeMarks(`found-${p.id}`, linesOf(p.id).filter((l) => !isMarked(l)), true)}
                                  >
                                    {busyId === `found-${p.id}` ? "Marking..." : "Mark as subscription"}
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="spending-note">Found from all of your history. Overdue ones are left out of the monthly total.</p>
                  </div>
                </TabPanel>
              )}
            </>
          )}
        </section>
      )}
      {openedGroup && <GroupDetailModal group={openedGroup} flow="out" onClose={() => setOpenId(null)} />}
    </PageShell>
  );
};

export default Subscriptions;
