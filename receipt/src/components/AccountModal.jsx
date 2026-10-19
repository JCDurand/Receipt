import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { documentService } from "../utils/api";
import { useAuth } from "./AuthContext";
import { AccountBalance, AccountWarning } from "./AccountBalance";
import "../styles/AccountBalance.css";
import { formatDateTime } from "../utils/format";

const CARD_TYPES = ["Cheque", "Savings", "Credit"];

/* What is wrong with the details, or null; mirrors what the server checks */
const problemWith = (details, otherAccounts) => {
  if (!details.account_name.trim()) return "Account name is required.";
  if (!/^\d{4}$/.test(details.account_number)) return "Account number must be exactly 4 digits.";
  if (otherAccounts.some((acc) => acc.account_number === details.account_number)) {
    return "You already have an account with that account number.";
  }
  if (details.funds === "" || isNaN(Number(details.funds)) || Number(details.funds) < 0) {
    return "Opening balance must be zero or more.";
  }
  return null;
};

const detailsOf = (account) => ({
  account_name: account.account_name,
  account_number: account.account_number,
  card_type: account.card_type,
  funds: String(account.funds ?? "0"),
  currency: account.currency || "ZAR",
});

/**
 * Opened by clicking a bank account: its details, which can be edited, and the
 * statements uploaded to it. Saving reports the updated account through
 * `onSaved`. Statements and line items refer to their account rather than
 * copying its details, so every one of them shows the new details from then on.
 * `accounts` is all the user's accounts, to catch a clashing account number.
 */
const AccountModal = ({ account, accounts, onClose, onSaved }) => {
  const { currencies } = useAuth();
  const [saved, setSaved] = useState(() => detailsOf(account));
  const [form, setForm] = useState(() => detailsOf(account));
  const [statements, setStatements] = useState(null); /* null until loaded */
  const [statementsError, setStatementsError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [justSaved, setJustSaved] = useState(false);
  /* its balance now and whether it went below zero, which saving the opening balance changes */
  const [summary, setSummary] = useState(account);

  useEffect(() => {
    let isMounted = true;
    documentService
      .getAccount(account.id)
      .then((data) => {
        if (isMounted) setStatements(data.statements || []);
      })
      .catch((err) => {
        console.error("Failed to load the account's statements", err);
        if (isMounted) setStatementsError("Failed to load this account's statements. Please try again later.");
      });
    return () => {
      isMounted = false;
    };
  }, [account.id]);

  useEffect(() => {
    const handleKeyDown = (evt) => {
      if (evt.key === "Escape" && !isSaving) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, isSaving]);

  const otherAccounts = accounts.filter((acc) => acc.id !== account.id);
  const problem = problemWith(form, otherAccounts);
  const isDirty = Object.keys(form).some((key) => form[key] !== saved[key]);

  const setField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setJustSaved(false);
    setSaveError(null);
  };

  const handleSubmit = async (evt) => {
    evt.preventDefault();
    if (problem || !isDirty || isSaving) return;

    setIsSaving(true);
    setSaveError(null);
    try {
      const updated = await documentService.updateAccount(account.id, {
        ...form,
        account_name: form.account_name.trim(),
      });
      const now = detailsOf(updated);
      setSummary(updated);
      setSaved(now);
      setForm(now);
      setJustSaved(true);
      onSaved(updated);
    } catch (err) {
      console.error("Failed to update the account", err);
      setSaveError(err.serverMessage || err.message || "Failed to save the account. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="account-modal-overlay" onClick={() => !isSaving && onClose()}>
      <div
        className="account-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-modal-title"
        onClick={(evt) => evt.stopPropagation()}
      >
        <div className="account-modal-header">
          <div>
            <h2 id="account-modal-title">{saved.account_name}</h2>
            <p>
              {saved.card_type} &middot; ...{saved.account_number}
            </p>
            <AccountBalance account={{ ...summary, funds: saved.funds, currency: saved.currency }} />
          </div>
          <button type="button" className="account-modal-close" onClick={onClose} disabled={isSaving} aria-label="Close">
            &times;
          </button>
        </div>

        <AccountWarning account={summary} />
        <div className="account-modal-body">
          <form className="account-form" onSubmit={handleSubmit}>
            <h3>Details</h3>
            <div className="account-field">
              <label htmlFor="edit-account-name">Account Name</label>
              <input
                id="edit-account-name"
                type="text"
                maxLength={100}
                value={form.account_name}
                onChange={(e) => setField("account_name", e.target.value)}
              />
            </div>
            <div className="account-field">
              <label htmlFor="edit-account-number">Account Number</label>
              <input
                id="edit-account-number"
                type="text"
                inputMode="numeric"
                maxLength={4}
                value={form.account_number}
                onChange={(e) => setField("account_number", e.target.value.replace(/\D/g, "").slice(0, 4))}
              />
            </div>
            <div className="account-field">
              <label htmlFor="edit-account-type">Card Type</label>
              <select id="edit-account-type" value={form.card_type} onChange={(e) => setField("card_type", e.target.value)}>
                {CARD_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            <div className="account-field">
              <label htmlFor="edit-account-funds">Opening balance (when the account was created)</label>
              <input
                id="edit-account-funds"
                type="number"
                min="0"
                step="0.01"
                value={form.funds}
                onChange={(e) => setField("funds", e.target.value)}
              />
            </div>

            <div className="account-field">
              <label htmlFor="edit-account-currency">Currency of the funds</label>
              <select id="edit-account-currency" value={form.currency} onChange={(e) => setField("currency", e.target.value)}>
                {currencies.length === 0 && <option value={form.currency}>{form.currency}</option>}
                {currencies.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.code} · {c.name}
                  </option>
                ))}
              </select>
            </div>

            {isDirty && problem && <p className="account-form-error">{problem}</p>}
            {saveError && <p className="account-form-error">{saveError}</p>}
            {justSaved && (
              <p className="account-form-saved" role="status">
                Saved. The new details now show on all of this account's statements and line items.
              </p>
            )}

            <button type="submit" className="account-submit-btn" disabled={isSaving || !isDirty || Boolean(problem)}>
              {isSaving ? "Saving..." : "Save changes"}
            </button>
          </form>

          <div className="account-statements">
            <h3>Statements</h3>
            {statementsError ? (
              <p className="account-list-status error">{statementsError}</p>
            ) : statements === null ? (
              <p className="account-list-status">Loading statements...</p>
            ) : statements.length === 0 ? (
              <p className="account-list-status">
                No statements have been uploaded to this account. Add one on the{" "}
                <Link to="/uploads">Source Documents</Link> page.
              </p>
            ) : (
              <ul className="account-statement-list">
                {statements.map((statement) => (
                  <li key={statement.id}>
                    <Link to={`/statements/${statement.id}`} className="account-statement-row">
                      <span className="account-statement-name" title={statement.file_name}>
                        {statement.file_name}
                      </span>
                      <span className="account-statement-meta">
                        {formatDateTime(statement.uploaded_at)} &middot; {statement.transaction_count}{" "}
                        {statement.transaction_count === 1 ? "line item" : "line items"}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AccountModal;
