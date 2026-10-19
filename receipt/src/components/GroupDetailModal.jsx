import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import ConversionBadge from "./ConversionBadge";
import { formatDay, formatMoney } from "../utils/format";
import { bankLabel, bankOf } from "../utils/grouping";

const SORTS = [
  { key: "newest", label: "Newest first", compare: (a, b) => b.line.date.localeCompare(a.line.date) },
  { key: "oldest", label: "Oldest first", compare: (a, b) => a.line.date.localeCompare(b.line.date) },
  { key: "largest", label: "Largest first", compare: (a, b) => b.cents - a.cents },
  { key: "smallest", label: "Smallest first", compare: (a, b) => a.cents - b.cents },
];

/* whether a line item brought money in (a statement credit, or a receipt item paid back) */
const lineIsIn = (line) => (line.kind === "statement_line" ? Number(line.amount) > 0 : line.direction === "in");

const lineName = (line) => line.display_name || line.description || line.merchant || "-";

/**
 * The summary of one group on a chart: the line items in it, which can be
 * narrowed by further tags and sorted. `group` is one of groupLines's.
 */
const GroupDetailModal = ({ group, flow, onClose }) => {
  const [sort, setSort] = useState("newest");
  const [chosen, setChosen] = useState([]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  /* every tag on the group's line items, with how much is under each */
  const tagTotals = useMemo(() => {
    const totals = new Map();
    for (const { line, cents } of group.entries) {
      for (const tag of line.tags || []) {
        const t = totals.get(tag.id) || { id: tag.id, name: tag.name, cents: 0, count: 0 };
        t.cents += cents;
        t.count += 1;
        totals.set(tag.id, t);
      }
    }
    return [...totals.values()].sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name));
  }, [group]);

  const shown = useMemo(() => {
    const compare = SORTS.find((s) => s.key === sort).compare;
    return group.entries
      .filter(({ line }) => chosen.every((id) => (line.tags || []).some((t) => t.id === id)))
      .sort(compare);
  }, [group, chosen, sort]);

  const total = shown.reduce((sum, e) => sum + e.cents, 0);
  const toggle = (id) => setChosen((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));
  const noun = flow === "in" ? "received" : "spent";

  return (
    <div className="group-modal-overlay" onClick={onClose}>
      <div className="group-modal" role="dialog" aria-modal="true" aria-label={group.name} onClick={(e) => e.stopPropagation()}>
        <div className="group-modal-head">
          <div>
            <h3>{group.name}</h3>
            <p className="spending-hint">
              {formatMoney(total)} {noun} across {shown.length} of {group.entries.length} line{" "}
              {group.entries.length === 1 ? "item" : "items"}
              {shown.length > 0 && ` · ${formatMoney(Math.round(total / shown.length))} on average`}
            </p>
          </div>
          <button type="button" className="group-modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <div className="group-modal-controls">
          <div className="spending-group">
            <span className="spending-label">Narrow by tags</span>
            {tagTotals.length === 0 ? (
              <p className="spending-hint">None of these line items has a tag yet.</p>
            ) : (
              <div className="spending-presets" role="group" aria-label="Narrow by tags">
                {tagTotals.map((tag) => (
                  <button
                    key={tag.id}
                    type="button"
                    className={`spending-pill${chosen.includes(tag.id) ? " is-on" : ""}`}
                    aria-pressed={chosen.includes(tag.id)}
                    onClick={() => toggle(tag.id)}
                    title={`${formatMoney(tag.cents)} under ${tag.name}`}
                  >
                    {tag.name} · {tag.count}
                  </button>
                ))}
                {chosen.length > 0 && (
                  <button type="button" className="spending-pill" onClick={() => setChosen([])}>
                    Clear
                  </button>
                )}
              </div>
            )}
            {chosen.length > 1 && <p className="spending-hint">Only line items with all of the chosen tags are listed.</p>}
          </div>
          <label className="group-modal-sort">
            <span className="spending-label">Sort</span>
            <select className="analytics-select" value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="group-modal-body">
          {shown.length === 0 ? (
            <p className="dashboard-panel-empty">No line items have all of those tags.</p>
          ) : (
            <table className="recurring-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Line item</th>
                  <th>Tags</th>
                  <th>From</th>
                  <th className="num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {shown.map(({ line, cents }) => (
                  <tr key={`${line.id}-${cents}`} className={lineIsIn(line) ? "line-tint-credit" : "line-tint-debit"}>
                    <td>{formatDay(line.date)}</td>
                    <td>
                      {lineName(line)}
                      {line.merchant && line.merchant !== lineName(line) && <span className="spending-hint"> · {line.merchant}</span>}
                    </td>
                    <td>{(line.tags || []).map((t) => t.name).join(", ") || <span className="spending-hint">Untagged</span>}</td>
                    <td>
                      {line.source ? (
                        <Link to={`/uploads/${line.source.category}/${line.source.id}`}>{line.source.name}</Link>
                      ) : (
                        "-"
                      )}
                      {line.kind === "statement_line" && <span className="spending-hint"> · {bankLabel(bankOf(line))}</span>}
                    </td>
                    <td className={`num line-amount ${lineIsIn(line) ? "is-credit" : "is-debit"}`}>
                      {formatMoney(cents)} <ConversionBadge line={line} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

export default GroupDetailModal;
