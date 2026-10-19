import { notifySessionExpired } from './sessionEvents';
import { refreshAccessToken } from './tokenRefresh';

import { API_BASE_URL } from './apiBase';

/* Sends a request with the login token. If the token has expired, a new one is
   fetched and the request is sent once more. */
const sendWithAuth = async (endpoint, options = {}) => {
  const send = () => {
    const token = localStorage.getItem('access_token');
    return fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        ...options.headers,
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
    });
  };

  const response = await send();
  if (response.status !== 401) {
    return response;
  }
  try {
    await refreshAccessToken();
  } catch (e) {
    return response;
  }
  return send();
};

export const fetchWithAuth = async (endpoint, options = {}) => {
  const response = await sendWithAuth(endpoint, options);

  if (!response.ok) {
    let errorMsg = 'API request failed';
    try {
      const errorData = await response.json();
      errorMsg = errorData.error || errorData.detail || JSON.stringify(errorData);
    } catch (e) {
      errorMsg = response.statusText;
    }
    const error = new Error(`Error ${response.status}: ${errorMsg}`);
    error.status = response.status;
    /* the server's own words, without the status in front, for showing to the user */
    error.serverMessage = errorMsg;

    if (response.status === 401) {
      notifySessionExpired();
    }

    throw error;
  }

  if (response.status === 204) {
    return null; 
  }

  return response.json();
};

