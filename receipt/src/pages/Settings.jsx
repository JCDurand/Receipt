import React, { useEffect, useState } from "react";
import PageShell from "../components/PageShell";
import { useAuth } from "../components/AuthContext";

/* The user's preferences: for now, the currency every figure is shown in */
const Settings = () => {
  const { currency, currencies, changeCurrency } = useAuth();
  const [chosen, setChosen] = useState(currency);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState(null);

  /* the settings can arrive after this page opens */
  useEffect(() => setChosen(currency), [currency]);

  const save = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);
    setSaved(null);
    try {
      const code = await changeCurrency(chosen);
      setSaved(code);
    } catch (err) {
      setError(err.serverMessage || "Your currency could not be saved. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  const name = (code) => currencies.find((c) => c.code === code)?.name || code;

  return (
    <PageShell title="Settings" subtitle="How your figures are shown">
      <section className="dashboard-panel settings-panel">
        <h3 className="dashboard-panel-title">Currency</h3>
        <form className="settings-form" onSubmit={save}>
          <label htmlFor="settings-currency" className="spending-label">
            Show every amount in
          </label>
          <select
            id="settings-currency"
            className="analytics-select"
            value={chosen}
            onChange={(e) => {
              setChosen(e.target.value);
              setSaved(null);
            }}
            disabled={currencies.length === 0}
          >
            {currencies.length === 0 && <option value={chosen}>{chosen}</option>}
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code} · {c.name}
              </option>
            ))}
          </select>
          <button type="submit" className="spending-pill is-on" disabled={isSaving || chosen === currency}>
            {isSaving ? "Saving..." : "Save"}
          </button>
        </form>

        {saved && (
          <p className="settings-saved" role="status">
            <span aria-hidden="true">✓</span> Every figure is now shown in {name(saved)} ({saved}).
          </p>
        )}
        {error && <p className="spending-warning">{error}</p>}

        <div className="settings-note">
          <p>
            Documents are kept in the currency they were recorded in, and are converted to {name(currency)} ({currency}) when they are
            shown, at the exchange rate of the day of each line. So a statement in another currency adds to your totals in{" "}
            {currency}, and changing currency here changes every figure on every page.
          </p>
          <p>
            A line which was converted is marked with the change, like <span className="conversion-badge">ZAR -&gt; USD</span>; hover
            over it to see the amount as it was recorded and the rate used. You choose the currency of a document when you upload it.
          </p>
          <p className="spending-hint">
            Rates are the European Central Bank's daily reference rates, from <a href="https://frankfurter.dev" target="_blank" rel="noreferrer">Frankfurter</a>.
            They are published on working days, so a weekend uses the rate of the working day before it.
          </p>
        </div>
      </section>
    </PageShell>
  );
};

export default Settings;
