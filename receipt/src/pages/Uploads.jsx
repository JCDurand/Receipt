import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";
import UploadBox from "../components/UploadBox";
import UploadModal from "../components/UploadModal";
import ManualEntryModal from "../components/ManualEntryModal";
import { useAuth } from "../components/AuthContext";
import { useTags } from "../hooks/useTags";
import {
  receiptItemsPayload,
  rowsFromReceipt,
  rowsFromStatement,
  statementTransactionsPayload,
} from "../utils/lineItems";
import "../styles/PageFormat.css";
import "../styles/FileListTable.css";
import "../styles/UploadBox.css";
import { documentService } from "../utils/api";
import { usePageTitle } from "../components/PageTitle";

const BOXES = [
  { key: "statement", label: "Statements", docType: "Statement", category: "statement", bank: "investec" },
  { key: "receipt", label: "Receipts", docType: "Receipt", category: "receipt" },
];

// The three kinds of source document, which are the Type column's badges and the
// filter chips. A receipt is a receipt however it got here: uploaded as a file or
// entered by hand. Manual entries are badged by whichever Type was chosen in the
// modal (Cash gets its own banner).
const DOC_TYPES = ["Receipt", "Statement", "Cash"];
const ENTRY_TYPE_LABELS = { cash: "Cash", receipt: "Receipt", statement: "Statement" };

const displayType = (doc) => {
  const entryLabel = doc.meta?.entry_type && ENTRY_TYPE_LABELS[doc.meta.entry_type];
  if (entryLabel) return entryLabel;
  return doc.category === "statement" ? "Statement" : "Receipt";
};

const SUPPORTED_EXTENSIONS = [".pdf", ".csv"];

const fileExtension = (fileName) => {
  const dot = fileName.lastIndexOf(".");
  return dot === -1 ? "" : fileName.slice(dot).toLowerCase();
};

/* What reading a chosen file has produced so far (the line items it holds are
   the `lineRows` below, which the user then edits).
   status: "idle" (nothing to read), "parsing", "done", "failed" (the parse
   request itself failed) or "unsupported" (not a PDF or CSV). */
const IDLE_PARSE = { status: "idle", issues: [], merchantName: null, transactionDate: null, totalAmount: null };

const SORT_OPTIONS = [
  { value: "date-desc", label: "Uploaded: newest first" },
  { value: "date-asc", label: "Uploaded: oldest first" },
  { value: "type-asc", label: "Type: A to Z" },
  { value: "type-desc", label: "Type: Z to A" },
];

