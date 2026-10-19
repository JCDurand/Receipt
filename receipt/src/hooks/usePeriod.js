import { useMemo, useState } from "react";
import { periodPresets } from "../utils/periods";

/* The period a page looks at: one of the presets, or a custom range */
export const usePeriod = (defaultKey = "3m") => {
  const presets = useMemo(() => periodPresets(), []);
  const initial = presets.find((p) => p.key === defaultKey) || presets[0];
  const [period, setPeriod] = useState({ key: initial.key, from: initial.from, to: initial.to });

  const choosePreset = (key) => {
    const preset = presets.find((p) => p.key === key);
    if (preset) setPeriod({ key, from: preset.from, to: preset.to });
  };
  const chooseDates = (changes) => setPeriod((prev) => ({ ...prev, ...changes, key: "custom" }));

  return { period, presets, choosePreset, chooseDates };
};
