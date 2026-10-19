import React from "react";
import PageShell, { PageStatus } from "../components/PageShell";
import AnalysisPage from "../components/AnalysisPage";
import { useFinanceData } from "../hooks/useFinanceData";

/* Where the money went: expenses grouped by merchant or tag, and over time */
const ExpenseAnalysis = () => {
  const { lines, tags, isLoading, error } = useFinanceData();
  return (
    <PageShell title="Expense Analysis" subtitle="Where your money goes, by merchant and by tag, and when">
      <PageStatus isLoading={isLoading} error={error} />
      {!isLoading && !error && <AnalysisPage flow="out" lines={lines} tags={tags} />}
    </PageShell>
  );
};

export default ExpenseAnalysis;
