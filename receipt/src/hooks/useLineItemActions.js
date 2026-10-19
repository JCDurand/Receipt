import { useCallback } from "react";
import { documentService } from "../utils/api";
import { lineKey } from "./useLineSelection";

const isStatementLine = (line) => line.kind === "statement_line";

/**
 * What can be done to saved line items (as GET /line-items/ lists them), each
 * saving to the server and then showing the result through `setLines`. A
 * failure is thrown to the caller (the picker, the name, the dialog), which
 * reports it. `reload` loads the line items again, for changes which move
 * other line items too (a removal changes what receipts were matched to, a
 * receipt's total, and documents left empty).
 */
export const useLineItemActions = (setLines, reload) => {
  const replace = useCallback(
    (line, changes) => setLines((prev) => prev.map((l) => (lineKey(l) === lineKey(line) ? { ...l, ...changes } : l))),
    [setLines]
  );

  const saveTags = useCallback(
    async (line, tagIds) => {
      const save = isStatementLine(line) ? documentService.setTransactionTags : documentService.setItemTags;
      const saved = await save(line.id, tagIds);
      replace(line, { tags: saved.tags });
    },
    [replace]
  );

  const saveName = useCallback(
    async (line, name) => {
      const save = isStatementLine(line) ? documentService.setTransactionName : documentService.setItemName;
      const saved = await save(line.id, name);
      replace(line, { display_name: saved.display_name });
    },
    [replace]
  );

  const saveDetails = useCallback(
    async (line, changes) => {
      const save = isStatementLine(line) ? documentService.updateTransaction : documentService.updateItem;
      const saved = await save(line.id, changes);
      replace(line, saved);
    },
    [replace]
  );

  /* Marks a line item as a subscription (or takes the mark off) and shows it as saved */
  const saveSubscription = useCallback(
    async (line, on) => {
      const save = isStatementLine(line) ? documentService.setTransactionSubscription : documentService.setItemSubscription;
      const saved = await save(line.id, on);
      replace(line, saved);
    },
    [replace]
  );

  const remove = useCallback(
    async (line) => {
      const removeOne = isStatementLine(line) ? documentService.removeTransaction : documentService.removeItem;
      await removeOne(line.id);
      setLines((prev) => prev.filter((l) => lineKey(l) !== lineKey(line)));
      reload();
    },
    [setLines, reload]
  );

  const removeMany = useCallback(
    async (lines) => {
      const result = await documentService.removeLineItems(lines);
      reload();
      return result;
    },
    [reload]
  );

  return { saveTags, saveName, saveDetails, saveSubscription, remove, removeMany };
};
