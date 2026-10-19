import React from "react";
import LineItemEditModal from "./LineItemEditModal";

/* The edit dialog for a saved line item (as GET /line-items/ lists them).
   `onSave(line, changes)` is useLineItemActions' saveDetails. */
const LineEditor = ({ line, onSave, onClose }) => (
  <LineItemEditModal
    line={{
      name: line.description,
      alias: line.display_name,
      merchant: line.merchant,
      date: line.date,
      direction: line.direction,
      quantity: line.quantity,
    }}
    requireDate={line.kind === "statement_line"}
    showQuantity={line.kind === "receipt_item"}
    onSave={(changes) => onSave(line, changes)}
    onClose={onClose}
  />
);

export default LineEditor;
