/**
 * @file Transactions.jsx
 *
 * @description This page displays a list of all line items (transactions and receipt items) from the user's bank statements and receipts.
 * Users can sort, filter, search, edit, and remove line items. The page also provides a toolbar for filtering by tags and types.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Navbar from "../components/Navbar";
import LineTable from "../components/LineTable";
import LineEditor from "../components/LineEditor";
import { LineBulkDelete, LineRemoveDialog } from "../components/LineDeletion";
import { useTags } from "../hooks/useTags";
import { useLineSelection } from "../hooks/useLineSelection";
import { useLineItemActions } from "../hooks/useLineItemActions";
import { documentService } from "../utils/api";
import { getErrorMessage } from "../utils/errors";
import { COLUMNS, KIND_LABELS, compareBy } from "../utils/lineItemSort";
import { documentGroups, groupEntries } from "../utils/lineGroups";
import "../styles/Transactions.css";
import { usePageTitle } from "../components/PageTitle";

const PAGE_SIZE = 100;
const UNTAGGED = "__untagged__";
/* the type filter's choice for the line items marked as subscriptions */
const SUBSCRIPTIONS = "__subscriptions__";

const Transactions = () => {
  usePageTitle("Transactions");
  // Core data states for line items, loading status, and error handling
  const [lines, setLines] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newTagName, setNewTagName] = useState("");
  const [isCreatingTag, setIsCreatingTag] = useState(false);
  const [tagError, setTagError] = useState(null);
  /* why marking a line item as a subscription (or unmarking it) failed, if it did */
  const [subscriptionError, setSubscriptionError] = useState(null);

  // States for sorting, filtering, searching, and pagination
  const [sort, setSort] = useState({ key: "date", direction: "desc" });
  const [tagFilter, setTagFilter] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // The line item being edited, or asked about before it is removed
  const [editingLine, setEditingLine] = useState(null);
  const [removingLine, setRemovingLine] = useState(null);
  /* Statements and receipts whose line items have been shown (or, while
     filtering, hidden) by clicking them */
  const [toggled, setToggled] = useState(() => new Set());

  const { tags: availableTags, createTag } = useTags();
  const [localTags, setLocalTags] = useState([]);

  useEffect(() => {
    setLocalTags(availableTags);
  }, [availableTags]);

  const loadLines = useCallback(() => {
    return documentService
      .getLineItems()
      .then((data) => setLines(data || []))
      .catch((err) => {
        console.error("Failed to load line items", err);
        setError("Failed to load your line items. Please try again later.");
      });
  }, []);

  // Fetch line items on component mount
  useEffect(() => {
    loadLines().finally(() => setIsLoading(false));
  }, [loadLines]);

  const actions = useLineItemActions(setLines, loadLines);
  const selection = useLineSelection(lines);

  /* Creates a tag of the user's own from the toolbar. useTags adds it to the
     tags every picker and filter offers, so nothing else needs updating. */
  const handleCreateTag = async (e) => {
    e.preventDefault();
    const name = newTagName.trim();
    if (!name) return;

    setIsCreatingTag(true);
    setTagError(null);
    try {
      await createTag(name);
      setNewTagName("");
    } catch (err) {
      console.error("Failed to create tag", err);
      setTagError(getErrorMessage(err, "That tag couldn't be created. It may already exist."));
    } finally {
      setIsCreatingTag(false);
    }
  };

  /* Marks a line item as a subscription, or takes the mark off; a failure is shown above the table */
  const handleSubscription = async (line) => {
    setSubscriptionError(null);
    try {
      await actions.saveSubscription(line, !line.is_subscription);
    } catch (err) {
      console.error("Failed to change the subscription mark", err);
      setSubscriptionError(err.serverMessage || "The line item could not be marked. Please try again.");
    }
  };

  /**
   * Memoized computation of visible line items based on current filters, search term, and sorting.
   *
   * @returns {Array} Filtered and sorted line items to be displayed.
   */
  const visibleLines = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    const column = COLUMNS.find((c) => c.key === sort.key);
    const byColumn = compareBy(column, sort.direction);
    const byNewest = compareBy(COLUMNS[0], "desc");

    // Determine allowed tags based on the current tag filter, including child tags if applicable
    let allowedTags = [tagFilter];
    if (tagFilter && tagFilter !== UNTAGGED) {
      const childTags = localTags.filter(t => t.parent === tagFilter).map(t => t.id);
      allowedTags = [tagFilter, ...childTags];
    }

    return lines
      .filter((line) => {
        // Filter line items based on kind and tag filters
        if (kindFilter === SUBSCRIPTIONS && !line.is_subscription) return false;
        if (kindFilter && kindFilter !== SUBSCRIPTIONS && line.kind !== kindFilter) return false;

        // Handle tag filtering logic, including untagged and specific tag filters
        if (tagFilter === UNTAGGED && line.tags.length > 0) return false;
        if (tagFilter && tagFilter !== UNTAGGED && !line.tags.some((tag) => allowedTags.includes(tag.id))) return false;

        // Filter line items based on the search term across multiple fields
        return (
          !term ||
          [line.display_name, line.description, line.merchant, line.source?.name].some((text) =>
            text?.toLowerCase().includes(term)
          )
        );
      })
      .sort((a, b) => byColumn(a, b) || byNewest(a, b));
  }, [lines, sort, tagFilter, kindFilter, searchTerm, localTags]);

  /* While filtering, the documents with line items that match are open, so the
     matches show; otherwise they are closed until clicked */
  const isFiltering = Boolean(searchTerm.trim() || tagFilter || kindFilter);
  useEffect(() => setToggled(new Set()), [isFiltering]);
  const isOpen = useCallback((key) => (isFiltering ? !toggled.has(key) : toggled.has(key)), [isFiltering, toggled]);
  const toggleGroup = (key) =>
    setToggled((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const structure = useMemo(() => documentGroups(lines), [lines]);
  const { entries, topLevel } = useMemo(
    () => groupEntries(visibleLines, structure, isOpen, visibleCount),
    [visibleLines, structure, isOpen, visibleCount]
  );
  const allKeys = useMemo(() => [...structure.groups.keys()], [structure]);
  const setAll = (open) => setToggled(open === isFiltering ? new Set() : new Set(allKeys));

  const resetPaging = () => setVisibleCount(PAGE_SIZE);

  /**
   * Sorts the line items by the specified column key.
   *
   * @param {string} key - The key of the column to sort by.
   */
  const sortBy = (key) => {
    setSort((prev) => ({ key, direction: prev.key === key && prev.direction === "asc" ? "desc" : "asc" }));
    resetPaging();
  };

  return (
    <>
      <Navbar />
      <div className="container transactions-page">
        <div className="transactions-section" style={{ minWidth: 0, width: "100%" }}>
          <div className="transactions-header">
            <p>
              Every line item from your bank statements and receipts, under the document it came from:
              a statement holds its lines and any receipt matched to them, and a receipt its items. Click
              a statement or receipt to open it, and a line item to edit it. Rename a line item with the
              pencil beside its name, and sort by any column heading.
            </p>
          </div>

          {isLoading ? (
            <p>Loading your line items...</p>
          ) : error ? (
            <p style={{ color: "red" }}>{error}</p>
          ) : lines.length === 0 ? (
            <div className="transactions-empty">
              <p>You have no line items yet.</p>
              <p>
                Upload a bank statement or a receipt on the <Link to="/uploads">Source Documents</Link>{" "}
                page and its line items will be listed here.
              </p>
            </div>
          ) : (
            <>
            {/* Toolbar and filters */}
              <div className="transactions-toolbar">
                <input
                  type="text"
                  className="transactions-search"
                  placeholder="Search name, merchant or document..."
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value);
                    resetPaging();
                  }}
                  aria-label="Search line items"
                />
                <select
                  value={tagFilter}
                  onChange={(e) => {
                    setTagFilter(e.target.value);
                    resetPaging();
                  }}
                  aria-label="Filter by tag"
                >
                  <option value="">All tags</option>
                  <option value={UNTAGGED}>Untagged</option>
                  {localTags.map((tag) => (
                    <option key={tag.id} value={tag.id}>
                      {tag.name}
                    </option>
                  ))}
                </select>
                <select
                  value={kindFilter}
                  onChange={(e) => {
                    setKindFilter(e.target.value);
                    resetPaging();
                  }}
                  aria-label="Filter by type"
                >
                  <option value="">All types</option>
                  <option value={SUBSCRIPTIONS}>Subscriptions</option>
                  {Object.entries(KIND_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}s
                    </option>
                  ))}
                </select>
                <Link to="/tags" className="transactions-manage-tags-link" title="Rename, nest and delete tags">
                  Manage tags
                </Link>
                <form onSubmit={handleCreateTag} className="transactions-new-tag">
                  <input
                    type="text"
                    placeholder="New tag name..."
                    value={newTagName}
                    onChange={(e) => {
                      setNewTagName(e.target.value);
                      setTagError(null);
                    }}
                    disabled={isCreatingTag}
                    aria-label="New tag name"
                  />
                  <button 
                    type="submit" 
                    disabled={isCreatingTag || !newTagName.trim()}
                    className="transactions-new-tag-btn"
                  >
                    {isCreatingTag ? "Adding..." : "+ Add Tag"}
                  </button>
                </form>
                {tagError && (
                  <span className="transactions-tag-error" role="alert">
                    {tagError}
                  </span>
                )}
                <span className="transactions-count">
                  {visibleLines.length} of {lines.length} line {lines.length === 1 ? "item" : "items"}
                </span>
              </div>

              {subscriptionError && <p className="transactions-error" role="alert">{subscriptionError}</p>}

              {visibleLines.length === 0 ? (
                <p className="transactions-none">No line items match these filters.</p>
              ) : (
                <>
                  <div className="transactions-group-controls">
                    <button type="button" className="transactions-edit" onClick={() => setAll(true)}>
                      Open all
                    </button>
                    <button type="button" className="transactions-edit" onClick={() => setAll(false)}>
                      Close all
                    </button>
                  </div>
                  <div className="transactions-scroll scroll-area" style={{ overflowX: "auto", width: "100%" }}>
                    <LineTable
                      columns={COLUMNS}
                      entries={entries}
                      selection={selection}
                      onOpen={setEditingLine}
                      onRemove={setRemovingLine}
                      onRename={actions.saveName}
                      onToggleSubscription={handleSubscription}
                      tags={{ available: localTags, onChange: actions.saveTags, onCreate: createTag }}
                      sort={sort}
                      onSort={sortBy}
                      onToggleGroup={toggleGroup}
                      label="Transactions"
                    />
                  </div>
                </>
              )}

              <LineBulkDelete selection={selection} removeMany={actions.removeMany} />

              {topLevel > visibleCount && (
                <button
                  type="button"
                  className="transactions-more"
                  onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
                >
                  Show more ({topLevel - visibleCount} remaining)
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {removingLine && <LineRemoveDialog line={removingLine} onRemove={actions.remove} onClose={() => setRemovingLine(null)} />}
      {editingLine && <LineEditor line={editingLine} onSave={actions.saveDetails} onClose={() => setEditingLine(null)} />}
    </>
  );
};

export default Transactions;