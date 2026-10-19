import React, { useMemo, useState } from "react";
import PageShell, { PageStatus } from "../components/PageShell";
import PeriodFilter, { describePeriod } from "../components/PeriodFilter";
import { FilterToggle, TabPanel, Tabs, useTabs } from "../components/Tabs";
import { Empty, Pills, Stat } from "../components/AnalyticsBits";
import { StackedColumns } from "../components/Charts";
import { DocumentTree, TransactionList } from "../components/DocumentTimeline";
import { useFinanceData } from "../hooks/useFinanceData";
import { usePeriod } from "../hooks/usePeriod";
import { banksIn, bankOf } from "../utils/grouping";
import { MODES, buildDocuments, histogram, timelineNodes } from "../utils/documentTimeline";

const GRANULARITIES = [
  { key: "auto", label: "Auto" },
  { key: "day", label: "Day" },
  { key: "week", label: "Week" },
  { key: "month", label: "Month" },
];

const TABS = [
  { key: "histogram", label: "Histogram" },
  { key: "timeline", label: "Timeline" },
];

/* Receipt items which were matched to a statement line are that line's money,
   so a list of transactions has them once, as the statement line */
const isTransaction = (line) => line.kind === "statement_line" || !line.matched;

/* Statements and receipts against a timeline, as a histogram and as a tree: the
   statements are the main entries, the receipts consolidated into them branch off
   them, and the ones which are not stand alone. */
const TimelineTree = () => {
  const { lines, accounts, documents, isLoading, error } = useFinanceData();
  const periodState = usePeriod("6m");
  const { period } = periodState;
  const [mode, setMode] = useState("both");
  const [bank, setBank] = useState("all");
  const [granularity, setGranularity] = useState("auto");
  const [tab, setTab] = useTabs(TABS);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const built = useMemo(() => buildDocuments(documents, lines, accounts), [documents, lines, accounts]);
  const banks = useMemo(() => banksIn(lines.filter((l) => l.kind === "statement_line")), [lines]);
  const filters = useMemo(() => ({ from: period.from, to: period.to, bank }), [period.from, period.to, bank]);

  const nodes = useMemo(() => timelineNodes(built, mode, filters), [built, mode, filters]);
  const transactions = useMemo(
    () =>
      lines
        .filter(isTransaction)
        .filter((l) => (!period.from || l.date >= period.from) && (!period.to || l.date <= period.to))
        .filter((l) => bank === "all" || bankOf(l) === bank),
    [lines, period.from, period.to, bank]
  );
  const chart = useMemo(
    () => histogram(nodes, mode, { from: period.from, to: period.to }, granularity, transactions),
    [nodes, mode, period.from, period.to, granularity, transactions]
  );

  const statementCount = nodes.filter((n) => n.kind === "statement").length;
  const receiptNodes = nodes.filter((n) => n.kind !== "statement");
  const consolidated = nodes.filter((n) => n.kind === "statement").reduce((sum, s) => sum + s.children.length, 0) + receiptNodes.filter((r) => r.isConsolidated).length;
  const unconsolidated = receiptNodes.filter((r) => !r.isConsolidated && r.kind === "receipt").length;
  const isEmpty = mode === "transactions" ? transactions.length === 0 : nodes.length === 0;

  return (
    <PageShell title="Timeline Tree" subtitle="Your statements and receipts through time, and how they fit together">
      <PageStatus isLoading={isLoading} error={error} />
      {!isLoading && !error && (
        <section className="dashboard-panel analytics">
          <Tabs
            tabs={TABS}
            active={tab}
            onSelect={setTab}
            actions={
              <FilterToggle
                isOpen={filtersOpen}
                onToggle={() => setFiltersOpen(!filtersOpen)}
                summary={`${describePeriod(periodState)} · ${MODES.find((m) => m.key === mode).label} · ${bank === "all" ? "All banks" : banks.find((b) => b.key === bank)?.label || bank}`}
              />
            }
          />

          {filtersOpen && (
            <div className="analytics-filters">
              <PeriodFilter state={periodState} />
              <div className="spending-group">
                <span className="spending-label">Show</span>
                <Pills options={MODES} value={mode} onChange={setMode} label="What to show" />
                <p className="spending-hint">
                  {mode === "statements"
                    ? "Only the bank statements."
                    : mode === "both"
                      ? "Statements, with the receipts matched to them under each, and the receipts which are not matched on their own."
                      : "Only transactions: every line of money in or out, with no statements or receipts."}
                </p>
                <span className="spending-label">Bank</span>
                <select className="analytics-select" value={bank} onChange={(e) => setBank(e.target.value)} aria-label="Bank">
                  <option value="all">All banks</option>
                  {banks.map((b) => (
                    <option key={b.key} value={b.key}>
                      {b.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {tab === "histogram" && (
            <TabPanel id="histogram">
              {mode !== "transactions" && (
                <div className="stat-grid">
                  <Stat label="Statements" value={String(statementCount)} detail="In this period" />
                  {mode === "both" && (
                    <>
                      <Stat label="Consolidated receipts" value={String(consolidated)} detail="Matched to a statement line" tone="pos" />
                      <Stat label="Unconsolidated receipts" value={String(unconsolidated)} detail={unconsolidated ? "Waiting to be matched on Review" : "All matched"} />
                    </>
                  )}
                </div>
              )}
              <div className="chart-card chart-card-wide">
                <div className="chart-card-head">
                  <h4>{mode === "transactions" ? "Transactions" : "Uploads"} over time</h4>
                  <Pills options={GRANULARITIES} value={granularity} onChange={setGranularity} label="Time unit" />
                </div>
                {isEmpty || chart.points.length === 0 ? (
                  <Empty message="Nothing here in this period." action={period.key !== "all" ? { label: "Show all time", run: () => periodState.choosePreset("all") } : null} />
                ) : (
                  <StackedColumns
                    points={chart.points}
                    series={chart.series}
                    label="Statements and receipts over time"
                    counts
                    format={(n) => String(n)}
                  />
                )}
                <p className="spending-note">
                  {mode === "transactions"
                    ? "How many transactions there were in each period."
                    : "A statement is dated by its last line, a receipt by its date. Counts, not amounts: a consolidated receipt is part of its statement's spending."}
                </p>
              </div>
            </TabPanel>
          )}

          {tab === "timeline" && (
            <TabPanel id="timeline">
              <div className="chart-card chart-card-wide">
                <div className="chart-card-head">
                  <h4>{mode === "transactions" ? "All transactions" : "Statements and receipts"}</h4>
                  <Pills options={MODES} value={mode} onChange={setMode} label="What to show" />
                </div>
                {mode === "transactions" ? <TransactionList lines={transactions} /> : <DocumentTree nodes={nodes} showReceipts={mode === "both"} />}
              </div>
            </TabPanel>
          )}
        </section>
      )}
    </PageShell>
  );
};

export default TimelineTree;
