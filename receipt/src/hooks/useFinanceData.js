import { useCallback, useEffect, useState } from "react";
import { documentService } from "../utils/api";
import { useTags } from "./useTags";

/* What the dashboard pages are drawn from: every line item (already in the
   user's currency), the accounts, every uploaded document and the tags. */
export const useFinanceData = () => {
  const [data, setData] = useState({ lines: [], accounts: [], documents: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const { tags } = useTags();

  const load = useCallback(() => {
    let isMounted = true;
    setIsLoading(true);
    Promise.all([documentService.getLineItems(), documentService.getAccounts(), documentService.getDocuments()])
      .then(([lines, accounts, documents]) => {
        if (isMounted) setData({ lines: lines || [], accounts: accounts || [], documents: documents || [] });
      })
      .catch((err) => {
        console.error("Failed to load the dashboard data:", err);
        if (isMounted) setError("Failed to load your data. Please try again later.");
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => load(), [load]);

  return { ...data, tags, isLoading, error };
};
