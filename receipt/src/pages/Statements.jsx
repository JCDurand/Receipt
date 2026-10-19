import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";
import upload_logo from "../assets/upload_logo.png";
import "../styles/PageFormat.css";
import "../styles/FileListTable.css";
import "../styles/UploadBox.css";
import "../styles/Banners.css";
import "../styles/Statements.css";
import { documentService } from "../utils/api";
import { usePageTitle } from "../components/PageTitle";

const formatDate = (dateString) => {
  if (!dateString) return "N/A";
  const parsed = new Date(dateString);
  return isNaN(parsed.getTime()) ? dateString : parsed.toLocaleString();
};

const accountLabel = (account) =>
  account
    ? `${account.account_name || `${account.card_type} account`}${
        account.account_number ? ` (...${account.account_number})` : ""
      }`
    : "-";

/*
  Bank statements which have been uploaded. Statements are added from the
  Source Documents page; clicking one here opens the transactions read from it.
  */
const Statements = () => {
  usePageTitle("Statements");
  const navigate = useNavigate();

  const [documents, setDocuments] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [deletingId, setDeletingId] = useState(null);

  /* Fetch statements on mount */
  useEffect(() => {
    let isMounted = true;

    const fetchData = async () => {
      setIsLoading(true);

      const [docsResult, accountsResult] = await Promise.allSettled([
        documentService.getDocuments("statement"),
        documentService.getAccounts(),
      ]);

      if (!isMounted) return;

      if (docsResult.status === "fulfilled") {
        setDocuments(docsResult.value || []);
      } else {
        console.error("Failed to load statements", docsResult.reason);
        setError("Failed to load your statements. Please try again later.");
      }

      /* Accounts only label the table, so the table still works without them */
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

  const accountsById = useMemo(
    () => Object.fromEntries(accounts.map((account) => [account.id, account])),
    [accounts]
  );

  const visibleDocuments = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return documents
      .filter(
        (doc) =>
          !term ||
          doc.file_name?.toLowerCase().includes(term) ||
          accountLabel(accountsById[doc.meta?.account]).toLowerCase().includes(term)
      )
      .sort((a, b) => new Date(b.uploaded_at || 0) - new Date(a.uploaded_at || 0));
  }, [documents, searchTerm, accountsById]);

  const openStatement = (doc) => navigate(`/statements/${doc.id}`);

  const handleDelete = async (doc) => {
    if (!window.confirm(`Are you sure you want to delete "${doc.file_name}"?`)) return;

    setDeletingId(doc.id);
    try {
      await documentService.deleteDocument(doc.id, "statement");
      /* Remove document from current page */
      setDocuments((prevDocs) => prevDocs.filter((d) => d.id !== doc.id));
    } catch (err) {
      console.error("Failed to delete", err);
      alert("Failed to delete the statement: " + err.message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="container">
      <Navbar />
      <div className="scans-container">
        <div className="scans-content">
          <div className="scans-dashboard">
            <div className="page-header">
              <p>
                The bank statements you have uploaded. Click a statement to see the line items
                read from it.
              </p>
            </div>

            <div className="file-view-wrapper">
              {isLoading ? (
                <p>Loading your statements...</p>
              ) : error ? (
                <p style={{ color: "red" }}>{error}</p>
              ) : documents.length === 0 ? (
                <div className="first-upload-container">
                  <div className="first-upload-image">
                    <img src={upload_logo} alt="upload logo" />
                  </div>
                  <div className="first-upload-desc">
                    You have not yet uploaded a bank statement. Statements are added on the{" "}
                    <Link to="/uploads">Source Documents</Link> page and will be listed here.
                  </div>
                </div>
              ) : (
                <div className="file-list-container">
                  <div className="statements-toolbar">
                    <input
                      type="text"
                      className="statements-search"
                      placeholder="Search by statement or account..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      aria-label="Search statements"
                    />
                    <span className="statements-count">
                      {visibleDocuments.length} of {documents.length}{" "}
                      {documents.length === 1 ? "statement" : "statements"}
                    </span>
                  </div>

                  {visibleDocuments.length === 0 ? (
                    <p style={{ color: "#2c3e50ab" }}>No statements match your search.</p>
                  ) : (
                    <table className="file-table">
                      <thead>
                        <tr>
                          <th>Statement</th>
                          <th>Account</th>
                          <th>Uploaded At</th>
                          <th>Transactions</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleDocuments.map((doc) => (
                          <tr
                            key={doc.id}
                            className="statements-row"
                            tabIndex={0}
                            onClick={() => openStatement(doc)}
                            onKeyDown={(e) => {
                              if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
                                e.preventDefault();
                                openStatement(doc);
                              }
                            }}
                          >
                            <td>{doc.file_name}</td>
                            <td>{accountLabel(accountsById[doc.meta?.account])}</td>
                            <td>{formatDate(doc.uploaded_at)}</td>
                            <td>{doc.meta?.transaction_count ?? "-"}</td>
                            <td>
                              <button
                                type="button"
                                className="uploads-delete-btn"
                                disabled={deletingId === doc.id}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDelete(doc);
                                }}
                              >
                                {deletingId === doc.id ? "Deleting..." : "Delete"}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Statements;
