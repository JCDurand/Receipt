import { AccountWarning } from "./AccountBalance";
import "../styles/AccountBalance.css";

/**
 * Which bank account an upload belongs to. For a receipt the account may not be
 * known yet, so `allowLater` adds a "Reconcile later" checkbox which greys out
 * the list: the receipt is then uploaded with no account and waits in the
 * Review queue, where an account can be linked to it.
 */
const AccountChoice = ({
  id,
  label,
  accounts,
  value,
  onChange,
  allowLater = false,
  reconcileLater = false,
  onReconcileLaterChange,
}) => (
  <div className="upload-modal-field">
    <label className="upload-modal-field-label" htmlFor={id}>
      {label}
    </label>
    <select id={id} value={value} disabled={reconcileLater} onChange={(e) => onChange(e.target.value)}>
      <option value="">-- Select Account --</option>
      {accounts.map((acc) => (
        <option key={acc.id} value={acc.id}>
          {acc.account_name || `${acc.card_type} account`}
          {acc.account_number ? ` (...${acc.account_number})` : ""}
        </option>
      ))}
    </select>

    {!reconcileLater && <AccountWarning account={accounts.find((acc) => acc.id === value)} />}

    {allowLater && (
      <label className="upload-modal-checkbox">
        <input
          type="checkbox"
          checked={reconcileLater}
          onChange={(e) => onReconcileLaterChange(e.target.checked)}
        />
        <span>
          Reconcile later
          <span className="upload-modal-hint">
            The account is not known yet. It can be linked on the Review page.
          </span>
        </span>
      </label>
    )}
  </div>
);

export default AccountChoice;
