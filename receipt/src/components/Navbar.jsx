import { NavLink, useLocation } from "react-router-dom";
import React from "react";
import "../styles/Navbar.css";
import { useAuth } from "../components/AuthContext";
import { useLocalStorage } from "./useLocalStorage";
import navbar_logo from "../assets/navbar_logo.png";

/* The pages under "Dashboard", the first of which is the dashboard itself */
export const DASHBOARD_PAGES = [
  { to: "/dashboard", label: "Overview", end: true },
  { to: "/dashboard/expenses", label: "Expense Analysis" },
  { to: "/dashboard/income", label: "Income Analysis" },
  { to: "/dashboard/budgeting", label: "Budgeting" },
  { to: "/dashboard/subscriptions", label: "Subscriptions" },
  { to: "/dashboard/timeline", label: "Timeline Tree" },
];

/* The other pages, in groups: viewing the records, and managing what they come from */
const RECORD_PAGES = [
  { to: "/transactions", label: "Transactions" },
  { to: "/statements", label: "Statements" },
  { to: "/review", label: "Review" },
];

const MANAGE_PAGES = [
  { to: "/uploads", label: "Source Documents" },
  { to: "/accounts", label: "Accounts" },
  { to: "/tags", label: "Tags"},
];

/* A heading which opens and closes the pages under it. It is opened and closed
   only by clicking it, never by moving between pages, and is kept (each page has
   its own Navbar) so that it is as it was left. */
const NavGroup = ({ id, label, pages, pathname }) => {
  const [isOpen, setIsOpen] = useLocalStorage(`nav-${id}-open`, false);
  const hasActive = pages.some((page) => (page.end ? pathname === page.to : pathname === page.to || pathname.startsWith(`${page.to}/`)));
  return (
    <>
      <button
        type="button"
        className={`navbar-group-toggle${hasActive ? " has-active" : ""}`}
        aria-expanded={isOpen}
        aria-controls={`navbar-${id}-pages`}
        onClick={() => setIsOpen(!isOpen)}
      >
        <span>{label}</span>
        <span className="navbar-group-caret" aria-hidden="true">{isOpen ? "▾" : "▸"}</span>
      </button>
      {isOpen && (
        <div className="navbar-group" id={`navbar-${id}-pages`}>
          {pages.map((page) => (
            <NavLink key={page.to} to={page.to} end={page.end} className={({ isActive }) => (isActive ? "active" : "")}>
              <p>{page.label}</p>
            </NavLink>
          ))}
        </div>
      )}
    </>
  );
};

const Navbar = () => {
  const { currentUser, logout } = useAuth();
  const { pathname } = useLocation();

  const fullName = [currentUser?.first_name, currentUser?.last_name].filter(Boolean).join(" ");

  const getUserInitials = () => {
    if (!currentUser) return "U";
    return currentUser.username ? currentUser.username.charAt(0).toUpperCase() : "U";
  };

  return (
    <div>
      <div className="container_nav">
        {/* Logo */}
        <div className="navbar-header">
          <div className="navbar-logos">
            <img src={navbar_logo} alt="Receiptify Logo" />
          </div>

          {/* Navigation Links */}
          <div className="navbar-links">
            <NavGroup id="dashboard" label="Dashboard" pages={DASHBOARD_PAGES} pathname={pathname} />
            <NavGroup id="records" label="Records" pages={RECORD_PAGES} pathname={pathname} />
            <NavGroup id="manage" label="Manage" pages={MANAGE_PAGES} pathname={pathname} />
            <NavLink to="/settings" className={({ isActive }) => `navbar-settings-link${isActive ? " active" : ""}`}>
              <p>Settings</p>
            </NavLink>
          </div>
        </div>

        {/* User Section */}
        <div className="navbar-user">
          <div className="user-info">
            {/* <div className="user-avatar" title={currentUser?.username || "User"}>
              {currentUser?.avatar ? (
                <img src={currentUser.avatar} alt="User avatar" />
              ) : (
                getUserInitials()
              )}
            </div> */}
            {fullName && (
              <span className="user-fullname" title={fullName}>
                {fullName}
              </span>
            )}
            <span className="username" title={currentUser?.username || undefined}>
              {currentUser?.username || "User"}
            </span>
          </div>
          <button onClick={logout} className="logout-btn">
            Log Out
          </button>
        </div>
      </div>
    </div>
  );
};

export default Navbar;
