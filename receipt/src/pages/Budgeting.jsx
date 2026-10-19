import React, { useEffect, useMemo, useState } from "react";
import PageShell, { PageStatus } from "../components/PageShell";
import BudgetManager from "../components/BudgetManager";
import BudgetInsights from "../components/BudgetInsights";
import { TabPanel, Tabs, useTabs } from "../components/Tabs";
import { useFinanceData } from "../hooks/useFinanceData";
import { documentService } from "../utils/api";
import { addMonths, buildScopes, currentMonthKey, monthRange, monthlyTotals, scopeStats } from "../utils/budgeting";

/* Targets for monthly spending, overall and by tag, against the spending and
   where it is heading */
const Budgeting = () => {
  const { lines, tags, isLoading, error } = useFinanceData();
  const [budgets, setBudgets] = useState(null);
  const [budgetError, setBudgetError] = useState(null);
  const [windowMonths, setWindowMonths] = useState(6);
  const [focusId, setFocusId] = useState("overall");
  const nowKey = currentMonthKey();
  const [monthKey, setMonthKey] = useState(nowKey);

  useEffect(() => {
    let isMounted = true;
    documentService
      .getBudgets()
      .then((data) => isMounted && setBudgets(data || []))
      .catch(() => isMounted && setBudgetError("Failed to load your budgets."));
    return () => {
      isMounted = false;
    };
  }, []);

  /* the completed months to fit, and this one */
  const completed = useMemo(() => monthRange(addMonths(nowKey, -1), windowMonths), [nowKey, windowMonths]);
  const monthKeys = useMemo(() => [...completed, nowKey], [completed, nowKey]);

  const scopes = useMemo(() => buildScopes(budgets || [], tags), [budgets, tags]);
  const totals = useMemo(() => monthlyTotals(lines, scopes, monthKeys), [lines, scopes, monthKeys]);
  const stats = useMemo(() => scopeStats(scopes, totals, completed), [scopes, totals, completed]);

  /* how many targets need spending to come down: shown on the tab which says what to do */
  const needCutting = stats.filter((s) => s.reduceCents > 0).length;
  const tabs = [
    { key: "actions", label: "What to do", badge: needCutting },
    { key: "chart", label: "Spending by month" },
    { key: "stats", label: "How spending is changing" },
    { key: "targets", label: "Targets" },
  ];
  const [tab, setTab] = useTabs(tabs);

  const insight = {
    stats,
    totals,
    windowMonths,
    onWindow: (n) => {
      setWindowMonths(n);
      setMonthKey(nowKey);
    },
    focusId,
    onFocus: setFocusId,
    monthKey,
    onMonth: setMonthKey,
    monthKeys,
  };

  const ready = !isLoading && !error && budgets;
  return (
    <PageShell title="Budgeting" subtitle="Set monthly targets, and see whether your spending is on course to meet them">
      <PageStatus isLoading={isLoading || (!budgets && !budgetError)} error={error || budgetError} />
      {ready && (
        <section className="dashboard-panel analytics">
          <Tabs tabs={tabs} active={tab} onSelect={setTab} />
          {tab === "targets" ? (
            <TabPanel id="targets">
              <BudgetManager budgets={budgets} setBudgets={setBudgets} tags={tags} stats={stats} totals={totals} />
            </TabPanel>
          ) : (
            <TabPanel id={tab}>
              <BudgetInsights part={tab} {...insight} />
            </TabPanel>
          )}
        </section>
      )}
    </PageShell>
  );
};

export default Budgeting;
