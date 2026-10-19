import TagPicker from "./TagPicker";
import { DIRECTIONS, absAmount, quantityPatch } from "../utils/lineItems";
import "../styles/LineItemsTable.css";

/**
 * Line items which have not been saved yet, as a table which is filled in: for a
 * manual entry, or the lines read from a receipt or statement in the upload
 * dialog. Each row has a name, merchant, date, debit/credit, total and tags, and
 * (with `showQuantity`, for receipt items: a bank statement's lines have none) a
 * quantity, which is how many of the item the line is for (see utils/lineItems.js
 * for the row).
 *
 * The merchant, date, debit/credit, quantity and tags can always be changed. The name and
 * the total can too when `editableCore` is set (a manual entry, where the user
 * is the source); those read from a file are shown as they were read. A debit is
 * red and a credit green, and neither has a sign: the colour and the Debit/Credit
 * column say which it is.
 */
const LineItemsTable = ({ rows, onChange, availableTags, onCreateTag, editableCore = false, requireDate = false, showQuantity = false }) => {
  const update = (key, patch) => onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  const remove = (key) => onChange(rows.filter((row) => row.key !== key));

  return (
    <div className="li-scroll">
      <table className={`li-table${showQuantity ? " has-quantity" : ""}`}>
        <thead>
          <tr>
            <th className="li-col-date">Date</th>
            <th className="li-col-name">Name</th>
            <th className="li-col-merchant">Merchant</th>
            <th className="li-col-tags">Tags</th>
            <th className="li-col-amount">Total</th>
            {showQuantity && <th className="li-col-quantity">Qty</th>}
            <th className="li-col-direction">Debit / Credit</th>
            {editableCore && <th className="li-col-remove" />}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className={`is-${row.direction === "credit" ? "credit" : "debit"}`}>
              <td className="li-col-date">
                {/* the browser's date picker: it can only give a real date, as YYYY-MM-DD */}
                <input
                  type="date"
                  value={row.date}
                  aria-label="Date"
                  className={requireDate && !row.date ? "is-missing" : undefined}
                  onChange={(e) => update(row.key, { date: e.target.value })}
                />
              </td>
              <td className="li-col-name">
                {editableCore ? (
                  <input
                    type="text"
                    value={row.name}
                    placeholder="Item name"
                    aria-label="Name"
                    onChange={(e) => update(row.key, { name: e.target.value })}
                  />
                ) : (
                  <span title={row.name}>{row.name}</span>
                )}
              </td>
              <td className="li-col-merchant">
                <input
                  type="text"
                  value={row.merchant}
                  placeholder="Merchant"
                  aria-label="Merchant"
                  maxLength={255}
                  onChange={(e) => update(row.key, { merchant: e.target.value })}
                />
              </td>
              <td className="li-col-tags">
                <TagPicker
                  available={availableTags}
                  selected={row.tags}
                  onChange={(_ids, tags) => update(row.key, { tags })}
                  onCreateTag={onCreateTag}
                />
              </td>
              <td className="li-col-amount">
                {editableCore ? (
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={row.amount}
                    placeholder="0.00"
                    aria-label="Total"
                    className={`li-amount is-${row.direction}`}
                    onChange={(e) => update(row.key, { amount: absAmount(e.target.value) })}
                  />
                ) : (
                  <span className={`li-amount is-${row.direction}`}>{absAmount(row.amount)}</span>
                )}
              </td>
              {showQuantity && (
                <td className="li-col-quantity">
                  <input
                    type="number"
                    min="0.001"
                    step="any"
                    value={row.quantity}
                    placeholder="1"
                    aria-label="Quantity"
                    onChange={(e) => update(row.key, quantityPatch(row, e.target.value))}
                  />
                </td>
              )}
              <td className="li-col-direction">
                <select
                  value={row.direction}
                  aria-label="Debit or credit"
                  onChange={(e) => update(row.key, { direction: e.target.value })}
                >
                  {DIRECTIONS.map((direction) => (
                    <option key={direction.value} value={direction.value}>
                      {direction.label}
                    </option>
                  ))}
                </select>
              </td>
              {editableCore && (
                <td className="li-col-remove">
                  <button type="button" className="manual-entry-remove-item" onClick={() => remove(row.key)} aria-label="Remove line item">
                    &times;
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default LineItemsTable;