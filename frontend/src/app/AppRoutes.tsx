import { lazy, Suspense } from "react";
import type { ReactNode } from "react";
import { Route, Routes } from "react-router";
import { AlertNavBadge } from "../features/alerts/AlertNavBadge";
import { LiveAlertsProvider } from "../features/alerts/LiveAlerts";
import { TanksOverviewPage } from "../features/tanks";
import { LoadingState } from "../features/tanks/components/LoadingState";
import { AppShell } from "../shared/ui";
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

const NAV_BADGES = { "/alerts": <AlertNavBadge /> };

function Lazy({ children }: { children: ReactNode }) {
  return (
    <RouteBoundary>
      <Suspense fallback={<LoadingState />}>{children}</Suspense>
    </RouteBoundary>
  );
}

export function AppRoutes() {
  return (
    <LiveAlertsProvider>
      <AppShell navBadges={NAV_BADGES}>
        <Routes>
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
              <Lazy>
                <NewBatchPage />
              </Lazy>
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
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AppShell>
    </LiveAlertsProvider>
  );
}
