import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import PageShell, { PageStatus } from "../components/PageShell";
import PeriodFilter, { describePeriod } from "../components/PeriodFilter";
import { FilterToggle, TabPanel, Tabs, useTabs } from "../components/Tabs";
import ConversionBadge from "../components/ConversionBadge";
import { Empty, Pills, Stat } from "../components/AnalyticsBits";
import { GroupedBarChart, SERIES_COLORS } from "../components/Charts";
import { RecentUploads } from "../components/RecentActivity";
import AccountHistory from "../components/AccountHistory";
import { documentService } from "../utils/api";
import { useFinanceData } from "../hooks/useFinanceData";
import { usePeriod } from "../hooks/usePeriod";
import { cashFlow, change, incomeLines, previousPeriod, receivedCents, summarise } from "../utils/analytics";
import { spendingLines, spentCents, toCents } from "../utils/spending";
import { formatDay, formatMoney } from "../utils/format";

const GRANULARITIES = [
  { key: "auto", label: "Auto" },
  { key: "day", label: "Day" },
  { key: "week", label: "Week" },
  { key: "month", label: "Month" },
];
const LARGEST = 8;
const TABS = [
  { key: "summary", label: "Summary" },
  { key: "balance", label: "Account balances" },
  { key: "expenses", label: "Largest expenses" },
  { key: "income", label: "Largest income" },
  { key: "uploads", label: "Recent uploads" },
];
/* the tabs which are about the period chosen; the uploads are the latest, whenever */
const PERIOD_TABS = ["summary", "balance", "expenses", "income"];

/* The biggest line items of one kind in the period, biggest first */
const LargestList = ({ title, hint, lines, cents, tone, emptyText }) => {
  const biggest = [...lines].sort((a, b) => cents(b) - cents(a)).slice(0, LARGEST);
  return (
    <section className="dashboard-panel">
      <h3 className="dashboard-panel-title">{title}</h3>
      {biggest.length === 0 ? (
        <p className="dashboard-panel-empty">{emptyText}</p>
      ) : (
        <ul className="activity-log scroll-area">
          {biggest.map((line) => (
            <li key={`${line.kind}-${line.id}`} className={`activity-row ${tone === "is-negative" ? "line-tint-debit" : "line-tint-credit"}`}>
              <div className="activity-main">
                <span className="activity-name" title={line.display_name || line.description}>
                  {line.display_name || line.description || line.merchant || "-"}
                </span>
                <span className="activity-meta">
                  {formatDay(line.date)}
                  {line.source && (
                    <>
                      {" · "}
                      <Link to={`/uploads/${line.source.category}/${line.source.id}`}>{line.source.name}</Link>
                    </>
                  )}
                </span>
              </div>
              <strong className={`activity-amount line-amount ${tone === "is-negative" ? "is-debit" : "is-credit"}`}>
                {formatMoney(cents(line))} <ConversionBadge line={line} />
              </strong>
            </li>
          ))}
        </ul>
      )}
      <p className="spending-note">{hint}</p>
    </section>
  );
};

/* The overall picture: what came in and went out over a period of your choosing, the
   balance of your accounts through it, what was uploaded last, and the biggest
   expenses and income */
