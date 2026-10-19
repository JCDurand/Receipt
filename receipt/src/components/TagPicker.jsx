import { useEffect, useRef, useState } from "react";
import { getErrorMessage } from "../utils/errors";
import "../styles/TagPicker.css";

/**
 * The tags on one line item, as removable chips, and a box to add more: type
 * to find one of the available tags, or to create a new tag of the user's own.
 *
 * `available` is every tag which can be applied and `selected` the line item's
 * own, both as { id, name }. `onChange(tagIds, tags)` saves the line item's new
 * full set of tags (as ids, and as the tags themselves, for a line item which
 * is not saved yet) and `onCreateTag(name)` resolves with the tag it created; a
 * rejection from either is shown beneath the chips.
 */
const TagPicker = ({ available, selected, onChange, onCreateTag }) => {
  const pickerRef = useRef(null);
  const [isAdding, setIsAdding] = useState(false);
  const [query, setQuery] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);

  const selectedIds = selected.map((tag) => tag.id);
  const term = query.trim().toLowerCase();

  const choices = available.filter(
    (tag) => !selectedIds.includes(tag.id) && tag.name.toLowerCase().includes(term)
  );
  /* Offered only for a name which is not already a tag, or the two would clash */
  const canCreate = term !== "" && !available.some((tag) => tag.name.toLowerCase() === term);

  const close = () => {
    setIsAdding(false);
    setQuery("");
    setError(null);
  };

  useEffect(() => {
    if (!isAdding) return undefined;

    const handleOutsidePointerDown = (event) => {
      if (!pickerRef.current?.contains(event.target)) close();
    };

    document.addEventListener("pointerdown", handleOutsidePointerDown);
    return () => document.removeEventListener("pointerdown", handleOutsidePointerDown);
  }, [isAdding]);

  /* Runs a save, keeping the picker locked while it does and showing why it failed */
  const run = async (action) => {
    setIsSaving(true);
    setError(null);
    try {
      await action();
      return true;
    } catch (err) {
      console.error("Failed to save tags", err);
      setError(getErrorMessage(err, "The tag change couldn't be saved. Please try again."));
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  const addTag = async (tag) => {
    if (await run(() => onChange([...selectedIds, tag.id], [...selected, tag]))) close();
  };

  const createAndAdd = async () => {
    const name = query.trim();
    const done = await run(async () => {
      const tag = await onCreateTag(name);
      await onChange([...selectedIds, tag.id], [...selected, tag]);
    });
    if (done) close();
  };

  const removeTag = (tag) =>
    run(() =>
      onChange(
        selectedIds.filter((id) => id !== tag.id),
        selected.filter((t) => t.id !== tag.id)
      )
    );

  const handleKeyDown = (evt) => {
    if (evt.key === "Escape") {
      close();
    } else if (evt.key === "Enter") {
      evt.preventDefault();
      if (isSaving) return;
      if (choices.length > 0) addTag(choices[0]);
      else if (canCreate) createAndAdd();
    }
  };

  return (
    <div className="tag-picker" ref={pickerRef}>
      <div className="tag-picker-chips">
        {selected.map((tag) => (
          <span className="tag-chip" key={tag.id}>
            {tag.name}
            <button
              type="button"
              className="tag-chip-remove"
              aria-label={`Remove tag ${tag.name}`}
              disabled={isSaving}
              onClick={() => removeTag(tag)}
            >
              &times;
            </button>
          </span>
        ))}
        {!isAdding && (
          <button type="button" className="tag-add-btn" disabled={isSaving} onClick={() => { setError(null); setIsAdding(true); }}>
            + Tag
          </button>
        )}
      </div>

      {isAdding && (
        <div className="tag-picker-add">
          <input
            type="text"
            className="tag-picker-input"
            placeholder="Find or create a tag..."
            maxLength={100}
            autoFocus
            value={query}
            disabled={isSaving}
            onChange={(evt) => setQuery(evt.target.value)}
            onKeyDown={handleKeyDown}
            aria-label="Find or create a tag"
          />
          <ul className="tag-picker-choices">
            {choices.map((tag) => (
              <li key={tag.id}>
                <button type="button" disabled={isSaving} onClick={() => addTag(tag)}>
                  {tag.name}
                  {!tag.is_predefined && <span className="tag-own-label">yours</span>}
                </button>
              </li>
            ))}
            {canCreate && (
              <li>
                <button type="button" className="tag-create-choice" disabled={isSaving} onClick={createAndAdd}>
                  Create &ldquo;{query.trim()}&rdquo;
                </button>
              </li>
            )}
            {choices.length === 0 && !canCreate && <li className="tag-picker-none">No more tags to add.</li>}
          </ul>
          <button type="button" className="tag-picker-cancel" onClick={close}>
            Cancel
          </button>
        </div>
      )}

      {error && (
        <p className="tag-picker-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
};

export default TagPicker;
