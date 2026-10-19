import { Link } from "react-router-dom";
import ConversionBadge from "./ConversionBadge";
import { formatDateTime, formatDay, formatMoney } from "../utils/format";
import { toCents } from "../utils/spending";
import "../styles/DashboardSections.css";
import "../styles/TagPicker.css";

const RECENT_COUNT = 25;

const CATEGORY_LABELS = { statement: "Statement", receipt: "Receipt", cash: "Cash" };

const newestFirst = (a, b) => (b || "").localeCompare(a || "");

/* The most recently uploaded documents, newest first, and how many line items
   were read from each */
export const RecentUploads = ({ documents, count = RECENT_COUNT }) => {
  const recent = [...documents].sort((a, b) => newestFirst(a.uploaded_at, b.uploaded_at)).slice(0, count);

  return (
    <section className="dashboard-panel">
      <h3 className="dashboard-panel-title">Recent uploads</h3>
      {recent.length === 0 ? (
        <p className="dashboard-panel-empty">
          Nothing has been uploaded yet. Add documents on the <Link to="/uploads">Source Documents</Link> page.
        </p>
      ) : (
        <ul className="activity-log scroll-area">
          {recent.map((doc) => {
            const lineCount = doc.category === "statement" ? doc.meta?.transaction_count : doc.meta?.items?.length;
            return (
              <li key={`${doc.category}-${doc.id}`} className="activity-row">
                <div className="activity-main">
                  <Link to={`/uploads/${doc.category}/${doc.id}`} className="activity-name" title={doc.file_name}>
                    {doc.file_name}
                  </Link>
                  <span className="activity-meta">
                    {formatDateTime(doc.uploaded_at)}
                    {lineCount != null && ` · ${lineCount} ${lineCount === 1 ? "line item" : "line items"}`}
                  </span>
                </div>
                <span className={`activity-badge category-${doc.category}`}>
                  {CATEGORY_LABELS[doc.category] || doc.category}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};

/* The line items most recently added. They have no upload time of their own,
   so this is those from the most recently uploaded documents, newest first
   within each. */
export const RecentLineItems = ({ lines }) => {
  const recent = [...lines]
    .sort((a, b) => newestFirst(a.added_at, b.added_at) || newestFirst(a.date, b.date))
    .slice(0, RECENT_COUNT);

  return (
    <section className="dashboard-panel">
      <h3 className="dashboard-panel-title">Recent line items</h3>
      {recent.length === 0 ? (
        <p className="dashboard-panel-empty">
          No line items yet. They appear here once a statement or receipt has been read.
        </p>
      ) : (
        <ul className="activity-log scroll-area">
          {recent.map((line) => (
            <li key={`${line.kind}-${line.id}`} className="activity-row">
              <div className="activity-main">
                <span className="activity-name" title={line.description}>
                  {line.description || "-"}
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
                {line.tags.length > 0 && (
                  <span className="activity-tags">
                    {line.tags.map((tag) => (
                      <span className="tag-chip" key={tag.id}>
                        {tag.name}
                      </span>
                    ))}
                  </span>
                )}
              </div>
              <strong className={`activity-amount${line.amount.startsWith("-") ? " is-negative" : ""}`}>
                {formatMoney(toCents(line.amount))} <ConversionBadge line={line} />
              </strong>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};
