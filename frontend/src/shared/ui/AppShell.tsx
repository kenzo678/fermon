import type { ReactNode } from "react";
import { Link, useLocation } from "react-router";

export interface NavItem {
  to: string;
  label: string;
  /** Path prefixes that keep this item highlighted (e.g. `/tanks` for the overview at `/`). */
  sections: string[];
}

interface AppShellProps {
  children: ReactNode;
  /** Defaults to the app's sections; the caller decides what the current user may see. */
  nav?: NavItem[];
  /** Who is signed in and how to leave: rendered at the end of the header. */
  account?: ReactNode;
  /** Extra content shown inside a nav link, keyed by its `to` (e.g. a live counter). */
  navBadges?: Partial<Record<string, ReactNode>>;
}

export const DEFAULT_NAV: NavItem[] = [
  { to: "/", label: "Tanks", sections: ["/tanks"] },
  { to: "/batches", label: "Batches", sections: ["/batches"] },
  { to: "/alerts", label: "Alerts", sections: ["/alerts"] },
];

function isCurrent(pathname: string, to: string, sections: string[]): boolean {
  return pathname === to || sections.some((s) => pathname === s || pathname.startsWith(`${s}/`));
}

export function AppShell({ children, nav = DEFAULT_NAV, account, navBadges = {} }: AppShellProps) {
  const { pathname } = useLocation();
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 sm:px-6">
          <h1 className="text-lg font-semibold tracking-tight">Fermon</h1>
          {nav.length > 0 && (
          <nav aria-label="Main" className="flex gap-4 text-sm">
            {nav.map(({ to, label, sections }) => {
              const current = isCurrent(pathname, to, sections);
              return (
                <Link
                  key={to}
                  to={to}
                  aria-current={current ? "page" : undefined}
                  className={`inline-flex items-center gap-1.5 rounded px-1 py-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 ${
                    current ? "font-semibold text-slate-900 underline" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {label}
                  {navBadges[to] !== undefined && " "}
                  {navBadges[to]}
                </Link>
              );
            })}
          </nav>
          )}
          {account !== undefined && <div className="ml-auto">{account}</div>}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">{children}</main>
    </div>
  );
}
