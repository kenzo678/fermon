import type { ReactNode } from "react";
import { Link, useLocation } from "react-router";

interface AppShellProps {
  children: ReactNode;
}

const NAV = [
  { to: "/", label: "Tanks", sections: ["/tanks"] },
  { to: "/batches", label: "Batches", sections: ["/batches"] },
];

function isCurrent(pathname: string, to: string, sections: string[]): boolean {
  return pathname === to || sections.some((s) => pathname === s || pathname.startsWith(`${s}/`));
}

export function AppShell({ children }: AppShellProps) {
  const { pathname } = useLocation();
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 sm:px-6">
          <h1 className="text-lg font-semibold tracking-tight">Fermon</h1>
          <nav aria-label="Main" className="flex gap-4 text-sm">
            {NAV.map(({ to, label, sections }) => {
              const current = isCurrent(pathname, to, sections);
              return (
                <Link
                  key={to}
                  to={to}
                  aria-current={current ? "page" : undefined}
                  className={`rounded px-1 py-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 ${
                    current ? "font-semibold text-slate-900 underline" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">{children}</main>
    </div>
  );
}
