import { useCallback, useEffect, useState } from "react";
import { documentService } from "../utils/api";

/* The line items of one document (a statement, receipt or cash entry), in the
   same shape as the Transactions page has them, oldest first, so that the same
   table, edits and removals work on them. */
export const useDocumentLines = (documentId) => {
  const [lines, setLines] = useState(null);
  const [error, setError] = useState(null);

  const reload = useCallback(
    () =>
      documentService
        .getLineItems()
        .then((all) => {
          const own = (all || []).filter((line) => String(line.source?.id) === String(documentId));
          setLines(own.sort((a, b) => a.date.localeCompare(b.date)));
          setError(null);
        })
        .catch((err) => {
          console.error("Failed to load the document's line items", err);
          setError("Failed to load this document's line items. Please try again later.");
        }),
    [documentId]
  );

  useEffect(() => {
    reload();
  }, [reload]);

  return { lines, setLines, reload, error };
};
