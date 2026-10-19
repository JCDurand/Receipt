import { useEffect } from "react";
import { Link } from "react-router-dom";
import StatementTree from "./StatementTree";

/**
 * Opened by a receipt's Match button. Lists the uploaded statements with their
 * line items beneath them; choosing a line reports it through `onSelect` and
 * the parent closes the modal. A receipt which has a bank account can only be
 * matched to that account's statements, so only those are listed
 * (`accountName` says which).
 */
const MatchModal = ({ receipt, statements, accountName, onClose, onSelect }) => {
  useEffect(() => {
    const handleKeyDown = (evt) => {
      if (evt.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="match-modal-overlay" onClick={onClose}>
      <div
        className="match-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="match-modal-title"
        onClick={(evt) => evt.stopPropagation()}
      >
        <div className="match-modal-header">
          <div>
            <h3 id="match-modal-title">Match this receipt to a statement line</h3>
            <p title={receipt.name}>
              {receipt.name}
              {receipt.total ? ` · ${receipt.total}` : ""}
            </p>
          </div>
          <button type="button" className="match-modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="match-modal-body">
          {accountName && <p className="match-modal-note">Showing statements for {accountName}.</p>}
          {statements.length === 0 ? (
            <p className="review-empty-note">
              {accountName
                ? "No statements have been uploaded for this account. "
                : "No statements have been uploaded. "}
              Add one on the <Link to="/uploads">Source Documents</Link> page.
            </p>
          ) : (
            <StatementTree
              statements={statements}
              onSelectTransaction={(statement, transaction) => onSelect(receipt, statement, transaction)}
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default MatchModal;
