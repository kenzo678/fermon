import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { TanksOverviewPage } from "../features/tanks";
import { LoadingState } from "../features/tanks/components/LoadingState";
import { AppShell } from "../shared/ui";
import { NotFoundPage } from "./NotFoundPage";
import { RouteErrorBoundary } from "./RouteErrorBoundary";

// The detail page pulls in ECharts; loading it on demand keeps the overview bundle small on mobile.
const TankDetailPage = lazy(() =>
  import("../features/tanks/TankDetailPage").then((module) => ({ default: module.TankDetailPage })),
);

export function AppRoutes() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<TanksOverviewPage />} />
        <Route
          path="/tanks/:tankId"
          element={
            <RouteErrorBoundary>
              <Suspense fallback={<LoadingState />}>
                <TankDetailPage />
              </Suspense>
            </RouteErrorBoundary>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
