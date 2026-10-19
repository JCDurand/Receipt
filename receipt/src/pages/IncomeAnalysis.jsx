import React from "react";
import PageShell, { PageStatus } from "../components/PageShell";
import AnalysisPage from "../components/AnalysisPage";
import { useFinanceData } from "../hooks/useFinanceData";

/* Where the money came from: credits into the accounts grouped by payer or tag, and over time */
const IncomeAnalysis = () => {
  const { lines, tags, isLoading, error } = useFinanceData();
  return (
    <PageShell title="Income Analysis" subtitle="Your employers and other payers: what was paid into your accounts, and when">
      <PageStatus isLoading={isLoading} error={error} />
      {!isLoading && !error && <AnalysisPage flow="in" lines={lines} tags={tags} />}
    </PageShell>
  );
};

export default IncomeAnalysis;
