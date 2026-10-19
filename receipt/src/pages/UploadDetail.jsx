import React, { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import Navbar from "../components/Navbar";
import ConversionBadge from "../components/ConversionBadge";
import LineTable from "../components/LineTable";
import LineEditor from "../components/LineEditor";
import { LineBulkDelete, LineRemoveDialog } from "../components/LineDeletion";
import { useTags } from "../hooks/useTags";
import { useDocumentLines } from "../hooks/useDocumentLines";
import { useLineSelection } from "../hooks/useLineSelection";
import { useLineItemActions } from "../hooks/useLineItemActions";
import { columnsFor } from "../utils/lineItemSort";
import "../styles/PageFormat.css";
import "../styles/FileListTable.css";
import "../styles/UploadBox.css";
import "../styles/UploadDetail.css";
import { documentService } from "../utils/api";
import { accountLabel } from "../utils/format";
import { useAuth } from "../components/AuthContext";
import "../styles/Transactions.css";
import { usePageTitle } from "../components/PageTitle";

/* What a document's own table shows: its source and account are the page's, and
   only a statement's lines have a status, only a receipt's items a quantity */
const STATEMENT_COLUMNS = columnsFor(["date", "description", "tags", "amount", "status", "matched", "direction"]);
const RECEIPT_COLUMNS = columnsFor(["date", "description", "tags", "amount", "quantity", "unit_price", "matched", "direction"]);

const ENTRY_TYPE_LABELS = { cash: "Cash", receipt: "Receipt", statement: "Statement" };

const resolveDocType = (doc) => {
  if (!doc) return "Document";
  const entryLabel = doc.meta?.entry_type && ENTRY_TYPE_LABELS[doc.meta.entry_type];
  if (entryLabel) return entryLabel;
  return doc.category === "statement" ? "Statement" : "Receipt";
};

const formatDate = (dateString) => {
  if (!dateString) return "N/A";
  const parsed = new Date(dateString);
  return isNaN(parsed.getTime()) ? dateString : parsed.toLocaleString();
};

/* Dedicated page for a single upload: its metadata, and the line items
   extracted from it, each with tags which can be changed, and details (name,
   merchant, date and debit or credit) which can be edited. */
const UploadDetail = () => {
  const { category, id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const [doc, setDoc] = useState(location.state?.doc || null);
  const [docType, setDocType] = useState(location.state?.docType || null);
  const [isLoading, setIsLoading] = useState(!location.state?.doc);
  const [error, setError] = useState(null);

  const [nameInput, setNameInput] = useState(location.state?.doc?.file_name || "");
  const [isSavingName, setIsSavingName] = useState(false);
  const [nameError, setNameError] = useState(null);
  const [fileError, setFileError] = useState(null);

  const { tags: availableTags, createTag } = useTags();
  /* the currency every amount is shown in: the document's own amounts are converted to it */
  const { currency: ownCurrency } = useAuth();

  /* the line item whose Edit dialog is open, or which is being removed, if any */
  const [editingLine, setEditingLine] = useState(null);
  const [removingLine, setRemovingLine] = useState(null);

  /* The document records its account by id; this is what names it */
  const [accounts, setAccounts] = useState([]);
  useEffect(() => {
    let isMounted = true;
    documentService
      .getAccounts()
      .then((data) => {
        if (isMounted) setAccounts(data || []);
      })
      .catch((err) => console.error("Failed to load accounts", err));
    return () => {
      isMounted = false;
    };
  }, []);

  /* The document's line items, as the Transactions page has them, to edit, tag
     and remove. A change to them can change the document too (a receipt's total,
     or the document itself, when its last line item goes), so it is loaded again. */
  const isStatement = category === "statement";
  const { lines, setLines, reload: reloadLines, error: linesError } = useDocumentLines(id);
  const refreshDocument = useCallback(async () => {
    await reloadLines();
    const docs = await documentService.getDocuments(category).catch(() => null);
    if (!docs) return;
    const found = docs.find((d) => String(d.id) === String(id));
    if (found) setDoc(found);
    else navigate("/uploads");
  }, [reloadLines, category, id, navigate]);
  const actions = useLineItemActions(setLines, refreshDocument);
  const selection = useLineSelection(lines || []);

  useEffect(() => {
    if (doc) return;

    let isMounted = true;
    const fetchDoc = async () => {
      try {
        setIsLoading(true);
        const docs = await documentService.getDocuments(category);
        const found = (docs || []).find((d) => String(d.id) === String(id));
        if (!isMounted) return;
        if (!found) {
          setError("This document could not be found.");
        } else {
          setDoc(found);
          setDocType(resolveDocType(found));
          setNameInput(found.file_name || "");
        }
      } catch (err) {
        console.error("Failed to load document", err);
        if (isMounted) setError("Failed to load this document. Please try again later.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchDoc();
    return () => {
      isMounted = false;
    };
  }, [category, id, doc]);

  const handleSaveName = async () => {
    const trimmed = nameInput.trim();
    if (!trimmed || trimmed === doc.file_name) return;

    setIsSavingName(true);
    setNameError(null);
    try {
      await documentService.renameDocument(doc.id, doc.category, trimmed);
      setDoc((prev) => ({ ...prev, file_name: trimmed }));
    } catch (err) {
      console.error("Failed to rename document", err);
      setNameError(err.message || "Failed to rename document. Please try again.");
    } finally {
      setIsSavingName(false);
    }
  };

  usePageTitle(doc?.file_name || "Document");

  return (
    <div className="container">
      <Navbar />
      <div className="upload-detail-page">
        <button type="button" className="upload-detail-back" onClick={() => navigate("/uploads")}>
          &larr; Back to Uploads
        </button>

        {isLoading ? (
          <p>Loading document...</p>
        ) : error ? (
          <p style={{ color: "red" }}>{error}</p>
        ) : (
          <>
            <div className="upload-detail-header">
              <input
                type="text"
                className="upload-detail-name-input"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                aria-label="Document name"
              />
              <button
                type="button"
                className="upload-detail-view-btn"
                onClick={handleSaveName}
                disabled={isSavingName || !nameInput.trim() || nameInput.trim() === doc.file_name}
              >
                {isSavingName ? "Saving..." : "Save name"}
              </button>
            </div>
            {nameError && <p style={{ color: "red", marginTop: "-10px" }}>{nameError}</p>}

            <div className="upload-detail-grid">
              <div className="upload-detail-card">
                <h2>Metadata</h2>
                <dl className="upload-detail-meta-list">
                  <dt>Category</dt>
                  <dd><span
                      className={`file-type-badge doc-type-${(docType || resolveDocType(doc))
                        .toLowerCase()
                        .replace(" ", "-")}`} style={{width: "30%"}}
                    >
                      {docType || resolveDocType(doc)}
                    </span>
                  </dd>
                  <dt>Uploaded at</dt>
                  <dd>{formatDate(doc.uploaded_at)}</dd>

                  {doc.meta?.entry_type && (
                    <>
                      <dt>Entry type</dt>
                      <dd style={{ textTransform: "capitalize" }}>{doc.meta.entry_type}</dd>
                    </>
                  )}

                  {doc.meta?.account && (
                    <>
                      <dt>Account</dt>
                      <dd>{accountLabel(accounts.find((a) => a.id === doc.meta.account)) || "-"}</dd>
                    </>
                  )}

                  {doc.meta?.merchant_name && (
                    <>
                      <dt>Merchant</dt>
                      <dd>{doc.meta.merchant_name}</dd>
                    </>
                  )}

                  {doc.meta?.amount && (
                    <>
                      <dt>Amount</dt>
                      <dd>
                        {doc.meta.amount}{" "}
                        <ConversionBadge
                          line={{
                            conversion: doc.meta.amount_conversion,
                            original_amount: doc.meta.amount_original_amount,
                            original_currency: doc.meta.amount_original_currency,
                            exchange_rate: doc.meta.amount_exchange_rate,
                            rate_unavailable: doc.meta.amount_rate_unavailable,
                          }}
                        />
                      </dd>
                    </>
                  )}

                  {doc.meta?.currency && (
                    <>
                      <dt>Currency</dt>
                      <dd>
                        {doc.meta.currency}
                        {doc.meta.currency !== ownCurrency && (
                          <span className="upload-detail-currency-note"> · amounts shown in {ownCurrency}</span>
                        )}
                      </dd>
                    </>
                  )}

                  {isStatement && doc.meta?.bank && (
                    <>
                      <dt>Bank</dt>
                      <dd style={{ textTransform: "capitalize" }}>{doc.meta.bank}</dd>
                    </>
                  )}

                  {doc.meta?.transaction_date && (
                    <>
                      <dt>Transaction date</dt>
                      <dd>{formatDate(doc.meta.transaction_date)}</dd>
                    </>
                  )}
                </dl>

                {doc.file_path && (
                  <button
                    type="button"
                    className="upload-detail-view-btn"
                    onClick={() => {
                      setFileError(null);
                      documentService
                        .openDocumentFile(doc.id, doc.category)
                        .catch(() => setFileError("This file could not be opened. Please try again later."));
                    }}
                  >
                    View file
                  </button>
                )}
                {fileError && <p style={{ color: "red" }}>{fileError}</p>}
              </div>

              <div className="upload-detail-card upload-detail-items-card">
                <h2>Line items &amp; tags</h2>
                {linesError ? (
                  <p style={{ color: "red" }}>{linesError}</p>
                ) : lines === null ? (
                  <p>Loading line items...</p>
                ) : lines.length === 0 ? (
                  <div className="upload-modal-line-items-placeholder">
                    {isStatement
                      ? "No line items have been read from this statement. If it was uploaded moments ago it may still be processing, so try refreshing in a few seconds."
                      : "No line items were found for this document."}
                  </div>
                ) : (
                  <>
                    <div className="upload-detail-items-table scroll-area">
                      <LineTable
                        columns={isStatement ? STATEMENT_COLUMNS : RECEIPT_COLUMNS}
                        entries={lines.map((line) => ({ type: "line", line, depth: 0 }))}
                        selection={selection}
                        onOpen={setEditingLine}
                        onRemove={setRemovingLine}
                        onRename={actions.saveName}
                        tags={{ available: availableTags, onChange: actions.saveTags, onCreate: createTag }}
                        label="Line items"
                      />
                    </div>
                    <LineBulkDelete selection={selection} removeMany={actions.removeMany} />
                  </>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {removingLine && <LineRemoveDialog line={removingLine} onRemove={actions.remove} onClose={() => setRemovingLine(null)} />}
      {editingLine && <LineEditor line={editingLine} onSave={actions.saveDetails} onClose={() => setEditingLine(null)} />}
    </div>
  );
};

export default UploadDetail;
