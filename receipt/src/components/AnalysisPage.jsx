import React, { useMemo, useState } from "react";
import { CategoryBars, PieChart, StackedBars, StackedColumns } from "./Charts";
import { Empty, MultiPills, Pills, Stat } from "./AnalyticsBits";
import GroupDetailModal from "./GroupDetailModal";
import PeriodFilter, { describePeriod } from "./PeriodFilter";
import { FilterToggle, TabPanel, Tabs, useTabs } from "./Tabs";
import { usePeriod } from "../hooks/usePeriod";
import { change, downloadCsv, previousPeriod, toCsv } from "../utils/analytics";
import { banksIn, centsFor, countedLines, groupLines, groupsOverTime } from "../utils/grouping";
import { formatMoney, getCurrency } from "../utils/format";

const CHARTS = [
  { key: "donut", label: "Donut" },
  { key: "pie", label: "Pie" },
  { key: "bars", label: "Bars" },
];
const GRANULARITIES = [
  { key: "auto", label: "Auto" },
  { key: "day", label: "Day" },
  { key: "week", label: "Week" },
  { key: "month", label: "Month" },
];

const TABS = [
  { key: "breakdown", label: "Breakdown" },
  { key: "time", label: "Over time" },
  { key: "list", label: "All groups" },
];

/* What differs between money out and money in */
const WORDS = {
  out: {
    noun: "Spending",
    verb: "Spent",
    merchant: "Merchant",
    merchants: "merchants",
    merchantsLong: "Where the money went",
    none: "No spending in this period.",
  },
  in: {
    noun: "Income",
    verb: "Received",
    merchant: "Payer",
    merchants: "payers",
    merchantsLong: "Where the money came from",
    none: "No income in this period.",
  },
};

/**
 * Charts of money out (the Expense Analysis page) or money in (Income
 * Analysis): the same line items grouped by merchant or payer, or by tag
 * (with other tags, or merchants, as labels inside each group), as a donut, a
 * pie or bars, and the groups against dates. Any group can be opened to see its
 * line items.
 */
