import React, { useState } from "react";
import AccountChoice from "./AccountChoice";
import CurrencyChoice from "./CurrencyChoice";
import { useAuth } from "./AuthContext";
import LineItemsTable from "./LineItemsTable";
import { blankRow, manualItemsPayload } from "../utils/lineItems";
import "../styles/FileListTable.css";
import "../styles/UploadBox.css";

const ENTRY_TYPES = ["Cash", "Receipt", "Statement"];

let nextRowKey = 0;
const newRow = () => blankRow(nextRowKey++);

/**
 * Opened immediately when the Manual entry box is clicked - unlike the other
 * two upload boxes, there is no file involved. The user fills in the record
 * by hand, including an arbitrary number of line items (each with a name,
 * merchant, date, debit or credit, quantity, amount and tags), and it's saved
 * straight to the backend.
 */
const ManualEntryModal = ({ open, accounts, availableTags, onCreateTag, isSaving, error, onCancel, onSave }) => {
  const [name, setName] = useState("");
  const [entryType, setEntryType] = useState(ENTRY_TYPES[0]);
  const [account, setAccount] = useState("");
  const [reconcileLater, setReconcileLater] = useState(false);
  const [items, setItems] = useState([newRow()]);
  const [validationError, setValidationError] = useState("");
  /* until one is chosen: the account's currency, else the user's */
  const { currency: ownCurrency } = useAuth();
  const [currencyChoice, setCurrencyChoice] = useState("");
  const currency = currencyChoice || accounts.find((a) => a.id === account)?.currency || ownCurrency;

  if (!open) return null;

  const resetForm = () => {
    setName("");
    setEntryType(ENTRY_TYPES[0]);
    setAccount("");
    setReconcileLater(false);
    setCurrencyChoice("");
    setItems([newRow()]);
    setValidationError("");
  };

  const handleCancel = () => {
    if (isSaving) return;
    resetForm();
    onCancel();
  };

  const addItem = () => setItems((prev) => [...prev, newRow()]);

  /* only a receipt may leave its bank account until later */
  const isReceipt = entryType === "Receipt";
  const accountLater = isReceipt && reconcileLater;

  const handleSave = () => {
    setValidationError("");

    if(!name.trim()){
      setValidationError("Please provide a name for this entry.")
    }

    const hasIncompleteItems = items.some((item) => !item.name.trim() || item.cost === "");
      if (hasIncompleteItems || items.length === 0) {
        setValidationError("Please fill out the Item Name and Total for all line items.");
        return;
      }

    onSave(
      {
        display_name: name.trim(),
        entry_type: entryType.toLowerCase(),
        account: accountLater ? null : account || null,
        currency,
        items: manualItemsPayload(items),
      },
      resetForm
    );
  };

  const canSave = !isSaving && name.trim() && (entryType === "Cash" || accountLater || account);

  return (
    <div className="file-modal-overlay" onClick={handleCancel}>
      <div className="file-modal-content file-modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="file-modal-header">
          <div className="file-modal-title">
            <h3>Manual entry</h3>
          </div>
          <button type="button" className="file-modal-close" onClick={handleCancel} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="file-modal-body">
          <div className="upload-modal-field">
            <label className="upload-modal-field-label" htmlFor="manual-entry-name">
              Name
            </label>
            <input
              id="manual-entry-name"
              type="text"
              className="upload-modal-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Coffee with client"
            />
          </div>

          <div className="upload-modal-field">
            <label className="upload-modal-field-label" htmlFor="manual-entry-type">
              Type
            </label>
            <select id="manual-entry-type" value={entryType} onChange={(e) => setEntryType(e.target.value)}>
              {ENTRY_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
          
          {entryType !== "Cash" && (
            <AccountChoice
              id="manual-entry-account"
              label="Corresponding bank account"
              accounts={accounts}
              value={account}
              onChange={setAccount}
              allowLater={isReceipt}
              reconcileLater={reconcileLater}
              onReconcileLaterChange={setReconcileLater}
            />
          )}

          <CurrencyChoice id="manual-entry-currency" value={currency} onChange={setCurrencyChoice} />

          <div className="upload-modal-field">
            <span className="upload-modal-field-label">Line items</span>
            <div className="manual-entry-items">
              <LineItemsTable
                rows={items}
                onChange={setItems}
                availableTags={availableTags}
                onCreateTag={onCreateTag}
                editableCore
                showQuantity
              />
              <button type="button" className="manual-entry-add-item" onClick={addItem}>
                + Add line item
              </button>
            </div>
          </div>

          {(error || validationError) && (
            <p className="upload-modal-error" style={{ color: "#d9534f", fontWeight: "bold", marginTop: "10px" }}>
              {validationError || error}
            </p>
          )}
        </div>

        <div className="file-modal-footer">
          <span />
          <div style={{ display: "flex", gap: "8px" }}>
            <button type="button" className="upload-modal-cancel" onClick={handleCancel} disabled={isSaving}>
              Cancel
            </button>
            {/* The button is now always clickable unless actively saving */}
            <button type="button" className="file-modal-download" onClick={handleSave} disabled={isSaving}>
              {isSaving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ManualEntryModal;
