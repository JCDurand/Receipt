import ConversionBadge from "./ConversionBadge";
import { useState } from "react";
import LineItemName from "./LineItemName";
import { directionKey } from "../utils/format";
import { absAmount } from "../utils/lineItems";

/* A date-only value ("2026-08-15") is read as that calendar day, not as
   midnight UTC, which would show the day before in some timezones */
const formatDay = (dateString) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateString || "");
  const parsed = match ? new Date(+match[1], +match[2] - 1, +match[3]) : new Date(dateString);
  if (!dateString || isNaN(parsed.getTime())) return dateString || "-";
  return parsed.toLocaleDateString("en-ZA", { year: "numeric", month: "short", day: "numeric" });
};

const accountLabel = (account) =>
  account
    ? `${account.account_name || `${account.card_type} account`}${
        account.account_number ? ` (...${account.account_number})` : ""
      }`
    : "";

/**
 * Bank statements as a two level list: each statement is a header with its
 * line items (the transactions read from it) indented beneath. A statement's
 * line items scroll within themselves so a long statement does not stretch
 * the page.
 *
 * `statements` is [{ id, file_name, account, transactions: [...] }].
 * Clicking a statement's header collapses or expands its line items.
 * Each line shows the name the user gave it (with the name it was read with
 * beneath, in italics), its merchant and its amount, which has no sign and is
 * red for a debit and green for a credit.
 * Pass `onSelectTransaction(statement, transaction)` to make line items
 * clickable, and/or `onDropOnTransaction(statement, transaction)` to make them
 * accept a dragged receipt. A line which is already matched to a receipt
 * (`transaction.matched`) is marked as such and does neither.
 * Pass `onRenameTransaction(statement, transaction, name)` to let the names be
 * changed; it is left out where a line is a button, which cannot hold a text box.
 */
const StatementTree = ({ statements, onSelectTransaction, onDropOnTransaction, onRenameTransaction }) => {
  /* line item which a dragged receipt line item is currently over */
  const [dragOverId, setDragOverId] = useState(null);
  /* ids of the statements whose line items are hidden; all start expanded */
  const [collapsedIds, setCollapsedIds] = useState(() => new Set());

  const toggleCollapsed = (id) =>
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const dropHandlers = (statement, transaction) => {
    if (!onDropOnTransaction || transaction.matched) return {};
    return {
      onDragOver: (evt) => {
        evt.preventDefault(); /* required for the element to accept a drop */
        evt.dataTransfer.dropEffect = "link";
      },
      onDragEnter: () => setDragOverId(transaction.id),
      onDragLeave: (evt) => {
        /* leaving to a child of the same line does not count */
        if (!evt.currentTarget.contains(evt.relatedTarget)) setDragOverId(null);
      },
      onDrop: (evt) => {
        evt.preventDefault();
        setDragOverId(null);
        onDropOnTransaction(statement, transaction);
      },
    };
  };

  return (
    <div className="statement-tree">
      {statements.map((statement) => {
        const account = accountLabel(statement.account);
        const count = statement.transactions.length;
        const isCollapsed = collapsedIds.has(statement.id);
        const linesId = `statement-lines-${statement.id}`;

        return (
          <div className="statement-group" key={statement.id}>
            <button
              type="button"
              className="group-toggle"
              aria-expanded={!isCollapsed}
              aria-controls={linesId}
              onClick={() => toggleCollapsed(statement.id)}
            >
              <span className={`group-toggle-chevron${isCollapsed ? "" : " is-open"}`} aria-hidden="true">
                &#9656;
              </span>
              <span className="group-toggle-heading">
                <span className="statement-group-name" title={statement.file_name}>
                  {statement.file_name}
                </span>
                <span className="statement-group-meta">
                  {account && `${account} · `}
                  {count} {count === 1 ? "line item" : "line items"}
                </span>
              </span>
            </button>

            {isCollapsed ? null : count === 0 ? (
              <p className="statement-group-empty">No line items have been read from this statement.</p>
            ) : (
              <ul className="statement-lines" id={linesId}>
                {statement.transactions.map((transaction) => {
                  const content = (
                    <>
                      <span className="statement-line-date">{formatDay(transaction.date)}</span>
                      <span className="statement-line-desc">
                        <span className="statement-line-name">
                          <LineItemName
                            name={transaction.description}
                            alias={transaction.display_name}
                            onRename={
                              onRenameTransaction && ((name) => onRenameTransaction(statement, transaction, name))
                            }
                          />
                          {transaction.matched && <span className="statement-line-tag">Matched</span>}
                        </span>
                        {transaction.merchant && (
                          <span className="statement-line-meta">{transaction.merchant}</span>
                        )}
                      </span>
                      <strong className={`statement-line-amount is-${directionKey(transaction.direction)}`}>
                        {absAmount(transaction.amount)} <ConversionBadge line={transaction} />
                      </strong>
                    </>
                  );

                  return (
                    <li
                      key={transaction.id}
                      className={`statement-line is-${directionKey(transaction.direction)}${dragOverId === transaction.id ? " is-drag-over" : ""}${
                        transaction.matched ? " is-matched" : ""
                      }`}
                      {...dropHandlers(statement, transaction)}
                    >
                      {onSelectTransaction ? (
                        <button
                          type="button"
                          className="statement-line-button"
                          disabled={transaction.matched}
                          onClick={() => onSelectTransaction(statement, transaction)}
                        >
                          {content}
                        </button>
                      ) : (
                        <div className="statement-line-button">{content}</div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default StatementTree;
