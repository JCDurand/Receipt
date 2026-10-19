import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { documentService } from "../utils/api";
import { accountLabel } from "../utils/format";

/**
 * Links a receipt to the bank account it was paid from: for a receipt which was
 * uploaded with "Reconcile later" (or to correct one). Reports the saved
 * account's id through `onLinked`.
 */
const LinkAccountModal = ({ receipt, accounts, onClose, onLinked }) => {
  const [accountId, setAccountId] = useState(receipt.accountId || "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const handleKeyDown = (evt) => {
      if (evt.key === "Escape" && !isSaving) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, isSaving]);

  const canSave = accountId !== "" && accountId !== receipt.accountId && !isSaving;

  const handleSubmit = async (evt) => {
    evt.preventDefault();
    if (!canSave) return;

    setIsSaving(true);
    setError(null);
    try {
      await documentService.setReceiptAccount(receipt.id, accountId);
      onLinked(receipt.id, accountId);
    } catch (err) {
      console.error("Failed to link the receipt to the account", err);
      setError(err.serverMessage || err.message || "Failed to link this receipt. Please try again.");
      setIsSaving(false);
    }
  };

  return (
    <div className="match-modal-overlay" onClick={() => !isSaving && onClose()}>
      <form
        className="match-modal link-account-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="link-account-title"
        onClick={(evt) => evt.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <div className="match-modal-header">
          <div>
            <h3 id="link-account-title">Link receipt to a bank account</h3>
            <p title={receipt.name}>{receipt.name}</p>
          </div>
          <button type="button" className="match-modal-close" onClick={onClose} disabled={isSaving} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="match-modal-body link-account-body">
          {accounts.length === 0 ? (
            <p className="review-empty-note">
              You have no bank accounts yet. Add one on the <Link to="/accounts">Accounts</Link> page.
            </p>
          ) : (
            <>
              <label className="link-account-label" htmlFor="link-account-select">
                Bank account it was paid from
              </label>
              <select
                id="link-account-select"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                disabled={isSaving}
              >
                <option value="">-- Select Account --</option>
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {accountLabel(acc)}
                  </option>
                ))}
              </select>
              <p className="link-account-hint">
                The receipt can then only be matched to a line on this account's statements.
              </p>
            </>
          )}
          {error && <p className="link-account-error">{error}</p>}
        </div>

        <div className="link-account-footer">
          <button type="button" className="link-account-btn" onClick={onClose} disabled={isSaving}>
            Cancel
          </button>
          <button type="submit" className="match-btn" disabled={!canSave}>
            {isSaving ? "Linking..." : "Link account"}
          </button>
        </div>
      </form>
    </div>
  );
};

export default LinkAccountModal;