const Dashboard = () => {
  const { lines, accounts, documents, isLoading, error } = useFinanceData();
  const periodState = usePeriod("3m");
  const { period } = periodState;
  const [granularity, setGranularity] = useState("auto");
  const [tab, setTab] = useTabs(TABS);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const filters = useMemo(() => ({ from: period.from, to: period.to }), [period.from, period.to]);
  const summary = useMemo(() => summarise(lines, { ...filters, flow: "out" }), [lines, filters]);
  const before = useMemo(() => {
    const previous = previousPeriod(filters);
    return previous ? summarise(lines, { ...previous, flow: "out" }) : null;
  }, [lines, filters]);
  const flow = useMemo(() => cashFlow(lines, filters, granularity), [lines, filters, granularity]);
  const expenses = useMemo(() => spendingLines(lines, filters), [lines, filters]);
  const income = useMemo(() => incomeLines(lines, filters), [lines, filters]);

  /* Every account's balance through time, from its opening balance and its documents */
  const [history, setHistory] = useState(null);
  useEffect(() => {
    let isMounted = true;
    documentService
      .getAccountHistory()
      .then((data) => isMounted && setHistory(data))
      .catch((err) => console.error("Failed to load the account balances", err));
    return () => {
      isMounted = false;
    };
  }, []);
  /* what the accounts hold now, together, in the user's currency */
  const balanceNow = (accounts || []).reduce((sum, a) => sum + toCents(a.balance_converted ?? a.funds_converted ?? a.funds), 0);

  const flowPoints = flow.points.map((p) => ({
    ...p,
    short: flow.granularity === "month" ? p.label.split(" ")[0] : p.label.replace("Week of ", ""),
  }));
  const hasMovement = flowPoints.some((p) => p.inCents > 0 || p.outCents > 0);
  const uploads = useMemo(() => documents.filter((d) => d.category === "statement" || d.category === "receipt"), [documents]);

  return (
    <PageShell title="Overview" subtitle="Everything coming in and going out, across all of your accounts">
      <PageStatus isLoading={isLoading} error={error} />
      {!isLoading && !error && (
        <section className="dashboard-panel analytics">
          <Tabs
            tabs={TABS}
            active={tab}
            onSelect={setTab}
            actions={
              PERIOD_TABS.includes(tab) && (
                <FilterToggle isOpen={filtersOpen} onToggle={() => setFiltersOpen(!filtersOpen)} summary={describePeriod(periodState)} />
              )
            }
          />
          {filtersOpen && PERIOD_TABS.includes(tab) && (
            <div className="analytics-filters">
              <PeriodFilter state={periodState} />
            </div>
          )}

          {tab === "summary" && (
            <TabPanel id="summary">
              <div className="stat-grid">
                <Stat
                  label="Income"
                  value={formatMoney(summary.incomeCents)}
                  detail="Credits into your accounts"
                  tone="pos"
                  delta={before ? change(summary.incomeCents, before.incomeCents) : null}
                  upIsGood
                />
                <Stat
                  label="Expenses"
                  value={formatMoney(summary.spentCents)}
                  detail={`${summary.count} line ${summary.count === 1 ? "item" : "items"}`}
                  delta={before ? change(summary.spentCents, before.spentCents) : null}
                />
                <Stat
                  label="Net"
                  value={formatMoney(summary.netCents)}
                  detail={summary.incomeCents > 0 ? `${summary.netCents >= 0 ? "Saved" : "Overspent"} · ${Math.round((summary.netCents / summary.incomeCents) * 100)}% of income` : summary.netCents >= 0 ? "Saved" : "Overspent"}
                  tone={summary.netCents >= 0 ? "pos" : "neg"}
                />
                <Stat
                  label="Balance now"
                  value={formatMoney(balanceNow)}
                  detail={`${accounts.length} ${accounts.length === 1 ? "account" : "accounts"}`}
                  tone={balanceNow < 0 ? "neg" : undefined}
                />
              </div>
              <div className="chart-card chart-card-wide">
                <div className="chart-card-head">
                  <h4>Income and expenses</h4>
                  <Pills options={GRANULARITIES} value={granularity} onChange={setGranularity} label="Group by" />
                </div>
                {!hasMovement ? (
                  <Empty
                    message={lines.length === 0 ? "There are no line items yet. Upload a statement or a receipt to get started." : "Nothing moved in this period."}
                    action={lines.length > 0 && period.key !== "all" ? { label: "Show all time", run: () => periodState.choosePreset("all") } : null}
                  />
                ) : (
                  <GroupedBarChart
                    points={flowPoints}
                    label="Income and expenses over time"
                    series={[
                      { field: "inCents", name: "Income", color: SERIES_COLORS[2] },
                      { field: "outCents", name: "Expenses", color: SERIES_COLORS[1] },
                    ]}
                    extra={(p) => [`Net: ${formatMoney(p.netCents)}`]}
                  />
                )}
              </div>
            </TabPanel>
          )}

          {tab === "balance" && (
            <TabPanel id="balance">
              {history ? <AccountHistory history={history} period={period} /> : <p className="dashboard-panel-empty">Loading your account balances...</p>}
            </TabPanel>
          )}

          {tab === "expenses" && (
            <TabPanel id="expenses">
              <LargestList
                title="Largest expenses"
                hint="In the period chosen, biggest first."
                lines={expenses}
                cents={spentCents}
                tone="is-negative"
                emptyText="No expenses in this period."
              />
            </TabPanel>
          )}

          {tab === "income" && (
            <TabPanel id="income">
              <LargestList
                title="Largest income"
                hint="In the period chosen, biggest first."
                lines={income}
                cents={receivedCents}
                tone=""
                emptyText="No income in this period."
              />
            </TabPanel>
          )}

          {tab === "uploads" && (
            <TabPanel id="uploads">
              <RecentUploads documents={uploads} count={15} />
            </TabPanel>
          )}
        </section>
      )}
    </PageShell>
  );
};

export default Dashboard;
