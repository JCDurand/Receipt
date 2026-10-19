import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { useShownTitle } from "./PageTitle";
import { useLocalStorage } from "./useLocalStorage";
import "../styles/PreferencesBar.css";

const Svg = ({ children }) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
);

const MoonIcon = () => (
  <Svg>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </Svg>
);

const SunIcon = () => (
  <Svg>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Svg>
);

const GearIcon = () => (
  <Svg>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </Svg>
);

/* The bar across the top of every page once signed in: the page's title on the left
   and, on the right, the dark mode switch and the way to Settings. Dark mode choice
   is saved in local storage and applied to the page through the data-theme attribute. */

const PreferencesBar = () => {
  const { currentUser } = useAuth();
  const { pathname } = useLocation();
  const title = useShownTitle();
  const [isDark, setIsDark] = useLocalStorage("darkModeChosen", false);
  React.useEffect(() => {
    document.body.dataset.theme = isDark ? "dark" : "light";
  }, [isDark]);

  /* the sign-in page has neither the navbar nor a user */
  if (!currentUser || pathname === "/") return null;

  return (
    <div className="preferences-bar">
      <h1 className="preferences-title" title={title}>
        {title}
      </h1>
      <div className="preferences-actions" role="toolbar" aria-label="Preferences">
        <button
          type="button"
          className="preferences-btn"
          aria-pressed={isDark}
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
          title={isDark ? "Switch to light mode" : "Switch to dark mode"}
          onClick={() => setIsDark(!isDark)}
        >
          {isDark ? <SunIcon /> : <MoonIcon />}
        </button>
        <Link to="/settings" className="preferences-btn" aria-label="Settings" title="Settings">
          <GearIcon />
        </Link>
      </div>
    </div>
  );
};

export default PreferencesBar;
