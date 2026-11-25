import { lazy, Suspense } from "react";
import type { ReactNode } from "react";
import { Outlet, Route, Routes } from "react-router";
import { AlertNavBadge } from "../features/alerts/AlertNavBadge";
import { LiveAlertsProvider } from "../features/alerts/LiveAlerts";
import { AccountMenu } from "../features/auth/AccountMenu";
import { ChangePasswordPage } from "../features/auth/ChangePasswordPage";
import { LoginPage } from "../features/auth/LoginPage";
import { RequireAuth } from "../features/auth/RequireAuth";
import { RequirePermission } from "../features/auth/RequirePermission";
import { usePermissions, useSession } from "../features/auth";
import { TanksOverviewPage } from "../features/tanks";
import { LoadingState } from "../features/tanks/components/LoadingState";
import { AppShell, DEFAULT_NAV } from "../shared/ui";
import type { NavItem } from "../shared/ui";
import { NotFoundPage } from "./NotFoundPage";
import { RouteBoundary } from "./RouteErrorBoundary";

// The detail page pulls in ECharts; loading it on demand keeps the overview bundle small on mobile.
const TankDetailPage = lazy(() =>
  import("../features/tanks/TankDetailPage").then((module) => ({ default: module.TankDetailPage })),
);

// Batch pages carry the form code; none of it is needed to render the overview.
const BatchesPage = lazy(() =>
  import("../features/batches/BatchesPage").then((module) => ({ default: module.BatchesPage })),
);
const NewBatchPage = lazy(() =>
  import("../features/batches/NewBatchPage").then((module) => ({ default: module.NewBatchPage })),
);
const BatchDetailPage = lazy(() =>
  import("../features/batches/BatchDetailPage").then((module) => ({ default: module.BatchDetailPage })),
);

// The page itself is lazy; the live socket and the header counter are not, so they work everywhere.
const AlertsPage = lazy(() =>
  import("../features/alerts/AlertsPage").then((module) => ({ default: module.AlertsPage })),
);

// Admin-only page; its code is not needed by anyone else.
const UsersPage = lazy(() =>
  import("../features/users/UsersPage").then((module) => ({ default: module.UsersPage })),
);

const NAV_BADGES = { "/alerts": <AlertNavBadge /> };
const ADMIN_NAV: NavItem[] = [...DEFAULT_NAV, { to: "/users", label: "Users", sections: ["/users"] }];

function Lazy({ children }: { children: ReactNode }) {
  return (
    <RouteBoundary>
      <Suspense fallback={<LoadingState />}>{children}</Suspense>
    </RouteBoundary>
  );
}

/**
 * Everything behind the login: the header (navigation by role, account menu) and the live alerts
 * socket. A user who must replace a temporary password gets neither, because the API refuses
 * everything else until they do.
 */
function AuthenticatedLayout() {
  const forcedChange = useSession().data?.must_change_password === true;
  const { canManageUsers } = usePermissions();
  const shell = (
    <AppShell
      nav={forcedChange ? [] : canManageUsers ? ADMIN_NAV : DEFAULT_NAV}
      account={<AccountMenu showChangePassword={!forcedChange} />}
      navBadges={forcedChange ? {} : NAV_BADGES}
    >
      <Outlet />
    </AppShell>
  );
  return forcedChange ? shell : <LiveAlertsProvider>{shell}</LiveAlertsProvider>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AuthenticatedLayout />}>
          <Route path="/" element={<TanksOverviewPage />} />
          <Route
            path="/tanks/:tankId"
            element={
              <Lazy>
                <TankDetailPage />
              </Lazy>
            }
          />
          <Route
            path="/batches"
            element={
              <Lazy>
                <BatchesPage />
              </Lazy>
            }
          />
          <Route
            path="/batches/new"
            element={
              <RequirePermission allow={(permissions) => permissions.canWriteBatches}>
                <Lazy>
                  <NewBatchPage />
                </Lazy>
              </RequirePermission>
            }
          />
          <Route
            path="/batches/:batchId"
            element={
              <Lazy>
                <BatchDetailPage />
              </Lazy>
            }
          />
          <Route
            path="/alerts"
            element={
              <Lazy>
                <AlertsPage />
              </Lazy>
            }
          />
          <Route path="/account/password" element={<ChangePasswordPage />} />
          <Route
            path="/users"
            element={
              <RequirePermission allow={(permissions) => permissions.canManageUsers}>
                <Lazy>
                  <UsersPage />
                </Lazy>
              </RequirePermission>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
