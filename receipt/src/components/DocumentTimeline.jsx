import React, { useState } from "react";
import { Link } from "react-router-dom";
import ConversionBadge from "./ConversionBadge";
import { formatDay, formatMoney } from "../utils/format";
import { bankLabel } from "../utils/grouping";

const PAGE = 25;

const range = (first, last) => (first === last ? formatDay(first) : `${formatDay(first)} to ${formatDay(last)}`);

const ReceiptCard = ({ receipt, child = false }) => {
  const isCash = receipt.kind === "cash";
  return (
    <div className={`doc-card doc-receipt${child ? " is-child" : " is-standalone"}${receipt.isConsolidated || isCash ? "" : " is-unconsolidated"}`}>
      <div className="doc-card-main">
        <span className="doc-title">
          <Link to={`/uploads/${receipt.kind}/${receipt.id}`}>{receipt.name}</Link>
        </span>
        <span className="doc-meta">
          {isCash ? "Cash entry" : "Receipt"} · {formatDay(receipt.date)}
          {receipt.itemCount > 0 && ` · ${receipt.itemCount} ${receipt.itemCount === 1 ? "item" : "items"}`}
        </span>
      </div>
      <span
        className={`doc-badge ${isCash ? "is-cash" : receipt.isConsolidated ? "is-consolidated" : "is-unconsolidated"}`}
        title={
          isCash
            ? "Cash is never on a bank statement"
            : receipt.isConsolidated
              ? "Matched to a bank statement line"
              : "Not matched to any bank statement line yet"
        }
      >
        {isCash ? "Cash" : receipt.isConsolidated ? (receipt.statementOutOfView ? "Consolidated (statement not shown)" : "Consolidated") : "Unconsolidated"}
      </span>
      <strong className="doc-amount">{receipt.itemCount > 0 ? formatMoney(receipt.totalCents) : "-"}</strong>
    </div>
  );
};

const StatementNode = ({ statement, showReceipts }) => {
  const [open, setOpen] = useState(true);
  const children = statement.children || [];
  return (
    <li className="doc-node">
      <span className="timeline-dot has-branches" aria-hidden="true" />
      <div className="doc-card doc-statement">
        <div className="doc-card-main">
          <span className="doc-title">
            <Link to={`/uploads/statement/${statement.id}`}>{statement.name}</Link>
          </span>
          <span className="doc-meta">
            Statement · {range(statement.firstDate, statement.lastDate)} · {bankLabel(statement.bank)}
            {statement.account && ` · ${statement.account}`}
            {statement.lineCount > 0 && ` · ${statement.lineCount} lines`}
            {!showReceipts && statement.receipts.length > 0 && ` · ${statement.receipts.length} ${statement.receipts.length === 1 ? "receipt" : "receipts"} consolidated`}
          </span>
        </div>
        <span className="doc-in-out">
          <span className="is-pos">+{formatMoney(statement.inCents)}</span>
          <span className="is-neg">−{formatMoney(statement.outCents)}</span>
        </span>
        {showReceipts && children.length > 0 && (
          <button type="button" className="timeline-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Hide" : "Show"} {children.length} {children.length === 1 ? "receipt" : "receipts"}
          </button>
        )}
      </div>
      {showReceipts && children.length > 0 && open && (
        <ul className="doc-children">
          {children.map((receipt) => (
            <li key={receipt.id}>
              <ReceiptCard receipt={receipt} child />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
};

/* Statements down a line through time (newest first) with the receipts consolidated into each
   branching off it; receipts matched to nothing stand on the line alone */
export const DocumentTree = ({ nodes, showReceipts }) => {
  const [shown, setShown] = useState(PAGE);
  if (nodes.length === 0) return <p className="dashboard-panel-empty">Nothing was uploaded in this period.</p>;
  let lastMonth = null;
  return (
    <div className="timeline">
      <ol className="timeline-spine doc-spine">
        {nodes.slice(0, shown).map((node) => {
          const month = node.date.slice(0, 7);
          const showMonth = month !== lastMonth;
          lastMonth = month;
          return (
            <React.Fragment key={`${node.kind}-${node.id}`}>
              {showMonth && (
                <li className="doc-month">
                  {new Date(+month.slice(0, 4), +month.slice(5, 7) - 1, 1).toLocaleDateString("en-ZA", { month: "long", year: "numeric" })}
                </li>
              )}
              {node.kind === "statement" ? (
                <StatementNode statement={node} showReceipts={showReceipts} />
              ) : (
                <li className="doc-node">
                  <span className={`timeline-dot${node.isConsolidated || node.kind === "cash" ? " is-consolidated" : " is-unconsolidated"}`} aria-hidden="true" />
                  <ReceiptCard receipt={node} />
                </li>
              )}
            </React.Fragment>
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

/* Every transaction, and nothing else: no statements or receipts, only the lines of money moving */
export const TransactionList = ({ lines }) => {
  const [shown, setShown] = useState(PAGE * 2);
  if (lines.length === 0) return <p className="dashboard-panel-empty">There are no transactions in this period.</p>;
  let lastDay = null;
  return (
    <div className="timeline">
      <ol className="timeline-spine">
        {lines.slice(0, shown).map((line) => {
          const showDate = line.date !== lastDay;
          lastDay = line.date;
          const isIn = line.kind === "statement_line" ? Number(line.amount) > 0 : line.direction === "in";
          return (
            <li key={`${line.kind}-${line.id}`} className="timeline-node">
              {showDate && <div className="timeline-date">{formatDay(line.date)}</div>}
              <span className="timeline-dot" aria-hidden="true" />
              <div className={`timeline-card ${isIn ? "line-tint-credit" : "line-tint-debit"}`}>
                <div className="timeline-card-main">
                  <span className="timeline-title" title={line.display_name || line.description}>
                    {line.display_name || line.description || line.merchant || "-"}
                  </span>
                  <span className="timeline-meta">
                    {line.merchant && line.merchant !== line.description ? `${line.merchant} · ` : ""}
                    {(line.tags || []).map((t) => t.name).join(", ") || "Untagged"}
                  </span>
                </div>
                <strong className={`timeline-amount line-amount ${isIn ? "is-credit" : "is-debit"}`}>
                  {isIn ? "+" : "−"}
                  {formatMoney(Math.abs(Math.round(Number(line.amount) * 100)))} <ConversionBadge line={line} />
                </strong>
              </div>
            </li>
          );
        })}
      </ol>
      {lines.length > shown && (
        <button type="button" className="spending-pill timeline-more" onClick={() => setShown(shown + PAGE * 2)}>
          Show more ({lines.length - shown} left)
        </button>
      )}
    </div>
  );
};
