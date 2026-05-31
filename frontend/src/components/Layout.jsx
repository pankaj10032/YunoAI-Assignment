import React from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useTheme } from "../context/ThemeContext";

const navItems = [
  { label: "Dashboard", path: "/" },
  { label: "Agents", path: "/agents" },
  { label: "Workflows", path: "/workflows" },
  { label: "Monitor", path: "/monitor" },
  { label: "Settings", path: "/settings" },
];

const pageTitles = {
  "/": "Dashboard",
  "/agents": "Agents",
  "/workflows": "Workflows",
  "/monitor": "Monitor",
  "/settings": "Settings",
};

export default function Layout() {
  const location = useLocation();
  const title = pageTitles[location.pathname] || "AI Orchestrator";
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="min-h-screen bg-canvas text-ink transition-colors duration-300">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-surface lg:block">
        <div className="border-b border-line px-6 py-5">
          <p className="text-sm font-semibold uppercase text-muted">Platform</p>
          <h1 className="mt-1 text-2xl font-bold">AI Orchestrator</h1>
        </div>
        <nav className="space-y-1 px-3 py-4">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-ink text-white"
                    : "text-muted hover:bg-soft hover:text-ink"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 border-b border-line bg-surface/95 px-4 py-4 backdrop-blur transition-colors duration-300 sm:px-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase text-muted">
                Agent workspace
              </p>
              <h2 className="text-2xl font-bold">{title}</h2>
            </div>
            <div className="flex items-center gap-2 sm:gap-3">
              <button
                type="button"
                role="button"
                aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
                onClick={toggleTheme}
                className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-line bg-surface text-ink transition-colors duration-300 hover:bg-soft focus:outline-none focus:ring-2 focus:ring-ink/30"
              >
                {theme === "dark" ? (
                  <SunIcon />
                ) : (
                  <MoonIcon />
                )}
              </button>
              <div className="hidden items-center gap-3 rounded-md border border-line bg-surface-strong px-3 py-2 text-sm sm:flex">
                <span className="h-2 w-2 rounded-full bg-emerald-600" />
                Demo Admin
              </div>
            </div>
          </div>
          <nav className="mt-4 flex gap-2 overflow-x-auto lg:hidden">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-ink text-white"
                      : "bg-surface text-muted ring-1 ring-line hover:bg-soft hover:text-ink"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </header>
        <main className="px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.8A8.5 8.5 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8l1.8-1.8M18 6l1.8-1.8" />
    </svg>
  );
}
