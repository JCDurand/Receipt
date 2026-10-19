import ConversionBadge from "../components/ConversionBadge";
import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import Navbar from "../components/Navbar";
import MatchModal from "../components/MatchModal";
import LinkAccountModal from "../components/LinkAccountModal";
import ConfirmDialog from "../components/ConfirmDialog";
import StatementTree from "../components/StatementTree";
import LineItemName from "../components/LineItemName";
import { documentService } from "../utils/api";
import { accountLabel, directionKey, formatDay, shownName } from "../utils/format";
import { absAmount } from "../utils/lineItems";
import { toCents } from "../utils/spending";
import "../styles/Review.css";
import { usePageTitle } from "../components/PageTitle";

const NOTICE_MS = 6000;

const Review = () => {
  usePageTitle("Review");
  const [isLoading, setIsLoading] = useState(true);
  const [err, setError] = useState(null);
  /* Receipts waiting to be matched, each with the line items read from it */
  const [pendingReceipts, setPendingReceipts] = useState([]);
  /* Every uploaded statement, each with the line items read from it */
  const [statements, setStatements] = useState([]);
  const [accounts, setAccounts] = useState([]);
  /* receipt whose Match modal is open, if any */
  const [matchingReceipt, setMatchingReceipt] = useState(null);
  /* receipt whose Link account modal is open, if any */
  const [linkingReceipt, setLinkingReceipt] = useState(null);
  /* receipt being dragged from the left, if any */
  const [draggedReceipt, setDraggedReceipt] = useState(null);
  /* a match whose amounts differ, waiting for the user to say it is fine */
  const [pendingMatch, setPendingMatch] = useState(null);
  /* ids of the receipts whose line items are hidden; all start expanded */
  const [collapsedReceiptIds, setCollapsedReceiptIds] = useState(() => new Set());
  /* what the popup reports of the last match, if it is showing */
  const [notice, setNotice] = useState(null);

  /* Every receipt which has not been matched to a bank statement line waits here,
     with all the line items read from it. It is the receipt as a whole which is
     matched, not its items. Cash manual entries never appear here: the API
     serves them under their own "cash" category rather than "receipt". */
  const toPendingReceipts = (receipts) =>
    receipts
      .filter((doc) => !doc.has_transaction)
      .map((doc) => {
        const items = (doc.meta?.items || []).map((item) => ({
          id: item.id,
          /* the name it was read with, and the alias the user has given it, if any */
          name: item.item_name,
          alias: item.display_name,
          merchant: item.merchant,
          date: item.date,
          direction: item.direction,
          amount: item.item_total,
          /* amounts are shown in the user's currency; these say what was recorded */
          shown: item,
        }));
        /* a receipt with no total of its own is worth what its items add up to */
        const total =
          doc.meta?.amount ??
          (items.length > 0 ? (items.reduce((sum, item) => sum + toCents(item.amount), 0) / 100).toFixed(2) : null);

        return {
          id: doc.id,
          name: doc.file_name,
          date: doc.meta?.transaction_date || doc.uploaded_at,
          merchant: doc.meta?.merchant_name,
          accountId: doc.meta?.account || null,
          total,
          /* the total as recorded, in the receipt's own currency, for comparing with
             a statement line recorded in the same one */
          currency: doc.meta?.currency || null,
          recordedTotal:
            doc.meta?.amount_original_amount ??
            doc.meta?.amount ??
            (items.length > 0
              ? (items.reduce((sum, item) => sum + toCents(item.shown.original_amount ?? item.amount), 0) / 100).toFixed(2)
              : null),
          items,
        };
      });

  useEffect(() => {
    let isMounted = true;

    const fetchData = async () => {
      try {
        setIsLoading(true);
        setError(null);

        /* Fetch receipts, statements and accounts on mount */
        const [receiptsData, statementsData, accountsData] = await Promise.all([
          documentService.getDocuments("receipt").catch(() => []),
          documentService.getDocuments("statement").catch(() => []),
          documentService.getAccounts().catch(() => []),
        ]);

        /* The list of statements does not include their line items, so each
           statement is then fetched for its own. One which fails to load is
           left out rather than failing the page. */
        const loaded = await Promise.all(
          (statementsData || []).map((doc) => documentService.getStatement(doc.id).catch(() => null))
        );

        if (isMounted) {
          setPendingReceipts(toPendingReceipts(receiptsData || []));
          setAccounts(accountsData || []);
          setStatements(
            loaded
              .filter(Boolean)
              .sort((a, b) => new Date(b.uploaded_at || 0) - new Date(a.uploaded_at || 0))
          );
        }
      } catch (error) {
        if (isMounted) {
          console.error("Failed to load receipts to review:", error);
          setError("Failed to load documents from the database. Please try again later.");
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      isMounted = false;
    };
  }, []);

  /* The popup dismisses itself */
  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  const formatDate = (dateString) => {
    if (!dateString) return "-";
    const parsed = new Date(dateString);
    return isNaN(parsed.getTime()) ? dateString : parsed.toLocaleDateString("en-ZA", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const accountName = (accountId) => {
    const account = accounts.find((acc) => acc.id === accountId);
    return account ? accountLabel(account) : null;
  };

  /* Matches the receipt to the statement line for real: the server links them,
     marks the line as reconciled and has the receipt take the line's amount.
     The receipt then leaves the queue. */
  const performMatch = async (receipt, statement, transaction) => {
    try {
      await documentService.updateDocument(receipt.id, transaction.id);
    } catch (error) {
      console.error("Failed to match the receipt:", error);
      setNotice({ kind: "error", message: error.serverMessage || error.message || "The receipt could not be matched." });
      return;
    }

    setPendingReceipts((prev) => prev.filter((r) => r.id !== receipt.id));
    setStatements((prev) =>
      prev.map((s) =>
        s.id === statement.id
          ? {
              ...s,
              transactions: s.transactions.map((t) =>
                t.id === transaction.id ? { ...t, matched: true, status: "Reconciled" } : t
              ),
            }
          : s
      )
    );
    setNotice({ kind: "success", receipt, statement, transaction });
  };

  /* Choosing a statement line, in the modal or by dropping the receipt on it. If
     the amounts differ the user is asked first, as matching makes the receipt
     take the statement's amount. */
  const requestMatch = (receipt, statement, transaction) => {
    setMatchingReceipt(null);

    if (transaction.matched) {
      setNotice({ kind: "error", message: "That statement line has already been matched." });
      return;
    }

    /* Both are shown converted, each at its own day's rate, so two documents in the
       same foreign currency are compared as they were recorded, not as converted */
    const recorded = receipt.currency && receipt.currency === transaction.original_currency;
    const receiptAmount = recorded ? receipt.recordedTotal : receipt.total;
    const lineAmount = recorded ? transaction.original_amount : transaction.amount;
    const receiptCents = receiptAmount == null ? 0 : toCents(receiptAmount);
    if (receiptCents !== 0 && receiptCents !== Math.abs(toCents(lineAmount))) {
      setPendingMatch({ receipt, statement, transaction });
    } else {
      performMatch(receipt, statement, transaction);
    }
  };

  const confirmMismatch = () => {
    const { receipt, statement, transaction } = pendingMatch;
    setPendingMatch(null);
    performMatch(receipt, statement, transaction);
  };

  /* Save the name the user gives a line item (an alias; the name it was read
     with is kept), then show the saved one. A failure is thrown to the name,
     which reports it. */
  const handleItemName = async (receipt, item, name) => {
    const saved = await documentService.setItemName(item.id, name);
    setPendingReceipts((prev) =>
      prev.map((r) =>
        r.id === receipt.id
          ? { ...r, items: r.items.map((i) => (i.id === item.id ? { ...i, alias: saved.display_name } : i)) }
          : r
      )
    );
  };

  const handleTransactionName = async (statement, transaction, name) => {
    const saved = await documentService.setTransactionName(transaction.id, name);
    setStatements((prev) =>
      prev.map((s) =>
        s.id === statement.id
          ? {
              ...s,
              transactions: s.transactions.map((t) =>
                t.id === transaction.id ? { ...t, display_name: saved.display_name } : t
              ),
            }
          : s
      )
    );
  };

  const handleAccountLinked = (receiptId, accountId) => {
    setPendingReceipts((prev) => prev.map((r) => (r.id === receiptId ? { ...r, accountId } : r)));
    setLinkingReceipt(null);
  };

  const toggleReceipt = (id) =>
    setCollapsedReceiptIds((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const closeMatchModal = useCallback(() => setMatchingReceipt(null), []);
  const closeLinkModal = useCallback(() => setLinkingReceipt(null), []);

  /* functions for dragging a receipt onto a statement's line item */
  const handleReceiptDragStart = (evt, receipt) => {
    evt.dataTransfer.setData("text/plain", receipt.name || ""); /* Firefox will not drag without data */
    evt.dataTransfer.effectAllowed = "link";
    setDraggedReceipt(receipt);
  };

  const handleReceiptDragEnd = () => setDraggedReceipt(null);

  const handleDropOnTransaction = (statement, transaction) => {
    if (draggedReceipt) requestMatch(draggedReceipt, statement, transaction);
    setDraggedReceipt(null);
  };

  /* A receipt with a bank account can only be matched to that account's statements */
  const statementsFor = (receipt) =>
    receipt.accountId ? statements.filter((s) => s.account?.id === receipt.accountId) : statements;

  return (
    <>
      <Navbar />
      <div className="container review-page">
        <div className="table-section review-section">
          <div className="review-header">
            <p>
              Receipts wait here until they are matched to a line on a bank statement. Use a receipt's
              Match button, or drag the receipt onto a statement line. A receipt uploaded with
              "Reconcile later" needs its bank account linked first.
            </p>
          </div>

          {isLoading ? (
            <div style={{ textAlign: "center", padding: "40px", borderRadius: "12px", border: "1px dashed #151313ff" }}>
              <p style={{ color: "#666", margin: 0, fontWeight: "500" }}>
                Loading receipts from database...
              </p>
            </div>
          ) : err ? (
            <div style={{ textAlign: "center", padding: "40px", borderRadius: "12px", border: "1px dashed #ff6b6b" }}>
              <p style={{ color: "#ff6b6b", margin: 0, fontWeight: "500" }}>{err}</p>
            </div>
          ) : pendingReceipts.length > 0 ? (
            <div className="review-columns">
              { /* Receipts to match, with the line items read from each */ }
              <section className="review-panel">
                <h3 className="review-panel-title">Receipts to match</h3>
                <div className="review-panel-body">
                  <div className="pending-cols-head">
                    <span>Line Item</span>
                    <span>Amount</span>
                  </div>

                  {pendingReceipts.map((receipt) => {
                    const isCollapsed = collapsedReceiptIds.has(receipt.id);
                    const linesId = `pending-lines-${receipt.id}`;
                    const account = accountName(receipt.accountId);
                    const itemCount = receipt.items.length;

                    return (
                      <div className="pending-group" key={receipt.id}>
                        <div
                          className={`pending-group-head${draggedReceipt?.id === receipt.id ? " is-dragging" : ""}`}
                          draggable
                          onDragStart={(evt) => handleReceiptDragStart(evt, receipt)}
                          onDragEnd={handleReceiptDragEnd}
                        >
                          <div
                            className="group-toggle"
                            role="button"
                            tabIndex={0}
                            aria-expanded={!isCollapsed}
                            aria-controls={linesId}
                            onClick={() => toggleReceipt(receipt.id)}
                            onKeyDown={(evt) => {
                              if (evt.key === "Enter" || evt.key === " ") {
                                evt.preventDefault();
                                toggleReceipt(receipt.id);
                              }
                            }}
                          >
                            <span className={`group-toggle-chevron${isCollapsed ? "" : " is-open"}`} aria-hidden="true">
                              &#9656;
                            </span>
                            <span className="group-toggle-heading">
                              <span className="pending-group-name" title={receipt.name}>{receipt.name}</span>
                              <span className="pending-group-meta">
                                {receipt.merchant || "Unknown merchant"} · {formatDate(receipt.date)} · {itemCount}{" "}
                                {itemCount === 1 ? "line item" : "line items"}
                                {receipt.total != null && (
                                  <>
                                    {" · "}
                                    <span className="nowrap">Total {receipt.total}</span>
                                  </>
                                )}
                              </span>
                              <span className={`pending-group-meta pending-group-account${receipt.accountId ? "" : " is-unlinked"}`}>
                                {receipt.accountId
                                  ? `Account: ${account || "linked"}`
                                  : "No bank account linked (reconcile later)"}
                              </span>
                            </span>
                          </div>

                          <div className="pending-group-actions">
                            <button
                              type="button"
                              className="link-account-btn"
                              onClick={() => setLinkingReceipt(receipt)}
                            >
                              {receipt.accountId ? "Change account" : "Link account"}
                            </button>
                            <button type="button" className="match-btn" onClick={() => setMatchingReceipt(receipt)}>
                              Match
                            </button>
                          </div>
                        </div>

                        {!isCollapsed &&
                          (itemCount === 0 ? (
                            <p className="pending-empty" id={linesId}>
                              No line items were read from this receipt.
                            </p>
                          ) : (
                            <ul className="pending-lines" id={linesId}>
                              {receipt.items.map((item) => (
                                <li key={item.id} className={`pending-line is-${directionKey(item.direction)}`}>
                                  <span className="pending-line-desc">
                                    <LineItemName
                                      name={item.name}
                                      alias={item.alias}
                                      fallback="Untitled Item"
                                      onRename={(name) => handleItemName(receipt, item, name)}
                                    />
                                    {(item.merchant || item.date) && (
                                      <span className="pending-line-meta">
                                        {[item.merchant, item.date && formatDay(item.date)].filter(Boolean).join(" · ")}
                                      </span>
                                    )}
                                  </span>
                                  <span className={`pending-line-amount is-${directionKey(item.direction)}`}>
                                    {item.amount ? absAmount(item.amount) : "-"} <ConversionBadge line={item.shown} />
                                  </span>
                                </li>
                              ))}
                            </ul>
                          ))}
                      </div>
                    );
                  })}
                </div>
              </section>

              { /* Statements and their line items */ }
              <section className="review-panel">
                <h3 className="review-panel-title">Statements</h3>
                <div className="review-panel-body">
                  {statements.length === 0 ? (
                    <p className="review-empty-note">
                      No statements have been uploaded. Add one on the <Link to="/uploads">Source Documents</Link> page.
                    </p>
                  ) : (
                    <StatementTree
                      statements={statements}
                      onDropOnTransaction={handleDropOnTransaction}
                      onRenameTransaction={handleTransactionName}
                    />
                  )}
                </div>
              </section>
            </div>
          ) : (
            /* Interim table: not the same class as in other pages */
            <div style={{ textAlign: "center", padding: "40px", borderRadius: "12px", border: "1px dashed #100c0cff" }}>
              <p style={{ color: "#666", margin: "0 0 8px 0", fontWeight: "500" }}>
                No receipts to review.
              </p>
              <p style={{ color: "#999", margin: 0, fontSize: "0.85rem" }}>
                Receipts you upload wait here until they are matched to a line on a bank statement.
              </p>
            </div>
          )}
        </div>
      </div>

      {matchingReceipt && (
        <MatchModal
          receipt={matchingReceipt}
          statements={statementsFor(matchingReceipt)}
          accountName={matchingReceipt.accountId ? accountName(matchingReceipt.accountId) : null}
          onClose={closeMatchModal}
          onSelect={requestMatch}
        />
      )}

      {linkingReceipt && (
        <LinkAccountModal
          receipt={linkingReceipt}
          accounts={accounts}
          onClose={closeLinkModal}
          onLinked={handleAccountLinked}
        />
      )}

      {pendingMatch && (
        <ConfirmDialog
          title="The amounts do not match"
          confirmLabel="Match anyway"
          onConfirm={confirmMismatch}
          onCancel={() => setPendingMatch(null)}
        >
          <p>
            The receipt total is {pendingMatch.receipt.total}, but the statement line is{" "}
            {(Math.abs(toCents(pendingMatch.transaction.amount)) / 100).toFixed(2)}.
          </p>
          <p>
            The statement is the authoritative record, so matching will update the receipt's total to
            the statement's amount.
          </p>
        </ConfirmDialog>
      )}

      {notice && (
        <div className={`match-notice${notice.kind === "error" ? " is-error" : ""}`} role="status">
          <div>
            <strong>{notice.kind === "error" ? "Could not match" : "Receipt matched"}</strong>
            <p>
              {notice.kind === "error"
                ? notice.message
                : `"${notice.receipt.name}" has been matched to "${shownName(notice.transaction.description, notice.transaction.display_name) || "-"}" in ${notice.statement.file_name}.`}
            </p>
          </div>
          <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss">
            &times;
          </button>
        </div>
      )}
    </>
  );
};

export default Review;
