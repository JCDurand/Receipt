import React from "react";
import Navbar from "./Navbar";
import { usePageTitle } from "./PageTitle";
import "../styles/Dashboard.css";
import "../styles/DashboardSections.css";
import "../styles/Analytics.css";
import "../styles/Insights.css";

/* The frame of each dashboard page: the navbar, what the page is about and what it shows.
   The title appears in the preferences bar across the top. */
const PageShell = ({ title, subtitle, children }) => {
  usePageTitle(title);
  return (
    <>
      <Navbar />
      <div className="container dashboard-view">
        <div className="dashboard-container">
          {subtitle && (
            <div className="dashboard-header">
              <p>{subtitle}</p>
            </div>
          )}
          {children}
        </div>
      </div>
    </>
  );
};

/* What a page shows while its data loads, or when it could not */
export const PageStatus = ({ isLoading, error }) =>
  isLoading ? (
    <p className="dashboard-section">Loading your data...</p>
  ) : error ? (
    <p className="dashboard-section" style={{ color: "#ff6b6b" }}>{error}</p>
  ) : null;

export default PageShell;
