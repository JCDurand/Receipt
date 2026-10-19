import React from "react";
import { useAuth } from "./AuthContext";

/**
 * The currency a document's amounts are in. It starts as the bank account's (or
 * the user's own currency), and can be changed for a document in another one.
 * When it is not the user's currency, a note says it will be converted.
 */
const CurrencyChoice = ({ id, value, onChange }) => {
  const { currency: own, currencies } = useAuth();
  return (
    <div className="upload-modal-field">
      <label className="upload-modal-field-label" htmlFor={id}>
        Currency of this document
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {currencies.length === 0 && <option value={value}>{value}</option>}
        {currencies.map((c) => (
          <option key={c.code} value={c.code}>
            {c.code} · {c.name}
          </option>
        ))}
      </select>
      {value !== own && (
        <span className="upload-modal-hint">
          Shown as {value} -&gt; {own}: converted to {own} at the rate on the day of each line.
        </span>
      )}
    </div>
  );
};

export default CurrencyChoice;
