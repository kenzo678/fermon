import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import { useLiveAlerts } from "./useLiveAlerts";
import type { LiveAlertsStatus } from "./useLiveAlerts";

const LiveAlertsContext = createContext<LiveAlertsStatus>("offline");

/**
 * Mounts the single `/ws/alerts` socket for the whole app (so counters stay live on every page)
 * and shares its connection status with whoever wants to display it.
 */
export function LiveAlertsProvider({ children }: { children: ReactNode }) {
  const status = useLiveAlerts();
  return <LiveAlertsContext.Provider value={status}>{children}</LiveAlertsContext.Provider>;
}

export function useLiveAlertsStatus(): LiveAlertsStatus {
  return useContext(LiveAlertsContext);
}
