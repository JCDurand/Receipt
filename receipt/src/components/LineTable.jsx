import React from "react";
import { Link } from "react-router-dom";
import ConversionBadge from "./ConversionBadge";
import DirectionBadge from "./DirectionBadge";
import LineItemName from "./LineItemName";
import TagPicker from "./TagPicker";
import { lineKey } from "../hooks/useLineSelection";
import { accountLabel, directionKey, formatDateTime, formatDay, formatMoney, shownName } from "../utils/format";
import { absAmount } from "../utils/lineItems";
import { KIND_LABELS } from "../utils/lineItemSort";
import "../styles/LineTable.css";

/* What is inside a row which does its own thing when clicked, rather than open the line */
const INTERACTIVE = "button, a, input, select, textarea, label, [role='button'], [contenteditable='true']";

const GROUP_LABELS = { statement: "Statement", receipt: "Receipt", cash: "Cash entry" };

/* One line item's cell for a column */
const Cell = ({ column, line, tags, onRename }) => {
  const direction = directionKey(line.direction);
  switch (column.key) {
    case "date":
      return <td className="nowrap">{formatDay(line.date)}</td>;
    case "description":
      return (
        <td className="line-table-name">
          <LineItemName name={line.description} alias={line.display_name} onRename={onRename && ((name) => onRename(line, name))} />
          {line.merchant && line.merchant !== line.description && <span className="line-table-sub">{line.merchant}</span>}
        </td>
      );
    case "tags":
      return (
        <td className="line-table-tags">
          {tags ? (
            <TagPicker
              available={tags.available}
              selected={line.tags || []}
              onChange={(tagIds) => tags.onChange(line, tagIds)}
              onCreateTag={tags.onCreate}
            />
          ) : (
            (line.tags || []).map((t) => t.name).join(", ") || "-"
          )}
        </td>
      );
    case "source":
      return (
        <td className="line-table-text">
          {line.source ? (
            <Link to={`/uploads/${line.source.category}/${line.source.id}`} title={line.source.name}>
              {line.source.name}
            </Link>
          ) : (
            "-"
          )}
        </td>
      );
    case "kind":
      return (
        <td className="nowrap">
          <span className={`transactions-badge kind-${line.kind}`}>{KIND_LABELS[line.kind]}</span>
          {line.is_cash && <span className="line-table-cash">Cash</span>}
        </td>
      );
    case "account":
      return <td className="nowrap">{accountLabel(line.account) || "-"}</td>;
    case "amount":
      return (
        <td className={`is-numeric nowrap line-amount is-${direction}`}>
          {absAmount(line.amount)} <ConversionBadge line={line} />
        </td>
      );
    case "quantity":
      return <td className="is-numeric">{line.quantity == null ? "-" : Number(line.quantity)}</td>;
    case "unit_price":
      return (
        <td className={`is-numeric nowrap${line.unit_price != null ? ` line-amount is-${direction}` : ""}`}>
          {line.unit_price != null ? absAmount(line.unit_price) : "-"}
        </td>
      );
    case "status":
      return <td className="nowrap">{line.status || "-"}</td>;
    case "matched":
      return <td>{line.matched ? "Yes" : "No"}</td>;
    case "added_at":
      return <td className="nowrap">{line.added_at ? formatDateTime(line.added_at) : "-"}</td>;
    case "direction":
      return (
        <td className="nowrap">
          <DirectionBadge direction={line.direction} />
        </td>
      );
    default:
      return <td />;
  }
};

/* A statement's or receipt's row: it opens and closes the line items under it */
const GroupRow = ({ entry, colSpan, onToggle }) => {
  const { group } = entry;
  return (
    <tr className={`line-table-group depth-${entry.depth}${entry.isOpen ? " is-open" : ""}`} onClick={() => onToggle(group.key)}>
      <td className="line-select-cell" />
      <td colSpan={colSpan}>
        <div className="line-group" style={{ paddingLeft: `${entry.depth * 22}px` }}>
          <button
            type="button"
            className="line-group-toggle"
            aria-expanded={entry.isOpen}
            aria-label={`${entry.isOpen ? "Hide" : "Show"} the line items of ${group.name}`}
            onClick={(evt) => {
              evt.stopPropagation();
              onToggle(group.key);
            }}
          >
            <span aria-hidden="true">{entry.isOpen ? "▾" : "▸"}</span>
          </button>
          <span className={`line-group-kind is-${group.kind}`}>{GROUP_LABELS[group.kind]}</span>
          <Link
            to={`/uploads/${group.kind === "statement" ? "statement" : group.kind}/${group.id}`}
            className="line-group-name"
            onClick={(evt) => evt.stopPropagation()}
          >
            {group.name}
          </Link>
          <span className="line-group-meta">
            {group.firstDate && (group.firstDate === group.lastDate ? formatDay(group.firstDate) : `${formatDay(group.firstDate)} to ${formatDay(group.lastDate)}`)}
            {group.account && ` · ${accountLabel(group.account)}`}
            {" · "}
            {group.shown === group.total ? `${group.total} line ${group.total === 1 ? "item" : "items"}` : `${group.shown} of ${group.total} line items match`}
            {group.receipts > 0 && ` · ${group.receipts} ${group.receipts === 1 ? "receipt" : "receipts"}`}
          </span>
          <span className="line-group-money">
            {group.inCents > 0 && <span className="is-credit">+{formatMoney(group.inCents)}</span>}
            {group.outCents > 0 && <span className="is-debit">−{formatMoney(group.outCents)}</span>}
          </span>
        </div>
      </td>
      <td />
    </tr>
  );
};

