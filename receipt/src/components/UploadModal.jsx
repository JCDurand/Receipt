import React from "react";
import AccountChoice from "./AccountChoice";
import CurrencyChoice from "./CurrencyChoice";
import LineItemsTable from "./LineItemsTable";
import "../styles/FileListTable.css";
import "../styles/UploadBox.css";

/**
 * Confirmation modal shown the moment a file is chosen or dropped on one of
 * the upload boxes. The file's line items (a receipt's items, or a statement's
 * transactions) are read as soon as it is chosen and listed here as a table which
 * can be filled in: each one's merchant, date, debit or credit, and tags (with
 * anything that could not be read flagged as an issue). Nothing is saved until
 * "Upload" is clicked here.
 */
const UploadModal = ({
  file,
  name,
  onNameChange,
  docType,
  category,
  accounts,
  selectedAccount,
  onSelectAccount,
  selectedBank,
  onSelectBank,
  currency,
  onCurrencyChange,
  reconcileLater,
  onReconcileLaterChange,
  isUploading,
  parse,
  rows,
  onRowsChange,
  availableTags,
  onCreateTag,
  error,
  onCancel,
  onConfirm,
}) => {
  if (!file) return null;

  /* A statement always belongs to an account; a receipt's may be left until later */
  const requiresAccount = category === "statement";
  const isReceipt = category === "receipt";
  const isParsing = parse.status === "parsing";
  const isUnsupported = parse.status === "unsupported";
  const hasRead = parse.status === "done" || parse.status === "failed";
  const parseFailed = parse.status === "failed";
  const issueCount = parse.issues.length;

  return (
    <div className="file-modal-overlay" onClick={onCancel}>
      <div className="file-modal-content file-modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="file-modal-header">
          <div className="file-modal-title">
            <input
              type="text"
              className="upload-modal-name-input"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              aria-label="Document name"
            />
          </div>
          <button type="button" className="file-modal-close" onClick={onCancel} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="file-modal-body">
          <div className="upload-modal-field">
            <span className="upload-modal-field-label">Document type</span>
            <span className={`file-type-badge doc-type-${docType.toLowerCase().replace(" ", "-")}`}>
              {docType}
            </span>
          </div>

          {requiresAccount && (
            <div className="upload-modal-field">
              <label className="upload-modal-field-label" htmlFor="upload-modal-bank">
                Bank format
              </label>
              <select id="upload-modal-bank" value={selectedBank || "investec"} onChange={
                  (e) => onSelectBank(e.target.value)}
              >
                <option value="investec">Investec</option>
                <option value="fnb">FNB</option>
                <option value="absa">ABSA</option>
              </select>
            </div>
          )}

          {(requiresAccount || isReceipt) && (
            <AccountChoice
              id="upload-modal-account"
              label="Target bank account"
              accounts={accounts}
              value={selectedAccount}
              onChange={onSelectAccount}
              allowLater={isReceipt}
              reconcileLater={reconcileLater}
              onReconcileLaterChange={onReconcileLaterChange}
            />
          )}

          {(requiresAccount || isReceipt) && <CurrencyChoice id="upload-modal-currency" value={currency} onChange={onCurrencyChange} />}

          {!isUnsupported && (
            <div className="upload-modal-field">
              <span className="upload-modal-field-label">
                {requiresAccount ? "Transactions" : "Line items"}
                {hasRead && ` (${rows.length})`}
                {issueCount > 0 && (
                  <span className="upload-modal-issue-count">
                    {issueCount} {issueCount === 1 ? "issue" : "issues"}
                  </span>
                )}
              </span>

              {isParsing && (
                <div className="upload-modal-line-items-placeholder">
                  Reading line items from this file...
                </div>
              )}

              {hasRead && rows.length > 0 && (
                <LineItemsTable
                  rows={rows}
                  onChange={onRowsChange}
                  availableTags={availableTags}
                  onCreateTag={onCreateTag}
                  requireDate={requiresAccount}
                  showQuantity={!requiresAccount}
                />
              )}

              {hasRead && parse.totalAmount && (
                <span className="upload-modal-items-total">Receipt total: {parse.totalAmount}</span>
              )}

              {hasRead && (
                <ul className="upload-modal-issues" role={parseFailed ? "alert" : undefined} aria-live="polite">
                  {parse.issues.map((issue, idx) => (
                    <li key={idx}>
                      <span className="upload-modal-issue-flag">Issue</span>
                      {issue}
                    </li>
                  ))}
                </ul>
              )}

              {hasRead && rows.length === 0 && issueCount === 0 && (
                <div className="upload-modal-line-items-placeholder">
                  {requiresAccount ? "No transactions were found." : "No line items were found."}
                </div>
              )}
            </div>
          )}

          {error && <p className="upload-modal-error">{error}</p>}
        </div>

        <div className="file-modal-footer">
          <span className="file-modal-metadata">
            <span>{(file.size / 1024).toFixed(1)} KB</span>
          </span>
          <div style={{ display: "flex", gap: "8px" }}>
            <button type="button" className="upload-modal-cancel" onClick={onCancel} disabled={isUploading}>
              Cancel
            </button>
            <button
              type="button"
              className={`file-modal-download${parseFailed ? " parser-failed" : ""}`}
              onClick={onConfirm}
              disabled={
                isUploading ||
                isParsing ||
                parseFailed ||
                isUnsupported ||
                !name.trim() ||
                (requiresAccount && !selectedAccount) ||
                (isReceipt && !reconcileLater && !selectedAccount) ||
                (requiresAccount && rows.some((row) => !row.date))
              }
            >
              {isUploading ? "Uploading..." : "Upload"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UploadModal;
