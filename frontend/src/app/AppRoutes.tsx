import { Route, Routes } from "react-router";
import { TankDetailPlaceholder, TanksOverviewPage } from "../features/tanks";
import { AppShell } from "../shared/ui";
import { NotFoundPage } from "./NotFoundPage";

export function AppRoutes() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<TanksOverviewPage />} />
        <Route path="/tanks/:tankId" element={<TankDetailPlaceholder />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