/**
 * A table of line items, in the columns given (in COLUMNS' order), with each
 * row tinted by which way its money went: red for money out, green for money in.
 *
 * `entries` are what to show, in order: { type: "line", line, depth } and, for
 * line items grouped under their statement or receipt, { type: "group", group,
 * depth, isOpen } (see utils/lineGroups). Groups only open and close; it is the
 * line items which are edited, picked and removed.
 *
 * `onToggleSubscription(line)`, when given, adds a button which marks a line item
 * as a subscription or takes the mark off (the line's `is_subscription` says which).
 *
 * Clicking a line item opens it (`onOpen`). The box beside it (which appears
 * when the pointer is over the row) picks it to be removed with others, and so
 * does shift-clicking it; `selection` is useLineSelection's. `sort` and
 * `onSort` make the headings sort the table, when given.
 */
const LineTable = ({ columns, entries, selection, onOpen, onRemove, onRename, onToggleSubscription, tags, sort, onSort, onToggleGroup, label = "Line items" }) => {
  const handleRowClick = (evt, line) => {
    if (evt.shiftKey) {
      selection?.toggle(line);
      return;
    }
    if (evt.target.closest(INTERACTIVE)) return;
    onOpen?.(line);
  };

  return (
    <table className="line-table transactions-table" aria-label={label}>
      <thead>
        <tr>
          <th className="line-select-cell" aria-label="Select" />
          {columns.map((column) => {
            const isSorted = sort?.key === column.key;
            return (
              <th
                key={column.key}
                className={column.numeric ? "is-numeric" : undefined}
                aria-sort={isSorted ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
              >
                {onSort ? (
                  <button type="button" className="transactions-sort" onClick={() => onSort(column.key)}>
                    {column.label}
                    <span className="transactions-sort-arrow" aria-hidden="true">
                      {isSorted ? (sort.direction === "asc" ? "▲" : "▼") : ""}
                    </span>
                  </button>
                ) : (
                  <span className="transactions-sort">{column.label}</span>
                )}
              </th>
            );
          })}
          <th aria-label="Actions" />
        </tr>
      </thead>
      <tbody>
        {entries.map((entry) => {
          if (entry.type === "group") {
            return <GroupRow key={`group-${entry.group.key}`} entry={entry} colSpan={columns.length} onToggle={onToggleGroup} />;
          }
          const { line } = entry;
          const isPicked = selection?.has(line);
          const name = shownName(line.description, line.display_name) || "line item";
          return (
            <tr
              key={lineKey(line)}
              className={`line-row is-${directionKey(line.direction)}${isPicked ? " is-selected" : ""}${entry.depth ? ` depth-${entry.depth}` : ""}`}
              onClick={(evt) => handleRowClick(evt, line)}
              /* a shift-click picks the line; it should not select the text as well */
              onMouseDown={(evt) => evt.shiftKey && evt.preventDefault()}
              title="Click to edit · shift-click to select"
            >
              <td className="line-select-cell" style={entry.depth ? { paddingLeft: `${entry.depth * 22 + 8}px` } : undefined}>
                {selection && (
                  <input
                    type="checkbox"
                    className="line-select"
                    checked={!!isPicked}
                    onChange={() => selection.toggle(line)}
                    onClick={(evt) => evt.stopPropagation()}
                    aria-label={`Select ${name}`}
                  />
                )}
              </td>
              {columns.map((column) => (
                <Cell key={column.key} column={column} line={line} tags={tags} onRename={onRename} />
              ))}
              <td className="nowrap">
                <div className="transactions-actions">
                  <button type="button" className="transactions-edit" onClick={() => onOpen?.(line)}>
                    Edit
                  </button>
                  {onToggleSubscription && (
                    <button
                      type="button"
                      className={`transactions-edit is-subscription${line.is_subscription ? " is-on" : ""}`}
                      aria-pressed={!!line.is_subscription}
                      title={line.is_subscription ? "Marked as a subscription: click to unmark" : "Mark as a subscription"}
                      onClick={() => onToggleSubscription(line)}
                    >
                      {line.is_subscription ? "★ Subscription" : "☆ Subscription"}
                    </button>
                  )}
                  {onRemove && (
                    <button type="button" className="transactions-edit is-danger" aria-label={`Remove ${name}`} onClick={() => onRemove(line)}>
                      Remove
                    </button>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};

export default LineTable;