export const documentService = {
  /* The signed-in user: their username and first and last name. The login token
     holds only their id. */
  getProfile: () => fetchWithAuth('/auth/user/'),

  /* The user's preferences: { currency, currencies: [{ code, name }] }. The
     currency is the one every amount is reported in; line items the server
     lists are already converted into it. */
  getSettings: () => fetchWithAuth('/settings/'),

  updateSettings: (changes) =>
    fetchWithAuth('/settings/', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    }),

  getAccounts: () => fetchWithAuth('/accounts/'),

  /* Every account's balance through time: { currency, accounts: [{ id,
     account_name, opened_on, opening, balance, balance_converted, warning,
     points: [{ date, balance, in, out, balance_converted, in_converted,
     out_converted }] }] }, each point the end of a day it moved */
  getAccountHistory: () => fetchWithAuth('/accounts/history/'),

  /* An account with the statements uploaded to it */
  getAccount: (id) => fetchWithAuth(`/accounts/${id}/`),

  /* Saves the details sent (any of account_name, account_number, card_type and
     funds); the account's statements, transactions and receipts refer to it,
     so they show the new details from then on. Resolves with the account. */
  updateAccount: (id, details) =>
    fetchWithAuth(`/accounts/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(details),
    }),

  createAccount: (account) =>
    fetchWithAuth('/accounts/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(account),
    }),

  getDocuments: (category) =>
    fetchWithAuth(category ? `/documents/?category=${category}` : '/documents/'),
  
  uploadDocument: (formData) =>
    fetchWithAuth('/documents/upload/', {
      method: 'POST',
      body: formData,
    }),

  /* A statement with its account and the transactions read from it */
  getStatement: (id) => fetchWithAuth(`/documents/statements/${id}/`),

  /* Reads a receipt's line items, or a bank statement's transactions, without
     saving it. `category` is "receipt" or "statement". Resolves with, for a receipt,
     { items, issues, merchant_name, transaction_date, total_amount } and, for a
     statement, { transactions, issues }. */
  parseDocument: (file, category = 'receipt', bank = 'investec') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category);
    if (bank) {
      formData.append('bank', bank);
    }
    return fetchWithAuth('/documents/parse/', {
      method: 'POST',
      body: formData,
    });
  },

  createManualEntry: (payload) =>
    fetchWithAuth('/documents/manual/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  /* Opens a document's file in a new tab. The file needs the login token, so
     it is fetched here rather than linked to. The tab is opened before the
     fetch so the browser still counts it as the user's click. */
  openDocumentFile: async (id, category) => {
    const tab = window.open('', '_blank');
    try {
      const response = await sendWithAuth(`/documents/${id}/file/?category=${category}`);
      if (response.status === 401) {
        notifySessionExpired();
      }
      if (!response.ok) {
        const error = new Error(`Error ${response.status}: the file could not be opened`);
        error.status = response.status;
        throw error;
      }
      const url = URL.createObjectURL(await response.blob());
      if (tab) {
        tab.location = url;
      } else {
        window.open(url, '_blank');
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {
      if (tab) tab.close();
      throw error;
    }
  },

  deleteDocument: (id, category) =>
    fetchWithAuth(`/documents/${id}/?category=${category}`, {
      method: 'DELETE',
    }),

  renameDocument: (id, category, displayName) =>
    fetchWithAuth(`/documents/${id}/rename/?category=${category}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName }),
    }),

  /* Links a receipt to the bank account it was paid from, for one uploaded
     before that was known ("reconcile later") */
  setReceiptAccount: (receiptId, accountId) =>
    fetchWithAuth(`/documents/receipts/${receiptId}/account/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account: accountId }),
    }),

  /* Matches a whole receipt to a bank statement line. The statement is
     authoritative: the receipt takes the line's amount (and its account, if the
     receipt had none). Resolves with { id, transaction, account, total_amount }. */
  updateDocument: (receiptId, transactionId) =>
    fetchWithAuth(`/documents/update/${receiptId}/?target=${transactionId}`, {
      method: 'PATCH',
    }),

  linkItem: (itemId, transactionId) =>
    fetchWithAuth(`/documents/items/${itemId}/link/?target=${transactionId}`, {
      method: 'PATCH',
    }),

  /* Every line item: the lines of the user's bank statements and the items on
     their receipts, each with all of its details and its tags */
  getLineItems: () => fetchWithAuth('/line-items/'),

  /* The tags which can be applied: the predefined ones and the user's own */
  getTags: () => fetchWithAuth('/tags/'),

  createTag: (name, parentId = null) =>{
    const payload = { name };
    if (parentId) {
      payload.parent = parentId;
    }
    return fetchWithAuth('/tags/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  getTemplates: () => fetchWithAuth('/templates/'),

  createTemplate: (payload) =>
    fetchWithAuth('/templates/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  deleteTemplate: (id) =>
    fetchWithAuth(`/templates/${id}/`, {
      method: 'DELETE',
    }),
    
  updateTemplate: (id, payload) =>
    fetchWithAuth(`/templates/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  /* Each replaces all of the line item's tags with tagIds, and resolves with
     the line item's tags as { id, name } in its `tags` */
  setItemTags: (itemId, tagIds) =>
    fetchWithAuth(`/documents/items/${itemId}/tags/`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: tagIds }),
    }),

  setTransactionTags: (transactionId, tagIds) =>
    fetchWithAuth(`/documents/transactions/${transactionId}/tags/`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: tagIds }),
    }),
    
    updateTag: (id, payload) =>
      fetchWithAuth(`/tags/${id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    }),
    
    deleteTag: (id) =>
      fetchWithAuth(`/tags/${id}/`, {
        method: 'DELETE',
      }),

  /* Monthly budgets, one per tag and one overall (tag null), as { id, tag,
     tag_name, monthly_limit, start_month, months }. A budget applies for
     `months` months from `start_month` (YYYY-MM-01), or for good when `months`
     is null. */
  getBudgets: () => fetchWithAuth('/budgets/'),

  createBudget: ({ tag = null, monthly_limit, start_month, months = null }) =>
    fetchWithAuth('/budgets/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tag, monthly_limit, start_month, months }),
    }),

  /* Changes any of monthly_limit, start_month and months */
  updateBudget: (id, changes) =>
    fetchWithAuth(`/budgets/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    }),

  deleteBudget: (id) => fetchWithAuth(`/budgets/${id}/`, { method: 'DELETE' }),

  /* Each changes a saved line item's details: any of display_name, merchant, date
     (YYYY-MM-DD, or null to have its receipt's) and direction ("debit" or
     "credit") in `changes`. The display_name is an alias: the name the line item
     was read with is never changed, and a blank one takes the alias away.
     Resolves with the line item as getLineItems lists it. A refusal is
     rejected with the server's reasons in its `serverMessage`. */
  updateItem: (itemId, changes) =>
    fetchWithAuth(`/documents/items/${itemId}/details/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    }),

  updateTransaction: (transactionId, changes) =>
    fetchWithAuth(`/documents/transactions/${transactionId}/details/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    }),

  /* Each marks a line item as a subscription (on) or takes the mark off, and
     resolves with the line item as getLineItems lists it, its `is_subscription`
     saying which. The mark is not one of the line item's tags. */
  setTransactionSubscription: (transactionId, on) =>
    fetchWithAuth(`/documents/transactions/${transactionId}/subscription/`, { method: on ? 'PUT' : 'DELETE' }),

  setItemSubscription: (itemId, on) =>
    fetchWithAuth(`/documents/items/${itemId}/subscription/`, { method: on ? 'PUT' : 'DELETE' }),

  /* The line items marked as subscriptions, grouped into one per thing paid for:
     { subscriptions: [{ name, amount, last_charged, next_expected, charges,
     account, lines }], monthly_total }, the soonest next charge first */
  getSubscriptions: () => fetchWithAuth('/subscriptions/'),

  /* Each removes a line item for good, and resolves with null. Removing a receipt
     item takes it out of its receipt's total (if that is what the total is made
     of); removing a statement line leaves a receipt which was matched to it
     unmatched. Other line items can change with it, so list them again. */
  removeItem: (itemId) => fetchWithAuth(`/documents/items/${itemId}/`, { method: 'DELETE' }),

  /* Removes several line items at once, given as [{ id, kind }] (kind is
     "statement_line" or "receipt_item"). All go or none. Resolves with
     { deleted, removed_statements, removed_receipts }: a statement or receipt
     with no line items left goes with them. */
  removeLineItems: (lines) =>
    fetchWithAuth('/line-items/delete/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines: lines.map(({ id, kind }) => ({ id, kind })) }),
    }),

  removeTransaction: (transactionId) =>
    fetchWithAuth(`/documents/transactions/${transactionId}/`, { method: 'DELETE' }),

  /* Just the alias: resolves with { ..., display_name }, null when there is none */
  setItemName: (itemId, displayName) => documentService.updateItem(itemId, { display_name: displayName }),

  setTransactionName: (transactionId, displayName) =>
    documentService.updateTransaction(transactionId, { display_name: displayName }),
};
