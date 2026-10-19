import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Navbar from "../components/Navbar";
import LineTable from "../components/LineTable";
import LineEditor from "../components/LineEditor";
import { LineBulkDelete, LineRemoveDialog } from "../components/LineDeletion";
import { useTags } from "../hooks/useTags";
import { useDocumentLines } from "../hooks/useDocumentLines";
import { useLineSelection } from "../hooks/useLineSelection";
import { useLineItemActions } from "../hooks/useLineItemActions";
import { columnsFor } from "../utils/lineItemSort";
import "../styles/FileListTable.css";
import "../styles/UploadDetail.css";
import "../styles/Statements.css";
import { documentService } from "../utils/api";
import "../styles/Transactions.css";

/* What a statement's own table shows: its account and source are the page's */
const STATEMENT_COLUMNS = columnsFor(["date", "description", "tags", "amount", "status", "matched", "direction"]);
import { usePageTitle } from "../components/PageTitle";

const formatDateTime = (dateString) => {
  if (!dateString) return "N/A";
  const parsed = new Date(dateString);
  return isNaN(parsed.getTime()) ? dateString : parsed.toLocaleString();
};

/* The transactions (line items) which were read from a single bank statement */
const StatementDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [statement, setStatement] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fileError, setFileError] = useState(null);

  const { tags: availableTags, createTag } = useTags();

  useEffect(() => {
    let isMounted = true;

    const fetchStatement = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await documentService.getStatement(id);
        if (isMounted) setStatement(data);
      } catch (err) {
        console.error("Failed to load statement", err);
        if (isMounted) {
          setError(
            err.status === 404
              ? "This statement could not be found."
              : "Failed to load this statement. Please try again later."
          );
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchStatement();
    return () => {
      isMounted = false;
    };
  }, [id]);

  /* the statement's lines, as the Transactions page has them, to edit, tag and remove */
  const { lines, setLines, reload, error: linesError } = useDocumentLines(id);
  const actions = useLineItemActions(setLines, reload);
  const selection = useLineSelection(lines || []);
  const [editingLine, setEditingLine] = useState(null);
  const [removingLine, setRemovingLine] = useState(null);

  const transactions = lines || [];
  const account = statement?.account;

  usePageTitle(statement?.file_name || "Statement");

  return (
    <div className="container statement-detail-page">
      <Navbar />
      <div className="statement-detail">
        <button type="button" className="upload-detail-back" onClick={() => navigate("/statements")}>
          &larr; Back to Statements
        </button>

        {isLoading ? (
          <p>Loading statement...</p>
        ) : error ? (
          <p style={{ color: "red" }}>{error}</p>
        ) : (
          <>
            <div className="statement-detail-header">
              {statement.file_path && (
                <button
                  type="button"
                  className="upload-detail-view-btn"
                  onClick={() => {
                    setFileError(null);
                    documentService
                      .openDocumentFile(id, "statement")
                      .catch(() => setFileError("This file could not be opened. Please try again later."));
                  }}
                >
                  View file
                </button>
              )}
            </div>
            {fileError && <p style={{ color: "red" }}>{fileError}</p>}

            <dl className="statement-detail-meta">
              <div>
                <dt>Account</dt>
                <dd>
                  {account.account_name || `${account.card_type} account`}
                  {account.account_number ? ` (...${account.account_number})` : ""}
                </dd>
              </div>
              <div>
                <dt>Uploaded at</dt>
                <dd>{formatDateTime(statement.uploaded_at)}</dd>
              </div>
              <div>
                <dt>File type</dt>
                <dd>{statement.doc_type || "-"}</dd>
              </div>
              <div>
                <dt>Transactions</dt>
                <dd>{transactions.length}</dd>
              </div>
            </dl>

            {linesError ? (
              <p style={{ color: "red" }}>{linesError}</p>
            ) : lines === null ? (
              <p>Loading the statement's lines...</p>
            ) : transactions.length === 0 ? (
              <p className="statement-detail-empty">
                No transactions have been read from this statement. If it was uploaded moments
                ago it may still be processing, so try refreshing in a few seconds.
              </p>
            ) : (
              <>
                <div className="statement-table-scroll scroll-area">
                  <LineTable
                    columns={STATEMENT_COLUMNS}
                    entries={transactions.map((line) => ({ type: "line", line, depth: 0 }))}
                    selection={selection}
                    onOpen={setEditingLine}
                    onRemove={setRemovingLine}
                    onRename={actions.saveName}
                    tags={{ available: availableTags, onChange: actions.saveTags, onCreate: createTag }}
                    label="Statement lines"
                  />
                </div>
                <LineBulkDelete selection={selection} removeMany={actions.removeMany} />
              </>
            )}
          </>
        )}
      </div>
      {removingLine && <LineRemoveDialog line={removingLine} onRemove={actions.remove} onClose={() => setRemovingLine(null)} />}
      {editingLine && <LineEditor line={editingLine} onSave={actions.saveDetails} onClose={() => setEditingLine(null)} />}
    </div>
  );
};

export default StatementDetail;
