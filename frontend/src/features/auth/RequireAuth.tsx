import { Navigate, Outlet, useLocation } from "react-router";
import { ErrorState } from "../tanks/components/ErrorState";
import { PASSWORD_PATH } from "./AccountMenu";
import { useSession } from "./hooks";

/**
 * Route guard: nothing under it renders without a session. Visitors go to the login page (which
 * sends them back here afterwards); a temporary password must be replaced before anything else.
 */
export function RequireAuth() {
  const session = useSession();
  const { pathname, search, hash } = useLocation();

  if (session.isPending) {
    return (
      <div
        role="status"
        aria-label="Checking your session"
        className="mx-auto mt-24 h-16 max-w-sm animate-pulse rounded-lg bg-slate-200"
      />
    );
  }
  if (session.isError) {
    return (
      <div className="mx-auto mt-24 max-w-md px-4">
        <ErrorState message={session.error.message} onRetry={() => void session.refetch()} />
      </div>
    );
  }
  const user = session.data;
  if (user === null) return <Navigate to="/login" replace state={{ from: `${pathname}${search}${hash}` }} />;
  if (user.must_change_password && pathname !== PASSWORD_PATH) return <Navigate to={PASSWORD_PATH} replace />;
  return <Outlet />;
}
