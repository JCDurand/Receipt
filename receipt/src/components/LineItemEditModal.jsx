import { useEffect, useId, useState } from "react";
import { DIRECTIONS } from "../utils/lineItems";
import { directionKey } from "../utils/format";
import "../styles/Review.css"; /* the dialogs' look */
import "../styles/LineItemEditModal.css";

/* The reasons a save was refused: the server's field errors, as sentences */
const describeError = (err) => {
  try {
    const reasons = JSON.parse(err.serverMessage);
    if (reasons && typeof reasons === "object") {
      return Object.values(reasons).flat().join(" ");
    }
  } catch {
    /* not the server's field errors */
  }
  return err.serverMessage || err.message || "The changes could not be saved.";
};

/**
 * Changes a saved line item's name, merchant, date, debit/credit and (for a
 * receipt item) quantity. These can be set when a line item is entered, and this
 * is how they are changed after.
 *
 * `line` is { name, alias, merchant, date, direction, quantity }: `name` is what
 * the line was read with, `alias` the name the user gave it (if any), `date`
 * YYYY-MM-DD or empty, `direction` "debit"/"credit" (or "in"/"out", as the server
 * lists them) and `quantity` how many of the item the line is for. Only what was
 * changed is sent: `onSave(changes)` gets some of { display_name, merchant, date,
 * direction, quantity }, saves them and resolves, or throws to have its reason
 * shown. `requireDate` is for a line which cannot be without a date; a receipt
 * item without one has its receipt's. `showQuantity` is for a receipt item: a
 * bank statement line has no quantity.
 */
const LineItemEditModal = ({ line, requireDate = false, showQuantity = false, onSave, onClose }) => {
  const shownName = line.alias || line.name || "";
  const initial = {
    name: shownName,
    merchant: line.merchant || "",
    date: line.date || "",
    direction: directionKey(line.direction),
    quantity: line.quantity == null || line.quantity === "" ? "1" : String(Number(line.quantity)),
  };

  const [name, setName] = useState(initial.name);
  const [merchant, setMerchant] = useState(initial.merchant);
  const [date, setDate] = useState(initial.date);
  const [direction, setDirection] = useState(initial.direction);
  const [quantity, setQuantity] = useState(initial.quantity);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const id = useId();

  useEffect(() => {
    const handleKeyDown = (evt) => {
      if (evt.key === "Escape" && !isSaving) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, isSaving]);

  const changes = {};
  if (name.trim() !== initial.name) changes.display_name = name.trim();
  if (merchant.trim() !== initial.merchant) changes.merchant = merchant.trim();
  if (date !== initial.date) changes.date = date || null;
  if (direction !== initial.direction) changes.direction = direction;

  /* the quantity must be more than nothing; the price of one follows from it and the amount */
  const isBadQuantity = showQuantity && !(Number(quantity) > 0);
  if (showQuantity && !isBadQuantity && Number(quantity) !== Number(initial.quantity)) {
    changes.quantity = quantity.trim();
  }

  const isMissingDate = requireDate && !date;
  const canSave = Object.keys(changes).length > 0 && !isMissingDate && !isBadQuantity && !isSaving;

  const handleSubmit = async (evt) => {
    evt.preventDefault();
    if (!canSave) return;

    setIsSaving(true);
    setError(null);
    try {
      await onSave(changes);
      onClose();
    } catch (err) {
      console.error("Failed to save the line item's details", err);
      setError(describeError(err));
      setIsSaving(false);
    }
  };

  return (
    <div className="match-modal-overlay" onClick={() => !isSaving && onClose()}>
      <form
        className="match-modal link-account-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        onClick={(evt) => evt.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <div className="match-modal-header">
          <div>
            <h3 id={`${id}-title`}>Edit line item</h3>
            <p title={line.name}>{line.name || "-"}</p>
          </div>
          <button type="button" className="match-modal-close" onClick={onClose} disabled={isSaving} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="match-modal-body link-account-body li-edit-body">
          <label className="link-account-label" htmlFor={`${id}-name`}>
            Name
          </label>
          <input
            id={`${id}-name`}
            type="text"
            value={name}
            maxLength={255}
            placeholder={line.name || "Name"}
            disabled={isSaving}
            onChange={(e) => setName(e.target.value)}
          />
          <p className="link-account-hint">
            Only the name shown changes; the name it was read with is kept and shown in italics
            beneath it. Clear this to go back to that name.
          </p>

          <label className="link-account-label" htmlFor={`${id}-merchant`}>
            Merchant
          </label>
          <input
            id={`${id}-merchant`}
            type="text"
            value={merchant}
            maxLength={255}
            placeholder="Merchant"
            disabled={isSaving}
            onChange={(e) => setMerchant(e.target.value)}
          />

          <div className="li-edit-pair">
            <div className="li-edit-field">
              <label className="link-account-label" htmlFor={`${id}-date`}>
                Date
              </label>
              {/* the browser's date picker: it can only give a real date, as YYYY-MM-DD */}
              <input
                id={`${id}-date`}
                type="date"
                value={date}
                className={isMissingDate ? "is-missing" : undefined}
                disabled={isSaving}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>
            <div className="li-edit-field">
              <label className="link-account-label" htmlFor={`${id}-direction`}>
                Debit / Credit
              </label>
              <select
                id={`${id}-direction`}
                value={direction}
                disabled={isSaving}
                onChange={(e) => setDirection(e.target.value)}
              >
                {DIRECTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {showQuantity && (
            <>
              <div className="li-edit-pair">
                <div className="li-edit-field">
                  <label className="link-account-label" htmlFor={`${id}-quantity`}>
                    Quantity
                  </label>
                  <input
                    id={`${id}-quantity`}
                    type="number"
                    min="0.001"
                    step="any"
                    value={quantity}
                    className={isBadQuantity ? "is-missing" : undefined}
                    disabled={isSaving}
                    onChange={(e) => setQuantity(e.target.value)}
                  />
                </div>
                <div className="li-edit-field" />
              </div>
              {isBadQuantity ? (
                <p className="link-account-error">The quantity must be more than 0.</p>
              ) : (
                <p className="link-account-hint">
                  How many of the item this line is for: 5 red apples for 70.00 is a quantity of 5. The
                  amount stays as it is, and the price of one is worked out from it.
                </p>
              )}
            </>
          )}
          {isMissingDate && <p className="link-account-error">This line item needs a date.</p>}
          {!requireDate && (
            <p className="link-account-hint">Without a date of its own, a receipt item has its receipt's.</p>
          )}

          {error && <p className="link-account-error">{error}</p>}
        </div>

        <div className="link-account-footer">
          <button type="button" className="link-account-btn" onClick={onClose} disabled={isSaving}>
            Cancel
          </button>
          <button type="submit" className="match-btn" disabled={!canSave}>
            {isSaving ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
};

export default LineItemEditModal;
