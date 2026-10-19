import { useState } from "react";
import { Link } from "react-router-dom";
import { formatDay, formatMoney } from "../utils/format";
import { spentCents } from "../utils/spending";
import "../styles/Analytics.css";

const PAGE = 30;

/* Spending down a line through time. Each expense is a node on it; the receipt
   items which make it up branch off to the side. */
const ExpenseTimeline = ({ nodes }) => {
  const [shown, setShown] = useState(PAGE);
  const [open, setOpen] = useState(() => new Set());

  if (nodes.length === 0) return <p className="dashboard-panel-empty">No spending in this period.</p>;

  const toggle = (key) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const visible = nodes.slice(0, shown);
  let lastDate = null;

  return (
    <div className="timeline">
      <ol className="timeline-spine">
        {visible.map((node) => {
          const showDate = node.date !== lastDate;
          lastDate = node.date;
          const isOpen = open.has(node.key);
          const hasBranches = node.branches.length > 0;
          return (
            <li key={node.key} className="timeline-node">
              {showDate && <div className="timeline-date">{formatDay(node.date)}</div>}
              <span className={`timeline-dot${hasBranches ? " has-branches" : ""}`} aria-hidden="true" />
              <div className="timeline-card">
                <div className="timeline-card-main">
                  <span className="timeline-title" title={node.title}>
                    {node.source ? (
                      <Link to={`/uploads/${node.source.category}/${node.source.id}`}>{node.title}</Link>
                    ) : (
                      node.title
                    )}
                  </span>
                  <span className="timeline-meta">
                    {node.line ? "Statement line" : "Receipt"}
                    {node.line?.tags.length > 0 && ` · ${node.line.tags.map((t) => t.name).join(", ")}`}
                    {hasBranches && ` · ${node.branches.length} ${node.branches.length === 1 ? "item" : "items"}`}
                  </span>
                </div>
                <strong className="timeline-amount">{formatMoney(node.cents)}</strong>
                {hasBranches && (
                  <button
                    type="button"
                    className="timeline-toggle"
                    aria-expanded={isOpen}
                    onClick={() => toggle(node.key)}
                  >
                    {isOpen ? "Hide items" : "Show items"}
                  </button>
                )}
              </div>
              {hasBranches && isOpen && (
                <ul className="timeline-branches">
                  {node.branches.map((item) => (
                    <li key={item.id} className="timeline-branch">
                      <span className="timeline-branch-name" title={item.display_name || item.description}>
                        {item.display_name || item.description}
                        {item.quantity && Number(item.quantity) !== 1 ? ` × ${Number(item.quantity)}` : ""}
                      </span>
                      <span className="timeline-branch-amount">
                        {item.direction === "in" ? "−" : ""}
                        {formatMoney(Math.abs(Math.round(Number(item.amount) * 100)) || spentCents(item))}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
      {nodes.length > shown && (
        <button type="button" className="spending-pill timeline-more" onClick={() => setShown(shown + PAGE)}>
          Show more ({nodes.length - shown} left)
        </button>
      )}
    </div>
  );
};

export default ExpenseTimeline;