const AnalysisPage = ({ flow, lines, tags }) => {
  const words = WORDS[flow];
  const periodState = usePeriod("3m");
  const { period } = periodState;

  const [bank, setBank] = useState("all");
  const [groupBy, setGroupBy] = useState("merchant");
  const [tagIds, setTagIds] = useState([]);
  const [labelBy, setLabelBy] = useState("none");
  const [labelTagIds, setLabelTagIds] = useState([]);
  const [chart, setChart] = useState("donut");
  const [granularity, setGranularity] = useState("auto");
  const [selectedId, setSelectedId] = useState(null);
  const [tab, setTab] = useTabs(TABS);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const banks = useMemo(() => banksIn(lines.filter((l) => centsFor(flow, l) > 0)), [lines, flow]);
  const options = useMemo(
    () => ({ flow, from: period.from, to: period.to, bank, groupBy, tagIds, labelBy, labelTagIds }),
    [flow, period.from, period.to, bank, groupBy, tagIds, labelBy, labelTagIds]
  );
  /* the charts have eight colours, so past that the rest are one "Other"; the list below keeps more */
  const result = useMemo(() => groupLines(lines, tags, { ...options, maxGroups: 8 }), [lines, tags, options]);
  const listed = useMemo(() => groupLines(lines, tags, { ...options, maxGroups: 40 }), [lines, tags, options]);
  const overTime = useMemo(() => groupsOverTime(result.groups, period, granularity), [result.groups, period, granularity]);
  const before = useMemo(() => {
    const previous = previousPeriod({ from: period.from, to: period.to });
    if (!previous) return null;
    return countedLines(lines, { flow, bank, ...previous }).reduce((sum, l) => sum + centsFor(flow, l), 0);
  }, [lines, flow, bank, period.from, period.to]);

  const selected = [...result.groups, ...listed.groups].find((g) => g.id === selectedId) || null;
  const biggest = result.groups[0];
  const isTag = groupBy === "tag";
  const groupNoun = isTag ? "tag" : words.merchant.toLowerCase();

  const toggle = (setter) => (id) => setter((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const chooseGroupBy = (key) => {
    setGroupBy(key);
    /* a label of the same kind as the groups would only repeat them */
    if (key === "merchant" && labelBy === "merchant") setLabelBy("none");
    setSelectedId(null);
  };
  const labelOptions = [
    { key: "none", label: "Nothing" },
    ...(isTag ? [{ key: "merchant", label: words.merchant }] : []),
    { key: "tag", label: "Other tags" },
  ];

  /* nothing here: say why, and offer the period which has something */
  const why = useMemo(() => {
    if (result.count > 0) return null;
    const ever = countedLines(lines, { flow, bank });
    if (ever.length === 0) {
      return { message: lines.length === 0 ? "There are no line items yet. Upload a statement or a receipt to get started." : words.none };
    }
    if (tagIds.length) {
      return { message: `${words.none} Nothing is tagged ${tagIds.length === 1 ? "that" : "with those tags"} in it.`, action: { label: "Clear the tags", run: () => setTagIds([]) } };
    }
    return { message: `${words.none} There is some at other times.`, action: { label: "Show all time", run: () => periodState.choosePreset("all") } };
  }, [result.count, lines, flow, bank, tagIds.length, words.none, periodState]);

  const exportGroups = () =>
    downloadCsv(
      `newspeak-${flow === "in" ? "income" : "expenses"}-by-${groupBy}-${period.from || "start"}_to_${period.to || "today"}.csv`,
      toCsv([
        [isTag ? "Tag" : words.merchant, `Total (${getCurrency()})`, "Line items", "Share"],
        ...result.groups.map((g) => [g.name, (g.cents / 100).toFixed(2), g.count, `${((g.cents / (result.totalCents || 1)) * 100).toFixed(1)}%`]),
      ])
    );

  const bankName = bank === "all" ? "All banks" : banks.find((b) => b.key === bank)?.label || bank;
  const filterSummary = `${describePeriod(periodState)} · ${bankName} · by ${groupBy === "tag" ? "tag" : words.merchant.toLowerCase()}`;

  return (
    <section className="dashboard-panel analytics">
      <Tabs
        tabs={TABS}
        active={tab}
        onSelect={setTab}
        actions={
          <div className="analytics-exports">
            <button type="button" className="spending-pill" disabled={result.groups.length === 0} onClick={exportGroups}>
              Export groups (CSV)
            </button>
            <FilterToggle isOpen={filtersOpen} onToggle={() => setFiltersOpen(!filtersOpen)} summary={filterSummary} />
          </div>
        }
      />

      {filtersOpen && (
        <div className="analytics-filters">
          <PeriodFilter state={periodState} />
          <div className="spending-group">
            <span className="spending-label">Bank</span>
            <select className="analytics-select" value={bank} onChange={(e) => setBank(e.target.value)} aria-label="Bank">
              <option value="all">All banks</option>
              {banks.map((b) => (
                <option key={b.key} value={b.key}>
                  {b.label}
                </option>
              ))}
            </select>
            <span className="spending-label">Group by</span>
            <Pills
              options={[
                { key: "merchant", label: words.merchant },
                { key: "tag", label: "Tag" },
              ]}
              value={groupBy}
              onChange={chooseGroupBy}
              label="Group by"
            />
          </div>
          <div className="spending-group">
            {isTag && (
              <>
                <span className="spending-label">Tags to group by</span>
                <MultiPills
                  options={tags}
                  chosen={tagIds}
                  onToggle={toggle(setTagIds)}
                  label="Tags to group by"
                  empty="There are no tags to choose from yet."
                />
                <p className="spending-hint">
                  {tagIds.length === 0 ? "With none chosen, every tag is a group." : "Only these tags (and the tags beneath them) make groups."}
                </p>
              </>
            )}
            <span className="spending-label">Label each group with</span>
            <Pills options={labelOptions} value={labelBy} onChange={setLabelBy} label="Label each group with" />
            {labelBy === "tag" && (
              <>
                <MultiPills
                  options={tags}
                  chosen={labelTagIds}
                  onToggle={toggle(setLabelTagIds)}
                  label="Tags to label with"
                  empty="There are no tags to choose from yet."
                />
                <p className="spending-hint">{labelTagIds.length === 0 ? "With none chosen, every other tag is a label." : "Only these tags are labels."}</p>
              </>
            )}
            {labelBy !== "none" && <p className="spending-hint">Labels divide each bar of the Bars chart.</p>}
          </div>
        </div>
      )}

      {tab === "breakdown" && (
        <TabPanel id="breakdown">
          <div className="stat-grid">
            <Stat
              label={words.verb}
              value={formatMoney(result.totalCents)}
              detail={`${result.count} line ${result.count === 1 ? "item" : "items"}`}
              delta={before != null ? change(result.totalCents, before) : null}
              upIsGood={flow === "in"}
              tone={flow === "in" ? "pos" : undefined}
            />
            <Stat label={isTag ? "Tags" : words.merchants[0].toUpperCase() + words.merchants.slice(1)} value={String(result.groups.length)} detail="Groups on the charts" />
            <Stat
              label={`Biggest ${groupNoun}`}
              value={biggest ? formatMoney(biggest.cents) : "-"}
              detail={biggest ? `${biggest.name} · ${Math.round((biggest.cents / (result.totalCents || 1)) * 100)}%` : "Nothing here"}
            />
            <Stat label="Average line item" value={formatMoney(result.count ? Math.round(result.totalCents / result.count) : 0)} detail="Across the groups" />
          </div>
          <div className="chart-card chart-card-wide">
            <div className="chart-card-head">
              <h4>
                {words.noun} by {groupNoun}
              </h4>
              <Pills options={CHARTS} value={chart} onChange={setChart} label="Chart type" />
            </div>
            {why ? (
              <Empty {...why} />
            ) : chart === "bars" ? (
              <StackedBars groups={result.groups} labels={result.labels} onSelect={(g) => setSelectedId(g.id)} />
            ) : (
              <PieChart slices={result.groups} donut={chart === "donut"} onSelect={(g) => setSelectedId(g.id)} />
            )}
            <p className="spending-note">
              Click {isTag ? "a tag" : `a ${words.merchant.toLowerCase()}`} to see its line items.
              {isTag && " A line item with several tags is shared evenly between them."}
            </p>
          </div>
        </TabPanel>
      )}

      {tab === "time" && (
        <TabPanel id="time">
          <div className="chart-card chart-card-wide">
            <div className="chart-card-head">
              <h4>
                {words.noun} over time, by {groupNoun}
              </h4>
              <Pills options={GRANULARITIES} value={granularity} onChange={setGranularity} label="Time unit" />
            </div>
            {why || overTime.points.length === 0 ? (
              <Empty {...(why || { message: words.none })} />
            ) : (
              <StackedColumns
                points={overTime.points}
                series={overTime.series}
                label={`${words.noun} over time by ${groupNoun}`}
                onSelect={(s) => setSelectedId(s.id)}
              />
            )}
            <p className="spending-note">Click a {isTag ? "tag" : words.merchant.toLowerCase()} in the key to see its line items.</p>
          </div>
        </TabPanel>
      )}

      {tab === "list" && (
        <TabPanel id="list">
          <div className="chart-card chart-card-wide">
            <div className="chart-card-head">
              <h4>{isTag ? "Tags" : words.merchantsLong}</h4>
              <span className="spending-hint">Biggest first</span>
            </div>
            {why ? <Empty {...why} /> : <CategoryBars slices={listed.groups} onSelect={(g) => setSelectedId(g.id)} />}
          </div>
        </TabPanel>
      )}

      {selected && <GroupDetailModal group={selected} flow={flow} onClose={() => setSelectedId(null)} />}
    </section>
  );
};

export default AnalysisPage;
