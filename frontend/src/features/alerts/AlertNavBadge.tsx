import { useTanksQuery } from "../tanks/useTanksQuery";
import { AlertBadge } from "./components/AlertBadge";

/**
 * Header counter. Its source of truth is the tank list: the sum of `open_alerts` (unresolved
 * alerts per tank). The overview needs that query anyway, so the number is shared with the tank
 * cards, is never capped by a page limit, and live alert events keep it fresh.
 */
export function AlertNavBadge() {
  const { data } = useTanksQuery();
  return <AlertBadge count={data?.reduce((sum, tank) => sum + tank.open_alerts, 0) ?? 0} />;
}
