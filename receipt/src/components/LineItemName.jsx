import { useRef, useState } from "react";
import "../styles/LineItemName.css";

/**
 * A line item's name as the user sees it, and (when `onRename` is given) as they
 * change it. What they type is only an alias: `name` is what the line is really
 * called, as it was read from its file, and is never changed, so that the same
 * file is still recognised when it is uploaded again. While there is an `alias`
 * the real name is shown beneath it, in italics.
 *
 * `onRename(text)` saves the alias and resolves, or throws to have its message
 * shown. A blank name, or the real name, takes the alias away. Enter or leaving
 * the box saves, Escape drops the change. Without `onRename` the name is only
 * shown, as where it sits inside a button.
 */
const LineItemName = ({ name, alias, onRename, fallback = "-" }) => {
  /* null while the name is not being edited */
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState(null);
  const isSaving = useRef(false);
  /* set once Enter or Escape has settled the edit, so the box closing does not settle it again */
  const isSettled = useRef(false);

  const hasAlias = Boolean(alias) && alias !== name;
  const shown = hasAlias ? alias : name || "";

  const startEditing = () => {
    isSettled.current = false;
    setError(null);
    setDraft(shown);
  };

  const stopEditing = () => {
    setDraft(null);
    setError(null);
  };

  const save = async () => {
    if (isSaving.current) return;
    const next = draft.trim();
    if (next === shown) {
      stopEditing();
      return;
    }
    isSaving.current = true;
    isSettled.current = true;
    try {
      await onRename(next);
      stopEditing();
    } catch (err) {
      console.error("Failed to save the line item's name", err);
      isSettled.current = false;
      setError("The name could not be saved.");
    } finally {
      isSaving.current = false;
    }
  };

  const handleKeyDown = (evt) => {
    if (evt.key === "Enter") {
      evt.preventDefault();
      save();
    } else if (evt.key === "Escape") {
      evt.preventDefault();
      isSettled.current = true;
      stopEditing();
    }
  };

  if (draft !== null) {
    return (
      <span className="li-name is-editing">
        <input
          type="text"
          className="li-name-input"
          value={draft}
          maxLength={255}
          autoFocus
          aria-label="Name"
          placeholder={name || "Name"}
          onChange={(evt) => setDraft(evt.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            if (!isSettled.current) save();
          }}
        />
        {hasAlias && <em className="li-name-original">{name}</em>}
        {error && (
          <span className="li-name-error" role="alert">
            {error}
          </span>
        )}
      </span>
    );
  }

  return (
    <span className="li-name">
      <span className="li-name-row">
        <span className="li-name-text" title={shown || undefined}>
          {shown || fallback}
        </span>
        {onRename && (
          <button
            type="button"
            className="li-name-edit"
            aria-label={`Rename ${shown || "line item"}`}
            title="Rename"
            onClick={startEditing}
          >
            &#9998;
          </button>
        )}
      </span>
      {hasAlias && (
        <em className="li-name-original" title="The name it was read with">
          {name}
        </em>
      )}
    </span>
  );
};

export default LineItemName;