// Local calendar day as YYYY-MM-DD, directly comparable with <input type="date"> values.
const toDateKey = (dateString) => {
  const parsed = new Date(dateString);
  if (!dateString || isNaN(parsed.getTime())) return null;
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${parsed.getFullYear()}-${month}-${day}`;
};

const formatDate = (dateString) => {
  if (!dateString) return "N/A";
  const parsed = new Date(dateString);
  return isNaN(parsed.getTime()) ? dateString : parsed.toLocaleString();
};

const Uploads = () => {
  usePageTitle("Source Documents");
  const navigate = useNavigate();

  const [documents, setDocuments] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [parserNotification, setParserNotification] = useState(null);

  const [pendingFile, setPendingFile] = useState(null);
  const [pendingBox, setPendingBox] = useState(null);
  const [pendingName, setPendingName] = useState("");
  const [selectedAccount, setSelectedAccount] = useState("");
  const [selectedBank, setSelectedBank] = useState("investec");
  /* The currency chosen for the document; until one is, its account's, else the user's */
  const { currency: ownCurrency } = useAuth();
  const [currencyChoice, setCurrencyChoice] = useState("");
  const uploadCurrency = currencyChoice || accounts.find((a) => a.id === selectedAccount)?.currency || ownCurrency;
  /* a receipt whose bank account is not known yet: linked later, on the Review page */
  const [reconcileLater, setReconcileLater] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [modalError, setModalError] = useState(null);
  const [parse, setParse] = useState(IDLE_PARSE);
  /* The line items of the file (a receipt's items, or a statement's transactions),
     as rows for the user to fill in before uploading */
  const [lineRows, setLineRows] = useState([]);
  const { tags: availableTags, createTag } = useTags();
  /* Only the latest file's result may land: a slow PDF read must not overwrite
     the items of a file chosen after it */
  const parseRequestId = useRef(0);

  const [manualEntryOpen, setManualEntryOpen] = useState(false);
  const [isSavingManualEntry, setIsSavingManualEntry] = useState(false);
  const [manualEntryError, setManualEntryError] = useState(null);

  const [sortBy, setSortBy] = useState("date-desc");
  const [typeFilter, setTypeFilter] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [deletingKey, setDeletingKey] = useState(null);

  useEffect(() => {
    let isMounted = true;

    const fetchData = async () => {
      setIsLoading(true);

      const [docsResult, accountsResult] = await Promise.allSettled([
        documentService.getDocuments(),
        documentService.getAccounts(),
      ]);

      if (!isMounted) return;

      if (docsResult.status === "fulfilled") {
        setDocuments(docsResult.value || []);
      } else {
        console.error("Failed to load documents", docsResult.reason);
        setError("Failed to load your documents. Please try again later.");
      }

      if (accountsResult.status === "fulfilled") {
        setAccounts(accountsResult.value || []);
      } else {
        console.error("Failed to load accounts", accountsResult.reason);
      }

      setIsLoading(false);
    };

    fetchData();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!documents.some((doc) => ["pending", "processing"].includes(doc.processing_status))) {
      return undefined;
    }

    let isMounted = true;
    const poll = async () => {
      try {
        const latestDocuments = await documentService.getDocuments();
        if (!isMounted) return;
        const failedDocument = latestDocuments.find(
          (doc) =>
            doc.processing_status === "failed" &&
            documents.some(
              (current) => current.id === doc.id && current.processing_status !== "failed"
            )
        );
        if (failedDocument) {
          setParserNotification(
            `${failedDocument.file_name || "Document"} could not be parsed. ${failedDocument.parser_error || "Please review the file and try again."}`
          );
        }
        setDocuments(latestDocuments || []);
      } catch (pollError) {
        console.error("Failed to refresh parser status", pollError);
      }
    };

    const intervalId = window.setInterval(poll, 1500);
    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, [documents]);

  const rows = useMemo(
    () => documents.map((doc) => ({ doc, type: displayType(doc) })),
    [documents]
  );

  /* Date range applies first so the type chip counts reflect what each chip
     would actually show. */
  const dateFilteredRows = useMemo(
    () =>
      rows.filter(({ doc }) => {
        if (!dateFrom && !dateTo) return true;
        const key = toDateKey(doc.uploaded_at);
        if (!key) return false;
        return (!dateFrom || key >= dateFrom) && (!dateTo || key <= dateTo);
      }),
    [rows, dateFrom, dateTo]
  );

  const typeCounts = useMemo(() => {
    const counts = {};
    dateFilteredRows.forEach(({ type }) => {
      counts[type] = (counts[type] || 0) + 1;
    });
    return counts;
  }, [dateFilteredRows]);

  const visibleRows = useMemo(() => {
    const newestFirst = (a, b) =>
      new Date(b.doc.uploaded_at || 0) - new Date(a.doc.uploaded_at || 0);

    return dateFilteredRows
      .filter(({ type }) => typeFilter === "all" || type === typeFilter)
      .sort((a, b) => {
        switch (sortBy) {
          case "date-asc":
            return newestFirst(b, a);
          case "type-asc":
            return a.type.localeCompare(b.type) || newestFirst(a, b);
          case "type-desc":
            return b.type.localeCompare(a.type) || newestFirst(a, b);
          default:
            return newestFirst(a, b);
        }
      });
  }, [dateFilteredRows, typeFilter, sortBy]);

  const hasActiveFilters = typeFilter !== "all" || dateFrom || dateTo;

  const clearFilters = () => {
    setTypeFilter("all");
    setDateFrom("");
    setDateTo("");
  };

  const openModal = (box, file) => {
    const requestId = ++parseRequestId.current;
    setPendingBox(box);
    setPendingFile(file);
    setPendingName(file.name);
    setSelectedAccount("");
    setReconcileLater(false);

    /* The pickers only suggest PDF/CSV; a dropped file can be anything */
    if (!SUPPORTED_EXTENSIONS.includes(fileExtension(file.name))) {
      setModalError(`"${file.name}" is not a supported file type. Only PDF and CSV files can be uploaded.`);
      setParse({ ...IDLE_PARSE, status: "unsupported" });
      return;
    }

    setModalError(null);
    runParse(requestId, box.category, file, selectedBank);
  }

  const runParse = (requestId, category, file, bank) => {
    setLineRows([]);
    setParse({ ...IDLE_PARSE, status: "parsing" });
    documentService
      .parseDocument(file, category, bank)
      .then((result) => {
        if (requestId !== parseRequestId.current) return;
        const items = result.items || [];
        const issues = result.issues || [];
        setParse({
          status: "done",
          issues: result.issues || [],
          merchantName: result.merchant_name,
          transactionDate: result.transaction_date,
          totalAmount: result.total_amount,
        });
        setLineRows(category === "receipt" ? rowsFromReceipt(result) : rowsFromStatement(result, availableTags));
      })
      .catch((err) => {
        if (requestId !== parseRequestId.current) return;
        console.error("Failed to read the file", err);
        setParse({
          ...IDLE_PARSE,
          status: "failed",
          issues: [err.message || "The file could not be read."],
        });
      });
  };

  const handleBankChange = (newBank) => {
    setSelectedBank(newBank);
    if (!pendingFile || pendingBox?.category !== "statement") return;
    // restart parse when bank is changed
    const requestId = ++parseRequestId.current;
    runParse(requestId, "statement", pendingFile, newBank);
  };

  const closeModal = () => {
    if (isUploading) return;
    parseRequestId.current += 1;
    setPendingFile(null);
    setPendingBox(null);
    setPendingName("");
    setSelectedBank("investec");
    setCurrencyChoice("");
    setModalError(null);
    setParse(IDLE_PARSE);
    setLineRows([]);
  };

  const handleConfirmUpload = async () => {
    if (!pendingFile || !pendingBox) return;
    if (["unsupported", "parsing", "failed"].includes(parse.status)) return;

    if (pendingBox.category === "statement" && !selectedAccount) {
      setModalError("Please select a target bank account.");
      return;
    }

    if (pendingBox.category === "statement" && lineRows.some((row) => !row.date)) {
      setModalError("Every transaction needs a date.");
      return;
    }

    if (pendingBox.category === "receipt" && !reconcileLater && !selectedAccount) {
      setModalError("Please select a target bank account, or choose Reconcile later.");
      return;
    }

    const formData = new FormData();
    formData.append("file", pendingFile);
    formData.append("category", pendingBox.category);
    formData.append("display_name", pendingName.trim() || pendingFile.name);
    formData.append("currency", uploadCurrency);
    if (pendingBox.category === "statement" || (pendingBox.category === "receipt" && !reconcileLater)) {
      formData.append("account", selectedAccount);
    }
    if (pendingBox.category === "statement") {
      formData.append("bank", selectedBank);
    }
    if (parse.status === "done") {
      /* Save exactly what the user was shown (and edited), so the server does not
         read the file a second time. If reading failed, leave these out and the
         server will try for itself. */
      if (pendingBox.category === "receipt") {
        formData.append("items", JSON.stringify(receiptItemsPayload(lineRows)));
        if (parse.merchantName) formData.append("merchant_name", parse.merchantName);
        if (parse.totalAmount) formData.append("amount", parse.totalAmount);
        if (parse.transactionDate) formData.append("transaction_date", parse.transactionDate);
      } else {
        formData.append("transactions", JSON.stringify(statementTransactionsPayload(lineRows)));
      }
    }

    setIsUploading(true);
    setModalError(null);
    try {
      const newDoc = await documentService.uploadDocument(formData);
      
      if (!newDoc.id || newDoc.message) {
        setModalError(newDoc.message   || "This document has already been imported.");
        return;
      }

      setDocuments((prev) => [newDoc, ...prev]);
      setPendingFile(null);
      setPendingBox(null);
      setPendingName("");
      setCurrencyChoice("");
      setParse(IDLE_PARSE);
      setLineRows([]);
    } catch (err) {
      console.error("Upload failed", err);
      setModalError(err.message || "Upload failed. Please try again.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleSaveManualEntry = async (payload, resetForm) => {
    if (!payload.display_name) {
      setManualEntryError("Please give this entry a name.");
      return;
    }
    /* a receipt may leave its account until later; the modal will not send a
       receipt with neither an account nor "reconcile later" */
    if (payload.entry_type === "statement" && !payload.account) {
      setManualEntryError("Please select a corresponding bank account.");
      return;
    }

    setIsSavingManualEntry(true);
    setManualEntryError(null);
    try {
      const newDoc = await documentService.createManualEntry(payload);
      setDocuments((prev) => [newDoc, ...prev]);
      resetForm();
      setManualEntryOpen(false);
    } catch (err) {
      console.error("Failed to save manual entry", err);
      setManualEntryError(err.message || "Failed to save this entry. Please try again.");
    } finally {
      setIsSavingManualEntry(false);
    }
  };

  const handleDelete = async (doc) => {
    if (!window.confirm(`Are you sure you want to delete "${doc.file_name}"?`)) return;

    const key = `${doc.category}-${doc.id}`;
    setDeletingKey(key);
    try {
      await documentService.deleteDocument(doc.id, doc.category);
      setDocuments((prev) =>
        prev.filter((d) => !(d.id === doc.id && d.category === doc.category))
      );
    } catch (err) {
      console.error("Failed to delete", err);
      alert("Failed to delete the document: " + err.message);
    } finally {
      setDeletingKey(null);
    }
  };

  const handleRowClick = (doc) => {
    navigate(`/uploads/${doc.category}/${doc.id}`, {
      state: { doc, docType: displayType(doc) },
    });
  };

  return (
    <div className="container">
      <Navbar />
      {parserNotification && (
        <div className="alert-banner parser-alert" role="alert">
          <span className="alert-icon">!</span>
          <span className="alert-text">{parserNotification}</span>
          <button
            type="button"
            onClick={() => setParserNotification(null)}
            aria-label="Dismiss parser notification"
          >
            Dismiss
          </button>
        </div>
      )}
      <div className="scans-container">
        <div className="scans-content">
          <div className="scans-dashboard">
            <div className="page-header">
              <p>
                Upload bank statements and receipts, or enter a purchase by hand. Click a document to
                see the line items read from it and tag them.
              </p>
            </div>

            {/* Upload targets */}
            <div className="file-drop-wrapper">
              <div className="upload-box-row">
                {BOXES.map((box) => (
                  <UploadBox
                    key={box.key}
                    label={box.label}
                    onFileSelected={(file) => openModal(box, file)}
                  />
                ))}
                <div
                  className="upload-box"
                  onClick={() => setManualEntryOpen(true)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") setManualEntryOpen(true);
                  }}
                >
                  <span className="upload-box-label">Manual entry</span>
                  <span className="upload-box-hint">Click to record an entry by hand</span>
                </div>
              </div>
            </div>

            {/* Centralised documents table */}
            <div className="file-view-wrapper">
              <div className="file-list-container">
                {isLoading ? (
                  <p>Loading your documents...</p>
                ) : error ? (
                  <p style={{ color: "red" }}>{error}</p>
                ) : documents.length === 0 ? (
                  <p style={{ color: "#2c3e50ab" }}>
                    No documents uploaded yet. Use Statements, Receipts or Manual entry above to get started.
                  </p>
                ) : (
                  <>
                    <div className="uploads-toolbar">
                      <div className="uploads-filter-chips" role="group" aria-label="Filter by type">
                        <button
                          type="button"
                          className={`uploads-chip${typeFilter === "all" ? " active" : ""}`}
                          aria-pressed={typeFilter === "all"}
                          onClick={() => setTypeFilter("all")}
                        >
                          All ({dateFilteredRows.length})
                        </button>
                        {DOC_TYPES.map((type) => (
                          <button
                            type="button"
                            key={type}
                            className={`uploads-chip${typeFilter === type ? " active" : ""}`}
                            aria-pressed={typeFilter === type}
                            onClick={() => setTypeFilter(type)}
                          >
                            {type} ({typeCounts[type] || 0})
                          </button>
                        ))}
                      </div>

                      <div className="uploads-toolbar-row">
                        <label className="uploads-control">
                          <span>Sort by</span>
                          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                            {SORT_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </label>

                        <label className="uploads-control">
                          <span>Uploaded from</span>
                          <input
                            type="date"
                            value={dateFrom}
                            max={dateTo || undefined}
                            onChange={(e) => setDateFrom(e.target.value)}
                          />
                        </label>

                        <label className="uploads-control">
                          <span>Uploaded to</span>
                          <input
                            type="date"
                            value={dateTo}
                            min={dateFrom || undefined}
                            onChange={(e) => setDateTo(e.target.value)}
                          />
                        </label>

                        {hasActiveFilters && (
                          <button type="button" className="uploads-clear-filters" onClick={clearFilters}>
                            Clear filters
                          </button>
                        )}
                      </div>
                    </div>

                    {visibleRows.length === 0 ? (
                      <p style={{ color: "#2c3e50ab" }}>No uploads match the current filters.</p>
                    ) : (
                      <table className="file-table">
                        <thead>
                          <tr>
                            <th>File Name</th>
                            <th>Uploaded At</th>
                            <th>Type</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleRows.map(({ doc, type }) => {
                            const key = `${doc.category}-${doc.id}`;
                            return (
                              <tr
                                key={key}
                                onClick={() => handleRowClick(doc)}
                                style={{ cursor: "pointer" }}
                              >
                                <td>{doc.file_name}</td>
                                <td>{formatDate(doc.uploaded_at)}</td>
                                <td>
                                  <span
                                    className={`file-type-badge doc-type-${type
                                      .toLowerCase()
                                      .replace(" ", "-")}`}
                                  >
                                    {type}
                                  </span>
                                </td>
                                <td>
                                  <button
                                    type="button"
                                    className="uploads-delete-btn"
                                    disabled={deletingKey === key}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleDelete(doc);
                                    }}
                                  >
                                    {deletingKey === key ? "Deleting..." : "Delete"}
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <UploadModal
        file={pendingFile}
        name={pendingName}
        onNameChange={setPendingName}
        docType={pendingBox?.docType}
        category={pendingBox?.category}
        accounts={accounts}
        selectedAccount={selectedAccount}
        onSelectAccount={setSelectedAccount}
        selectedBank={selectedBank}
        onSelectBank={handleBankChange}
        currency={uploadCurrency}
        onCurrencyChange={setCurrencyChoice}
        reconcileLater={reconcileLater}
        onReconcileLaterChange={setReconcileLater}
        isUploading={isUploading}
        parse={parse}
        rows={lineRows}
        onRowsChange={setLineRows}
        availableTags={availableTags}
        onCreateTag={createTag}
        error={modalError}
        onCancel={closeModal}
        onConfirm={handleConfirmUpload}
      />

      <ManualEntryModal
        open={manualEntryOpen}
        accounts={accounts}
        availableTags={availableTags}
        onCreateTag={createTag}
        isSaving={isSavingManualEntry}
        error={manualEntryError}
        onCancel={() => {
          setManualEntryOpen(false);
          setManualEntryError(null);
        }}
        onSave={handleSaveManualEntry}
      />
    </div>
  );
};

export default Uploads;
