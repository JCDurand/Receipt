import { useEffect } from "react";

/* A question with a Continue and a Cancel button. `danger` marks what it asks
   as destructive (the button is red), and `isBusy` is while the answer is being
   acted on: nothing can be pressed then. */
const ConfirmDialog = ({ title, children, confirmLabel = "Continue", onConfirm, onCancel, danger = false, isBusy = false }) => {
  useEffect(() => {
    const handleKeyDown = (evt) => {
      if (evt.key === "Escape" && !isBusy) onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCancel, isBusy]);

  return (
    <div className="match-modal-overlay" onClick={() => !isBusy && onCancel()}>
      <div
        className="match-modal link-account-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onClick={(evt) => evt.stopPropagation()}
      >
        <div className="match-modal-header">
          <h3 id="confirm-dialog-title">{title}</h3>
        </div>
        <div className="match-modal-body link-account-body">{children}</div>
        <div className="link-account-footer">
          <button type="button" className="link-account-btn" onClick={onCancel} disabled={isBusy}>
            Cancel
          </button>
          <button
            type="button"
            className={`match-btn${danger ? " is-danger" : ""}`}
            onClick={onConfirm}
            disabled={isBusy}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
