import { useCallback, useMemo, useState } from "react";

export const lineKey = (line) => `${line.kind}-${line.id}`;

/* The line items picked to be removed together. A line is picked with the box
   which appears beside it, or by shift-clicking it; picking it again lets it go. */
export const useLineSelection = (lines) => {
  const [keys, setKeys] = useState(() => new Set());

  const toggle = useCallback((line) => {
    setKeys((prev) => {
      const next = new Set(prev);
      const key = lineKey(line);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const clear = useCallback(() => setKeys(new Set()), []);
  const has = useCallback((line) => keys.has(lineKey(line)), [keys]);
  /* only lines which still exist: a removed or refreshed-away line is not picked */
  const selectedLines = useMemo(() => lines.filter((l) => keys.has(lineKey(l))), [lines, keys]);

  return { has, toggle, clear, selectedLines, count: selectedLines.length };
};
