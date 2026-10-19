import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";
import AccountModal from "../components/AccountModal";
import { AccountBalance } from "../components/AccountBalance";
import { documentService } from "../utils/api";
import { useAuth } from "../components/AuthContext";
import "../styles/Accounts.css";
import "../styles/AccountBalance.css";
import { usePageTitle } from "../components/PageTitle";

const CARD_TYPES = ["Cheque", "Savings", "Credit"];

/*
  Bank account management — also doubles as the gate new users hit right
  after registering, since the rest of the site requires at least one account.
  */
const Accounts = () => {
  usePageTitle("Bank Accounts");
  const [accounts, setAccounts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [accountName, setAccountName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [cardType, setCardType] = useState("Cheque");
  const [funds, setFunds] = useState("");
  const [formError, setFormError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  /* the account whose details and statements are open, if any */
  const [openAccount, setOpenAccount] = useState(null);

  const navigate = useNavigate();
  const { setHasAccount, currency: ownCurrency, currencies } = useAuth();
  /* what the new account's funds are in: the user's currency, until another is chosen */
  const [currencyChoice, setCurrencyChoice] = useState("");
  const accountCurrency = currencyChoice || ownCurrency;

  useEffect(() => {
    let isMounted = true;

    const fetchAccounts = async () => {
      try {
        setIsLoading(true);
        const data = await documentService.getAccounts();
        if (isMounted) setAccounts(data || []);
      } catch (err) {
        console.error("Failed to load accounts", err);
        // A 401 here is handled globally by AuthProvider (session-expired banner).
        if (isMounted && err.status !== 401) {
          setLoadError("Failed to load your accounts. Please try again later.");
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchAccounts();
    return () => {
      isMounted = false;
    };
  }, []);

  const resetForm = () => {
    setAccountName("");
    setAccountNumber("");
    setCardType("Cheque");
    setFunds("");
    setCurrencyChoice("");
  };

  /* An edited account: the list shows its new details */
  const handleAccountSaved = (updated) =>
    setAccounts((prev) => prev.map((acc) => (acc.id === updated.id ? { ...acc, ...updated } : acc)));

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError("");

    if (!accountName || !accountNumber || !cardType) {
      setFormError("Account name, account number, and card type are required.");
      return;
    }

    if (!/^\d{4}$/.test(accountNumber)) {
      setFormError("Account number must be exactly 4 digits.");
      return;
    }

    if (accounts.some((acc) => acc.account_number === accountNumber)) {
      setFormError("You already have an account with that account number.");
      return;
    }

    setIsSubmitting(true);
    try {
      const newAccount = await documentService.createAccount({
        account_name: accountName,
        account_number: accountNumber,
        card_type: cardType,
        funds: funds === "" ? 0 : funds,
        currency: accountCurrency,
      });

      const isFirstAccount = accounts.length === 0;
      setAccounts((prev) => [...prev, newAccount]);
      resetForm();

      /* First account created (e.g. straight after registering) */
      if (isFirstAccount) {
        setHasAccount(true);
        navigate("/dashboard");
      }
      console.log("[LOG]: Bank Account created successfully! Redirecting user to dashboard...")
    } catch (err) {
      console.error("Failed to create account", err);
      setFormError(err.message || "Failed to create account. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <Navbar />
      <div className="container">
        <div className="accounts-container">
          <div className="accounts-content">
            <div className="accounts-header">
              <p className={accounts.length === 0 && !isLoading ? "creation-msg" : undefined}>
                {accounts.length === 0 && !isLoading
                  ? "Create at least one bank account to start using the site."
                  : "Manage your bank accounts or add a new one."}
              </p>
            </div>

            <div className="accounts-body">
              <div className="account-card account-form-card">
                <h2>New Account</h2>
                <form onSubmit={handleSubmit} className="account-form">
                  <div className="account-field">
                    <label>Account Name</label>
                    <input
                      type="text"
                      placeholder="e.g. Everyday Account"
                      value={accountName}
                      onChange={(e) => setAccountName(e.target.value)}
                    />
                  </div>

                  <div className="account-field">
                    <label>Account Number</label>
                    <input
                      type="text"
                      inputMode="numeric"
                      maxLength={4}
                      placeholder="4-digit account number"
                      value={accountNumber}
                      onChange={(e) => setAccountNumber(e.target.value.replace(/\D/g, "").slice(0, 4))}
                    />
                  </div>

                  <div className="account-field">
                    <label>Card Type</label>
                    <select value={cardType} onChange={(e) => setCardType(e.target.value)}>
                      {CARD_TYPES.map((type) => (
                        <option key={type} value={type}>{type}</option>
                      ))}
                    </select>
                  </div>

                  <div className="account-field">
                    <label>Currency</label>
                    <select value={accountCurrency} onChange={(e) => setCurrencyChoice(e.target.value)}>
                      {currencies.length === 0 && <option value={accountCurrency}>{accountCurrency}</option>}
                      {currencies.map((c) => (
                        <option key={c.code} value={c.code}>
                          {c.code} · {c.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="account-field">
                    <label>Opening Balance (optional)</label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="0.00"
                      value={funds}
                      onChange={(e) => setFunds(e.target.value)}
                    />
                  </div>

                  {formError && <p className="account-form-error">{formError}</p>}

                  <button type="submit" className="account-submit-btn" disabled={isSubmitting}>
                    {isSubmitting ? "Creating..." : "Create Account"}
                  </button>
                </form>
              </div>

              <div className="account-card account-list-card">
                <h2>Your Accounts</h2>
                {isLoading ? (
                  <p className="account-list-status">Loading your accounts...</p>
                ) : loadError ? (
                  <p className="account-list-status error">{loadError}</p>
                ) : accounts.length === 0 ? (
                  <p className="account-list-status">You don't have any accounts yet.</p>
                ) : (
                  <>
                  <p className="account-list-hint">Click on a bank account to edit its details and see the statements associated with it.</p>
                  <ul className="account-list">
                    {accounts.map((acc) => (
                      <li key={acc.id}>
                        <button
                          type="button"
                          className={`account-list-item${acc.warning ? " has-warning" : ""}`}
                          onClick={() => setOpenAccount(acc)}
                        >
                          <span className="account-list-main">
                            <span className="account-list-name">
                              {acc.account_name}
                              {acc.warning && (
                                <span className="account-warning-badge" title={acc.warning}>
                                  Below zero
                                </span>
                              )}
                            </span>
                            <span className="account-list-meta">{acc.card_type} &middot; ...{acc.account_number} &middot; {acc.currency}</span>
                          </span>
                          <AccountBalance account={acc} compact />
                        </button>
                      </li>
                    ))}
                  </ul>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {openAccount && (
        <AccountModal
          account={openAccount}
          accounts={accounts}
          onClose={() => setOpenAccount(null)}
          onSaved={handleAccountSaved}
        />
      )}
    </>
  );
};

export default Accounts;
