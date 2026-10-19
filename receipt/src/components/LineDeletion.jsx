import React, { useState } from "react";
import ConfirmDialog from "./ConfirmDialog";
import { lineKey } from "../hooks/useLineSelection";
import { formatDay, shownName } from "../utils/format";
import { absAmount } from "../utils/lineItems";

const errorText = (err, fallback) => err?.serverMessage || err?.message || fallback;

/**
 * Beneath a table of line items: how many are picked, and the button which
 * removes them all (after asking), then what went with them. `selection` is
 * useLineSelection's and `removeMany` useLineItemActions'.
 */
export const LineBulkDelete = ({ selection, removeMany }) => {
  const [isConfirming, setIsConfirming] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const picked = selection.selectedLines;

  const confirm = async () => {
    setIsBusy(true);
    setError(null);
    try {
      setResult(await removeMany(picked));
      selection.clear();
      setIsConfirming(false);
    } catch (err) {
      console.error("Failed to remove the line items", err);
      setError(errorText(err, "The line items could not be removed. Please try again."));
    } finally {
      setIsBusy(false);
    }
  };

  if (picked.length === 0 && !result) {
    return <p className="line-bulk-hint">Hover over a line item and tick its box, or shift-click it, to select it for removal. Click a line item to edit it.</p>;
  }

  return (
    <>
      <div className="line-bulk" role="status">
        {picked.length > 0 ? (
          <>
            <span>
              {picked.length} {picked.length === 1 ? "line item" : "line items"} selected
            </span>
            <button type="button" className="line-bulk-delete" onClick={() => setIsConfirming(true)}>
              Delete {picked.length === 1 ? "line item" : `all ${picked.length}`}
            </button>
            <button type="button" className="line-bulk-clear" onClick={selection.clear}>
              Clear selection
            </button>
            <span className="line-bulk-hint">Shift-click more line items to add them.</span>
          </>
        ) : (
          <span>
            Removed {result.deleted} {result.deleted === 1 ? "line item" : "line items"}
            {result.removed_statements.length > 0 &&
              `, and ${result.removed_statements.length} ${result.removed_statements.length === 1 ? "statement" : "statements"} left with none`}
            {result.removed_receipts.length > 0 &&
              `${result.removed_statements.length > 0 ? " and" : ", and"} ${result.removed_receipts.length} ${result.removed_receipts.length === 1 ? "receipt" : "receipts"} left with none`}
            .
          </span>
        )}
      </div>

      {isConfirming && (
        <ConfirmDialog
          title={`Delete ${picked.length} ${picked.length === 1 ? "line item" : "line items"}?`}
          confirmLabel={isBusy ? "Deleting..." : "Delete"}
          danger
          isBusy={isBusy}
          onConfirm={confirm}
          onCancel={() => {
            setIsConfirming(false);
            setError(null);
          }}
        >
          <p>
            These will be removed from your records for good
            {picked.some((l) => l.matched) && ", including the matches between statement lines and receipts"}.
          </p>
          <ul className="line-bulk-list">
            {picked.slice(0, 8).map((l) => (
              <li key={lineKey(l)}>
                {formatDay(l.date)} · {shownName(l.description, l.display_name) || "-"} · {absAmount(l.amount)}
              </li>
            ))}
            {picked.length > 8 && <li>and {picked.length - 8} more</li>}
          </ul>
          <p>
            A receipt's total follows the items removed from it, and a receipt matched to a removed statement line goes back
            to waiting on the Review page. A bank statement or receipt with no line items left is removed too, with its
            file. Uploading a statement again would bring its lines back.
          </p>
          {error && <p className="link-account-error">{error}</p>}
        </ConfirmDialog>
      )}
    </>
  );
};

/* Asks before removing one line item for good. `onRemove` is useLineItemActions' remove. */
export const LineRemoveDialog = ({ line, onRemove, onClose }) => {
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState(null);

  const confirm = async () => {
    setIsBusy(true);
    setError(null);
    try {
      await onRemove(line);
      onClose();
    } catch (err) {
      console.error("Failed to remove the line item", err);
      setError(errorText(err, "The line item could not be removed. Please try again."));
      setIsBusy(false);
    }
  };

  return (
    <ConfirmDialog
      title={line.kind === "statement_line" ? "Remove this statement line?" : "Remove this receipt item?"}
      confirmLabel={isBusy ? "Removing..." : "Remove"}
      danger
      isBusy={isBusy}
      onConfirm={confirm}
      onCancel={onClose}
    >
      <p>
        <strong>{shownName(line.description, line.display_name) || "-"}</strong> ({absAmount(line.amount)}) will be removed
        {line.source ? ` from ${line.source.name}` : ""} for good.
      </p>
      {line.kind === "statement_line" ? (
        <>
          {line.matched && (
            <p>A receipt is matched to this line. Removing it unmatches the receipt, which goes back to waiting on the Review page.</p>
          )}
          <p>Uploading the statement again would bring the line back.</p>
        </>
      ) : (
        <p>The receipt's total is updated if it was made up of its items.</p>
      )}
      {error && <p className="link-account-error">{error}</p>}
    </ConfirmDialog>
  );
};
